"""Orquestrador de transcrição de áudio de telefonia (coração do pipeline de auditoria).

Papel no fluxo: recebe os bytes do áudio da ligação (auditoria manual ou
automação), prepara o arquivo para o Azure, executa a cadeia de engines de
transcrição, pontua cada resultado como candidato e devolve os segmentos
diarizados ("Operador:" / "Motorista:") que alimentam a avaliação GPT-4o em
`core/evaluation.py`.

Arquitetura atual (default desde 2026-05-20):
- Engine DEFAULT é `fast` (Azure Fast Transcription REST) — melhor texto para
  telefonia G.729/GSM. Cadeia de fallback: fast → whisper → gpt4o_diarize → sdk.
- CANDIDATE SELECTOR (`core/transcription_selector.py`): cada engine executada
  vira um `TranscriptionCandidate` com score determinístico (diarização +
  qualidade de texto); o selector decide aceitar, aguardar confirmação de
  outra engine ou exigir revisão manual.
- JUDGE LLM (`core/transcription_judge.py`): desempata os dois melhores
  candidatos quando o selector sinaliza `empate_requer_judge` (1 chamada
  GPT-4o adicional).
- `hybrid_dual` (Diarize + Whisper em paralelo + fusão GPT-4o) é LEGADO
  opt-in via AZURE_TRANSCRIPTION_ENGINE=hybrid_dual. NÃO recomendar nem
  reativar — mantido apenas por compatibilidade.

CUSTO DE API: praticamente tudo aqui dispara chamadas PAGAS ao Azure. Cada
estratégia adicional da cadeia de fallback soma custo. Registro no
`cost_guard` (teto diário) por categoria:
- `transcricao_fast`    → Azure Speech (em `transcription_providers/azure.py`)
- `transcricao_whisper` → Azure OpenAI Whisper (idem)
- `transcricao_diarize` → GPT-4o-transcribe-diarize (`openai_diarize.py`)
- `merge_hybrid_dual`   → GPT-4o de fusão (neste módulo)
- `judge_transcricao`   → GPT-4o do judge (`transcription_judge.py`)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None
from typing import Any, Callable, Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from schemas import AuditAlert
import db.database as database
from audio.diarization_quality import (
    build_diarization_quality,
    build_diarization_reference,
    clone_transcription_segment,
    detect_audio_mime_type,
    extract_audio_excerpt,
    extract_segment_speaker,
    normalize_lookup_text,
    parse_float_value,
)
from utils.text_processing import (
    TEXT_CORRECTIONS_CONFIG,
    deduplicate_transcription_segments,
    filter_hallucinations,
    normalize_company_name,
    normalize_speaker_prefix,
    normalize_text_for_dedupe,
    remove_emojis,
)
from audio.audio_utils import (
    convert_audio_to_mp3,
    convert_audio_to_wav,
    split_stereo_audio,
)
from core.transcription_orchestrator import (
    build_strategy_order,
    infer_interlocutor_label,
    prepare_audio_for_azure,
    run_transcription_pipeline,
    score_transcription_segments,
    transcription_looks_valid,
)
from transcription_providers.openai_diarize import (
    GPT4oDiarizeTranscriptionDependencies,
    transcribe_audio_gpt4o_diarize as run_gpt4o_diarize_transcription,
)
from transcription_providers.azure import (
    AzureTranscriptionDependencies,
    transcribe_audio_azure as run_azure_transcription,
)
from transcription_providers.common import build_transcription_domain_prompt
from core.transcription_candidates import TranscriptionCandidate, build_candidate
from core.transcription_cross_signals import compute_cross_signals
from core.transcription_selector import (
    DECISION_ACCEPTED,
    DECISION_MANUAL_REVIEW,
    DECISION_NEEDS_REVIEW,
    DECISION_REJECTED,
    select_transcription_candidate,
)
from core.transcription_judge import JudgeOutcome, judge_tie_break

from core.config import (
    AI_MODEL,
    AI_PROVIDER_PRIORITY,
    AZURE_ACCEPTED_MIME,
    AZURE_SPEECH_KEY,
    LOSSLESS_OR_PCM_MIME_TYPES,
    WAV_MIME_TYPES,
    PROMPTS_CONFIG,
    _env_flag,
    _get_azure_gpt4o_diarize_auth_mode,
    _get_azure_gpt4o_diarize_model_name,
    _get_gpt4o_diarize_min_score,
    _get_gpt4o_diarize_primary_prescan_min_score,
    _get_gpt4o_diarize_primary_prescan_seconds,
    _get_gpt4o_diarize_primary_sectors,
    _get_gpt4o_diarize_retry_count,
    _get_gpt4o_diarize_retry_delay_seconds,
    _get_transcription_timeout_seconds,
    _get_whisper_temperature,
    _resolve_azure_gpt4o_diarize_config,
    _resolve_azure_whisper_config,
    ai_client,
)
from core.evaluation import parse_json_with_repair

__all__ = [
    # Funções públicas de transcrição
    "compute_input_hash",
    "validate_transcription", "extract_transcription",
    "transcribe_audio",
    "transcribe_audio_azure", "transcribe_audio_assemblyai", "transcribe_audio_gpt4o_diarize",
    "parse_iso_duration",
    # Funções internas (usadas por testes e evaluation/audit)
    "_should_use_gpt4o_diarize_as_primary",
    "_should_preprocess_audio_for_azure",
    "_build_candidate_diarization",
    "_extract_numeric_evidence",
    "_validate_merged_evidence",
    "_transcription_candidate_is_acceptable",
    "_score_transcription_candidate",
    "_should_promote_prescan_to_gpt4o",
    "_should_use_gpt4o_diarize_as_primary_for_audio",
    "_resolve_transcription_engine",
    "_guess_audio_filename",
    "_to_milliseconds", "_normalize_speaker_id",
    "_extract_phrase_text", "_extract_phrase_timing_ms",
    "_transcription_looks_valid", "_score_transcription_segments",
    "_should_discard_whisper_segment", "_should_replace_whisper_segment_with_inaudivel",
    # Aliases internos
    "_normalize_lookup_text", "_extract_segment_speaker",
    "_clone_transcription_segment", "_parse_float",
]

# ── Resolução de engine (default fast; hybrid_dual é legado opt-in) ─────────

# Grafias aceitas historicamente para o engine legado; todas normalizam para
# o id canônico "hybrid_dual".
_LEGACY_HYBRID_DUAL_ALIASES = {
    "hybrid_dual",
    "hybrid-dual",
    "hybrid dual",
    "dual_hybrid",
    "dual-hybrid",
    "dual hybrid",
}


def _resolve_transcription_engine(raw_engine: Optional[str]) -> str:
    """Normaliza o valor de AZURE_TRANSCRIPTION_ENGINE para um id canônico."""
    # Migracao: fast e o engine PADRAO em todos os fluxos. hybrid_dual fica como
    # legado opt-in — so roda quando pedido explicitamente via
    # AZURE_TRANSCRIPTION_ENGINE=hybrid_dual (ou pelos aliases legados).
    engine = str(raw_engine or "fast").strip().lower() or "fast"
    if engine in _LEGACY_HYBRID_DUAL_ALIASES:
        return "hybrid_dual"
    return engine

# ── Hash de idempotência e validação do formato de transcrição ──────────────

def compute_input_hash(
    audio_file: bytes,
    mime_type: str,
    alert: AuditAlert,
    operator_name: Optional[str],
    operator_id: Optional[str],
    sector_id: Optional[str]
) -> str:
    """SHA-256 determinístico das entradas de uma auditoria (idempotência).

    Combina bytes do áudio + mime + alerta serializado + identidade do
    operador/setor. Usado pela automação para detectar reprocessamento do
    mesmo item e evitar gastar transcrição/avaliação (chamadas pagas) à toa.
    Mudar a composição deste hash invalida deduplicações já persistidas.
    """
    hasher = hashlib.sha256()
    hasher.update(mime_type.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(audio_file)
    hasher.update(b"\0")
    alert_payload = alert.model_dump() if hasattr(alert, "model_dump") else alert.dict()
    alert_json = json.dumps(alert_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    hasher.update(alert_json.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update((operator_name or "").encode("utf-8"))
    hasher.update(b"\0")
    hasher.update((operator_id or "").encode("utf-8"))
    hasher.update(b"\0")
    hasher.update((sector_id or "").encode("utf-8"))
    return hasher.hexdigest()
def validate_transcription(data: Any) -> bool:
    """Confere se o payload tem o formato mínimo de transcrição.

    Aceita lista de segmentos ou dict com chave "transcription"; cada
    segmento precisa de start/end/text. Não valida conteúdo, só estrutura.
    """
    if isinstance(data, dict) and "transcription" in data:
        data = data.get("transcription")
    if not isinstance(data, list):
        return False
    for item in data:
        if not isinstance(item, dict):
            return False
        if "start" not in item or "end" not in item or "text" not in item:
            return False
    return True
def extract_transcription(data: Any) -> list[dict]:
    """Extrai a lista de segmentos do JSON retornado pela IA (dict ou lista)."""
    if isinstance(data, dict):
        t = data.get("transcription", [])
        return t if isinstance(t, list) else []
    if isinstance(data, list):
        return data
    return []
# ── Integridade da fusão GPT-4o (estrutura + evidência numérica) ────────────
# Helpers usados pelo hybrid_dual (LEGADO) para garantir que a fusão não
# corrompa timestamps, falantes nem números ditados (senhas, CPFs, placas).

def _timestamp_signature(segment: dict) -> tuple[str, str]:
    """Par (start, end) como strings, usado como chave de pareamento de segmentos."""
    return (str(segment.get("start") or "").strip(), str(segment.get("end") or "").strip())


def _timestamps_equivalent(first: str, second: str) -> bool:
    """Compara timestamps com tolerância de 1 ms (formatos textuais variam)."""
    if first == second:
        return True
    return abs(parse_iso_duration(first) - parse_iso_duration(second)) <= 0.001


def _preserve_diarization_metadata(
    merged_segments: list[dict],
    diarized_segments: list[dict],
) -> list[dict]:
    """Preserva os metadados de falante após a fusão de texto com GPT-4o.

    O prompt de fusão pede ao GPT-4o que retorne apenas start/end/text. A
    validação de candidatos ainda precisa dos campos nativos de diarização
    dos segmentos de origem para pontuar corretamente a confiabilidade de
    falante — então eles são re-anexados aqui (sem sobrescrever start/end/text).
    """
    if not isinstance(merged_segments, list) or not isinstance(diarized_segments, list):
        return merged_segments

    base_by_timestamp: dict[tuple[str, str], dict] = {}
    for segment in diarized_segments:
        if isinstance(segment, dict):
            signature = _timestamp_signature(segment)
            if any(signature):
                base_by_timestamp.setdefault(signature, segment)

    enriched: list[dict] = []
    protected_keys = {"start", "end", "text"}
    for index, merged_segment in enumerate(merged_segments):
        if not isinstance(merged_segment, dict):
            enriched.append(merged_segment)
            continue
        base_segment = base_by_timestamp.get(_timestamp_signature(merged_segment))
        if base_segment is None and index < len(diarized_segments) and isinstance(diarized_segments[index], dict):
            base_segment = diarized_segments[index]
        if base_segment is None:
            enriched.append(merged_segment)
            continue

        restored = dict(merged_segment)
        for key, value in base_segment.items():
            if key not in protected_keys and key not in restored:
                restored[key] = value
        enriched.append(restored)
    return enriched


def _segments_to_text(segments: list[dict]) -> str:
    """Concatena o texto de todos os segmentos em uma única string."""
    return " ".join(str(segment.get("text") or "") for segment in segments if isinstance(segment, dict))


def _extract_numeric_evidence(text: str) -> set[str]:
    """Extrai sequências de 4+ dígitos (senhas, CPFs, placas) ignorando separadores.

    São a "evidência numérica" que a fusão GPT-4o é proibida de perder ou
    inventar — base dos checks de `_validate_merged_evidence`.
    """
    evidence: set[str] = set()
    for match in re.finditer(r"(?:\d[\s\.\-:/]*){4,}", str(text or "")):
        digits = re.sub(r"\D+", "", match.group(0))
        if len(digits) >= 4:
            evidence.add(digits)
    return evidence


def _segments_numeric_evidence(segments: list[dict]) -> set[str]:
    """Evidência numérica do texto concatenado dos segmentos."""
    return _extract_numeric_evidence(_segments_to_text(segments))


def _validate_merged_structure(
    merged_segments: list[dict],
    diarized_segments: list[dict],
) -> dict[str, Any]:
    """Diagnostica mudanças estruturais da fusão (contagem, timestamps, falantes).

    Apenas diagnóstico — não bloqueia o processamento da auditoria por si só;
    quem decide rejeitar o merge é o chamador (`merge_transcriptions_with_gpt4o`).
    """
    issues: list[dict[str, Any]] = []
    expected_count = len(diarized_segments or [])
    actual_count = len(merged_segments or [])

    if actual_count != expected_count:
        issues.append(
            {
                "type": "segment_count_changed",
                "expected": expected_count,
                "actual": actual_count,
            }
        )

    for index, source_segment in enumerate(diarized_segments or []):
        if index >= actual_count:
            break
        merged_segment = merged_segments[index]
        if not isinstance(source_segment, dict) or not isinstance(merged_segment, dict):
            issues.append({"type": "invalid_segment", "index": index})
            continue

        source_start, source_end = _timestamp_signature(source_segment)
        merged_start, merged_end = _timestamp_signature(merged_segment)
        if not (
            _timestamps_equivalent(merged_start, source_start)
            and _timestamps_equivalent(merged_end, source_end)
        ):
            issues.append(
                {
                    "type": "timestamp_changed",
                    "index": index,
                    "expected": {"start": source_start, "end": source_end},
                    "actual": {"start": merged_start, "end": merged_end},
                }
            )

        source_speaker = normalize_lookup_text(extract_segment_speaker(str(source_segment.get("text") or "")))
        merged_speaker = normalize_lookup_text(extract_segment_speaker(str(merged_segment.get("text") or "")))
        if source_speaker and merged_speaker != source_speaker:
            issues.append(
                {
                    "type": "speaker_changed",
                    "index": index,
                    "expected": source_speaker,
                    "actual": merged_speaker,
                }
            )

    return {"ok": True, "has_diagnostics": bool(issues), "issues": issues}


def _validate_merged_evidence(
    merged_segments: list[dict],
    accurate_text: str,
    diarized_segments: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """Verifica se a fusão preservou a evidência numérica do Whisper.

    Retorna dict com `is_blocking` (corrupção REAL: número sumiu ou foi
    inventado) e diagnósticos não-bloqueantes (divergência entre as ASRs).
    Ver comentário inline sobre por que `numeric_conflict` NÃO bloqueia.
    """
    expected_numbers = _extract_numeric_evidence(accurate_text)
    merged_numbers = _segments_numeric_evidence(merged_segments)
    source_numbers = _segments_numeric_evidence(diarized_segments or [])

    missing_numbers = sorted(
        number for number in expected_numbers if number not in merged_numbers
    )
    unexpected_numbers = sorted(
        number
        for number in merged_numbers
        if number not in expected_numbers and number not in source_numbers
    )
    source_only_numbers = sorted(source_numbers - expected_numbers)
    accurate_only_numbers = sorted(expected_numbers - source_numbers)
    numeric_conflict = bool((source_numbers or expected_numbers) and source_numbers != expected_numbers)
    diagnostic_reasons: list[str] = []
    if missing_numbers:
        diagnostic_reasons.append("missing_numeric_sequences_from_whisper")
    if unexpected_numbers:
        diagnostic_reasons.append("unexpected_numeric_sequences")
    if numeric_conflict:
        diagnostic_reasons.append("numeric_conflict_between_sources")

    # Apenas missing/unexpected representam corrupcao REAL da fusao (numero do
    # whisper sumiu, ou GPT-4o inventou um numero que ninguem falou).
    # `numeric_conflict` apenas sinaliza que as duas ASRs (diarize vs whisper)
    # divergiram entre si — ruido esperado em audio ruidoso/longo, NAO defeito
    # do merge. Por isso e REPORTADO (has_diagnostics/diagnostic_reasons) mas
    # NAO bloqueia. Bloquear nele era falso-positivo que matava o hybrid_dual
    # justamente no audio dificil (v1.3.101).
    blocking = bool(missing_numbers or unexpected_numbers)

    return {
        "ok": True,
        "has_diagnostics": bool(diagnostic_reasons),
        "is_blocking": blocking,
        "diagnostic_reasons": diagnostic_reasons,
        "missing_numeric_sequences": missing_numbers,
        "unexpected_numeric_sequences": unexpected_numbers,
        "numeric_conflict_between_sources": numeric_conflict,
        "source_only_numeric_sequences": source_only_numbers,
        "accurate_only_numeric_sequences": accurate_only_numbers,
    }
# Aliases internos: nomes históricos deste módulo que os testes (e código
# legado) ainda importam; apontam para as implementações canônicas em
# audio.diarization_quality.
_normalize_lookup_text = normalize_lookup_text
_extract_segment_speaker = extract_segment_speaker
_clone_transcription_segment = clone_transcription_segment
_parse_float = parse_float_value


# ── Roteamento p/ GPT-4o diarize como engine primária (smart routing) ───────

def _resolve_whisper_prompt(sector_id: Optional[str]) -> str:
    """Prompt de vocabulário do Whisper: específico do setor (DB) ou default do JSON.

    Falha de banco não derruba a transcrição — cai no prompt local de
    `text_corrections.json`.
    """
    default_prompt = TEXT_CORRECTIONS_CONFIG.get(
        "whisper_prompt",
        "Opentech, nstech, BAS, motorista, placa, Mondelez, Unilever, Buonny, Sascar, Tracker, Onix, Autotrac, Omnilink, Ravex, isca, [Inaudível].",
    )
    try:
        from repositories.ai_prompts import get_whisper_prompt_for_sector

        return get_whisper_prompt_for_sector(database.get_connection, sector_id, default_prompt) or default_prompt
    except Exception:
        logger.debug("Falha ao carregar prompt Whisper por setor; usando fallback local.", exc_info=True)
        return default_prompt


def _should_use_gpt4o_diarize_as_primary(
    alert: Optional[AuditAlert],
    sector_id: Optional[str],
) -> bool:
    """Indica se o setor/alerta está na lista de setores que preferem GPT-4o diarize.

    A lista vem de env (AZURE_GPT4O_DIARIZE_PRIMARY_SECTORS); o match é por
    substring normalizada no sector_id e, na falta dele, no label/contexto do
    alerta. Só tem efeito quando o engine é auto/smart.
    """
    primary_sectors = _get_gpt4o_diarize_primary_sectors()
    if not primary_sectors:
        return False

    normalized_sector = _normalize_lookup_text(sector_id or "")
    if normalized_sector and any(primary in normalized_sector for primary in primary_sectors):
        return True

    haystack = _normalize_lookup_text(
        f"{getattr(alert, 'label', '') or ''} {getattr(alert, 'context', '') or ''}"
    )
    if haystack and any(primary in haystack for primary in primary_sectors):
        return True

    return False
def _should_preprocess_audio_for_azure(audio_size_bytes: int, mime_type: str) -> bool:
    """Decide se o áudio precisa ser convertido/comprimido antes do upload ao Azure.

    Sempre converte acima de 24 MB (limite prático de upload). Para formatos
    lossless/PCM, converte a partir de AZURE_LOSSLESS_PREPROCESS_MIN_BYTES
    (default 8 MB) para reduzir tempo e custo de transferência.
    """
    if int(audio_size_bytes or 0) >= 24 * 1024 * 1024:
        return True
    safe_mime = (mime_type or "").strip().lower()
    if safe_mime not in LOSSLESS_OR_PCM_MIME_TYPES:
        return False

    raw_min_bytes = os.getenv("AZURE_LOSSLESS_PREPROCESS_MIN_BYTES", str(8 * 1024 * 1024))
    try:
        min_bytes = int(str(raw_min_bytes).strip())
    except (TypeError, ValueError):
        min_bytes = 8 * 1024 * 1024
    min_bytes = max(0, min(min_bytes, 24 * 1024 * 1024))
    return int(audio_size_bytes or 0) >= min_bytes
def _build_candidate_diarization(transcription_segments: list[dict], diarization_reference: dict) -> dict[str, Any]:
    """Calcula as métricas de diarização (score, swap_risk...) de um candidato."""
    quality = build_diarization_quality(
        transcription_segments,
        {"diarization_reference": dict(diarization_reference or {})},
    )
    if not isinstance(quality, dict):
        return {}
    diarization = quality.get("diarization")
    return diarization if isinstance(diarization, dict) else {}
def _transcription_candidate_is_acceptable(
    transcription_segments: list[dict],
    diarization_reference: dict,
) -> bool:
    """Gate de aceitação imediata: texto válido + score de diarização mínimo + swap_risk low.

    Candidato aceitável encerra a cadeia de fallback (não gasta as próximas
    engines); reprovado vira "insufficient" mas continua concorrendo no selector.
    """
    if not _transcription_looks_valid(transcription_segments):
        return False
    diarization = _build_candidate_diarization(transcription_segments, diarization_reference)
    score = _parse_float(diarization.get("score"))
    swap_risk = str(diarization.get("swap_risk") or "").strip().lower()
    return bool(score is not None and score >= _get_gpt4o_diarize_min_score() and swap_risk == "low")
def _score_transcription_candidate(transcription_segments: list[dict], diarization_reference: dict) -> int:
    """Score determinístico do candidato: diarização (x10000) + bônus de risco + texto."""
    diarization = _build_candidate_diarization(transcription_segments, diarization_reference)
    diarization_score = _parse_float(diarization.get("score")) or 0.0
    swap_risk = str(diarization.get("swap_risk") or "").strip().lower()
    risk_bonus = {"low": 900, "medium": 300, "high": 0}.get(swap_risk, 0)
    return int(round(diarization_score * 10000)) + risk_bonus + _score_transcription_segments(transcription_segments)
def _should_promote_prescan_to_gpt4o(
    transcription_segments: list[dict],
    driver_label: str,
) -> bool:
    """Avalia o pré-scan (trecho curto via Fast) e decide se promove ao GPT-4o diarize.

    Promove quando o Fast não separou falantes (1 voz só), o swap_risk é alto
    ou o score ficou abaixo do mínimo configurado — sinais de que o diarize
    (mais caro) deve assumir como engine primária.
    """
    diarization_reference = build_diarization_reference(driver_label)
    diarization = _build_candidate_diarization(transcription_segments, diarization_reference)
    telephony_segment_count = int(diarization.get("telephony_segment_count") or 0)
    human_segment_count = int(diarization.get("human_segment_count") or 0)
    raw_speaker_count = int(diarization.get("raw_speaker_count") or 0)
    score = _parse_float(diarization.get("score")) or 0.0
    swap_risk = str(diarization.get("swap_risk") or "").strip().lower()
    if telephony_segment_count <= 0 or human_segment_count < 2:
        return False
    if raw_speaker_count <= 1:
        return True
    if swap_risk == "high":
        return True
    return score < _get_gpt4o_diarize_primary_prescan_min_score()
def _should_use_gpt4o_diarize_as_primary_for_audio(
    audio_file: bytes,
    mime_type: str,
    alert: Optional[AuditAlert],
    sector_id: Optional[str],
    operator_label: str,
    driver_label: str,
    *,
    gpt4o_diarize_available: bool,
) -> bool:
    """Decide se o GPT-4o diarize vira engine PRIMÁRIA para este áudio (smart routing).

    CUSTO: quando AZURE_GPT4O_DIARIZE_SMART_ROUTING está ativo (default),
    transcreve um TRECHO do áudio via Azure Fast Transcription (chamada paga,
    porém curta) como pré-scan antes de decidir. Falha do pré-scan assume
    GPT-4o como primário (fail-safe a favor da qualidade, não do custo).
    """
    if not gpt4o_diarize_available:
        return False
    if not _should_use_gpt4o_diarize_as_primary(alert, sector_id):
        return False
    if not _env_flag("AZURE_GPT4O_DIARIZE_SMART_ROUTING", True):
        return True

    try:
        excerpt_audio = extract_audio_excerpt(
            audio_file,
            mime_type,
            duration_seconds=_get_gpt4o_diarize_primary_prescan_seconds(),
        )
        excerpt_segments = transcribe_audio_azure(
            excerpt_audio,
            operator_label,
            driver_label,
            mime_type="audio/wav",
        )
        return _should_promote_prescan_to_gpt4o(excerpt_segments, driver_label)
    except Exception as exc:
        logger.warning("[Transcription] Smart routing falhou no pre-scan: %s; usando GPT-4o como primario", exc)
        return True
# ── Configuração do selector de candidatos e metadados de decisão ───────────

def _guess_audio_filename(mime_type: str) -> str:
    """Nome de arquivo sintético por MIME (as APIs Azure exigem filename no upload)."""
    mapping = {
        "audio/wav": "audio.wav",
        "audio/x-wav": "audio.wav",
        "audio/wave": "audio.wav",
        "audio/mpeg": "audio.mp3",
        "audio/mp3": "audio.mp3",
        "audio/ogg": "audio.ogg",
        "audio/webm": "audio.webm",
        "audio/mp4": "audio.m4a",
        "audio/x-m4a": "audio.m4a",
    }
    return mapping.get((mime_type or "").strip().lower(), "audio.wav")


def _get_transcription_strategy_timeout_seconds() -> int:
    """Timeout por estratégia da cadeia (default: timeout base + 240s, clamp 120–4200s)."""
    default_timeout = _get_transcription_timeout_seconds() + 240
    raw = os.getenv("AZURE_TRANSCRIPTION_STRATEGY_TIMEOUT_SECONDS", str(default_timeout))
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = default_timeout
    return max(120, min(parsed, 4200))


def _is_candidate_selector_enabled() -> bool:
    """Selector de candidatos ligado? (default ON; desligado = primeiro válido vence)."""
    return _env_flag("TRANSCRIPTION_CANDIDATE_SELECTOR_ENABLED", True)


def _critical_alert_for_transcription_selector(alert: Optional[AuditAlert]) -> bool:
    """Alerta crítico (polícia, pânico, sinistro...) endurece os gates do selector.

    Lista configurável via TRANSCRIPTION_CRITICAL_ALERT_IDS; match por
    substring no id/label do alerta.
    """
    configured = os.getenv(
        "TRANSCRIPTION_CRITICAL_ALERT_IDS",
        "PRIORITARIO-POLICIA,PARADA-MOT,BOTAO-PANICO,SUSPEITA-SINISTRO",
    )
    tokens = {
        token.strip().lower()
        for token in configured.replace(";", ",").split(",")
        if token.strip()
    }
    if not alert or not tokens:
        return False
    haystack = f"{getattr(alert, 'id', '') or ''} {getattr(alert, 'label', '') or ''}".lower()
    return any(token and token in haystack for token in tokens)


def _candidate_to_metadata(
    candidate: TranscriptionCandidate,
    *,
    cross_signals: dict[str, dict[str, Any]],
    judge_results: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Serializa um candidato (+ sinais cruzados e veredito do judge) para os metadados.

    Esse payload é persistido junto da auditoria e exibido na UI de revisão
    para explicar POR QUE a engine vencedora foi escolhida.
    """
    related_signals = {
        key: value
        for key, value in cross_signals.items()
        if candidate.candidate_id in key.split("__")
    }
    payload: dict[str, Any] = {
        "candidate_id": candidate.candidate_id,
        "provider": candidate.provider,
        "segments": candidate.segments,
        "deterministic_score": candidate.deterministic_score,
        "status": candidate.status,
        "provider_metadata": candidate.provider_metadata,
        "quality_flags": candidate.quality_flags,
        "cross_signals": related_signals,
        "error": candidate.error,
        "elapsed_seconds": candidate.elapsed_seconds,
    }
    judge_entry = (judge_results or {}).get(candidate.candidate_id)
    if isinstance(judge_entry, dict):
        if "score" in judge_entry:
            payload["judge_score"] = judge_entry.get("score")
        if "reason" in judge_entry:
            payload["judge_reason"] = judge_entry.get("reason")
    return payload


# ── Parsing de tempo e falante dos payloads Azure STT ───────────────────────
# As variantes da API Azure (Fast REST, SDK, batch) divergem em nomes de campo
# e unidades (ms, ticks de 100ns, segundos, ISO-8601, "MM:SS"). Estes helpers
# normalizam tudo para milissegundos/segundos sem lançar exceção.

def parse_iso_duration(duration_str) -> float:
    """Converte duração em segundos a partir de ISO-8601 (PT1M5S), "HH:MM:SS" ou número.

    Tolerante: entrada inválida retorna 0.0 (nunca lança) — timestamps ruins
    não podem derrubar a transcrição inteira.
    """
    if duration_str is None:
        return 0.0
    if isinstance(duration_str, (int, float)):
        return float(duration_str)

    raw = str(duration_str).strip().upper()
    if not raw:
        return 0.0

    match = re.match(r"^PT(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?$", raw)
    if match:
        hours = float(match.group(1) or 0.0)
        minutes = float(match.group(2) or 0.0)
        seconds = float(match.group(3) or 0.0)
        return hours * 3600.0 + minutes * 60.0 + seconds

    if ":" in raw:
        parts = raw.split(":")
        try:
            if len(parts) == 3:
                return (float(parts[0]) * 3600.0) + (float(parts[1]) * 60.0) + float(parts[2])
            if len(parts) == 2:
                return (float(parts[0]) * 60.0) + float(parts[1])
        except ValueError:
            return 0.0

    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return 0.0

def _to_milliseconds(value: Any, assume: str) -> Optional[float]:
    """Converte um valor de tempo para ms assumindo a unidade indicada.

    `assume`: "ms", "seconds", "ticks" (100ns do Azure) ou "auto"
    (heurística por magnitude para payloads de unidade desconhecida).
    """
    numeric = _parse_float(value)
    if numeric is None and isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        as_seconds = parse_iso_duration(text_value)
        if assume in ("seconds", "auto"):
            return max(0.0, as_seconds * 1000.0)
        if assume == "ms":
            return max(0.0, as_seconds)
        if assume == "ticks":
            return max(0.0, as_seconds / 10_000.0)
        return None

    if numeric is None:
        return None

    numeric = max(0.0, numeric)
    if assume == "seconds":
        return numeric * 1000.0
    if assume == "ticks":
        return numeric / 10_000.0
    if assume == "ms":
        return numeric

    # Modo auto: tolera unidades mistas vindas das diferentes variantes da API
    # Azure STT (>=1e8 só faz sentido como ticks; <=600 só como segundos).
    if numeric >= 100_000_000:
        return numeric / 10_000.0
    if numeric <= 600:
        return numeric * 1000.0
    if numeric <= 12 * 60 * 60 * 1000:
        return numeric
    return numeric / 10_000.0
def _normalize_speaker_id(raw_speaker: Any) -> int:
    """Extrai o id numérico do falante ("Guest-1", "speaker 2", 3...); -1 = desconhecido."""
    if raw_speaker is None or isinstance(raw_speaker, bool):
        return -1
    if isinstance(raw_speaker, int):
        return raw_speaker
    if isinstance(raw_speaker, float):
        return int(raw_speaker)

    text = str(raw_speaker).strip()
    if not text:
        return -1

    if re.match(r"^-?\d+$", text):
        try:
            return int(text)
        except ValueError:
            return -1

    match = re.search(r"(\d+)$", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return -1
    return -1
def _extract_phrase_text(phrase: dict) -> str:
    """Texto de uma frase do payload Azure (text/display/lexical, com fallback em nBest)."""
    text = str(phrase.get("text") or phrase.get("display") or phrase.get("lexical") or "").strip()
    if text:
        return text

    nbest = phrase.get("nBest") or phrase.get("NBest")
    if isinstance(nbest, list):
        for item in nbest:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("display") or item.get("lexical") or item.get("itn") or "").strip()
            if candidate:
                return candidate
    return ""
def _extract_phrase_timing_ms(phrase: dict) -> tuple[float, float]:
    """Resolve (offset_ms, duration_ms) de uma frase testando os aliases de campo conhecidos.

    Cada variante da API usa um nome/unidade diferente (offsetMilliseconds,
    offsetInTicks, start...); a primeira fonte que parsear vence. Sem duração
    explícita, deriva de end - start. Nunca retorna negativo.
    """
    offset_ms = None
    duration_ms = None

    offset_sources = (
        ("offsetMilliseconds", "ms"),
        ("offsetInMilliseconds", "ms"),
        ("offsetInTicks", "ticks"),
        ("offsetTicks", "ticks"),
        ("offset", "auto"),
        ("startSeconds", "seconds"),
        ("start", "seconds"),
        ("startTime", "seconds"),
        ("start_time", "seconds"),
    )
    duration_sources = (
        ("durationMilliseconds", "ms"),
        ("durationInMilliseconds", "ms"),
        ("durationInTicks", "ticks"),
        ("durationTicks", "ticks"),
        ("duration", "auto"),
        ("durationSeconds", "seconds"),
    )
    end_sources = (
        ("end", "seconds"),
        ("endSeconds", "seconds"),
        ("endTime", "seconds"),
        ("end_time", "seconds"),
    )

    for key, assume in offset_sources:
        if key in phrase:
            parsed = _to_milliseconds(phrase.get(key), assume)
            if parsed is not None:
                offset_ms = parsed
                break

    for key, assume in duration_sources:
        if key in phrase:
            parsed = _to_milliseconds(phrase.get(key), assume)
            if parsed is not None:
                duration_ms = parsed
                break

    if duration_ms is None:
        end_ms = None
        for key, assume in end_sources:
            if key in phrase:
                parsed = _to_milliseconds(phrase.get(key), assume)
                if parsed is not None:
                    end_ms = parsed
                    break
        if end_ms is not None and offset_ms is not None:
            duration_ms = max(0.0, end_ms - offset_ms)

    if offset_ms is None:
        offset_ms = 0.0
    if duration_ms is None:
        duration_ms = 0.0

    return (max(0.0, offset_ms), max(0.0, duration_ms))
# ── Filtros anti-alucinação de segmentos Whisper ─────────────────────────────
# Whisper alucina em silêncio/URA (lição da v1.2.x): estes filtros descartam ou
# substituem por "[Inaudível]" segmentos com métricas típicas de alucinação.

def _transcription_looks_valid(segments: list[dict]) -> bool:
    """Wrapper do validador do orchestrator (mantido aqui p/ testes legados)."""
    return transcription_looks_valid(segments, normalize_text_for_dedupe)
def _score_transcription_segments(segments: list[dict]) -> int:
    """Wrapper do scorer de texto do orchestrator (mantido aqui p/ testes legados)."""
    return score_transcription_segments(segments)
def _should_discard_whisper_segment(
    texto_normalizado: str,
    no_speech_prob: float,
    avg_logprob: float,
    compression_ratio: float,
    duracao_seconds: float,
    start_seconds: float,
) -> bool:
    """Decide DESCARTAR um segmento Whisper (alucinação óbvia ou lixo).

    Usa as métricas nativas do Whisper (no_speech_prob, avg_logprob,
    compression_ratio). Os 2 primeiros segundos da ligação são poupados
    (saudação curta é legítima, mesmo com métricas ruins).
    """
    if not texto_normalizado:
        return True

    if no_speech_prob >= 0.95 and avg_logprob <= -1.0:
        return True

    if "legendas" in texto_normalizado or "www." in texto_normalizado:
        return True

    if start_seconds <= 2.0:
        return False

    if duracao_seconds <= 0.35 and no_speech_prob >= 0.95:
        return True

    if compression_ratio >= 2.8 and avg_logprob <= -0.70 and duracao_seconds <= 1.20:
        return True

    return False
def _should_replace_whisper_segment_with_inaudivel(
    texto_normalizado: str,
    no_speech_prob: float,
    avg_logprob: float,
    compression_ratio: float,
    duracao_seconds: float,
) -> bool:
    """Decide trocar o texto do segmento Whisper pelo marcador "[Inaudível]".

    Diferente do descarte: o turno EXISTE no áudio, mas o texto não é
    confiável — preservar o turno mantém a estrutura da conversa para o
    auditor. Inclui frases-alucinação conhecidas observadas em produção.
    """
    if not texto_normalizado:
        return False

    if "inaudivel" in texto_normalizado:
        return False

    if texto_normalizado in {"eu falo com voce", "falo com voce", "falo com vc", "eu falo com vc", "antonio", "antônio"}:
        return True

    # Trechos com alta chance de nao-fala e baixa confianca devem virar marcador explicito.
    if no_speech_prob >= 0.60 and duracao_seconds >= 0.6:
        return True

    # Alucinacoes tipicas do Whisper em audio ruidoso: texto curto + compressao alta.
    token_count = len(texto_normalizado.split())
    if token_count <= 6 and no_speech_prob >= 0.40 and compression_ratio >= 2.0:
        return True

    if avg_logprob <= -0.9 and duracao_seconds >= 0.6:
        return True

    return False

# ── Wrappers dos providers (toda chamada aqui é PAGA) ───────────────────────
# Os providers reais vivem em transcription_providers/; estes wrappers apenas
# injetam as dependências deste módulo (filtros, parsing, prompts) e mantêm a
# assinatura histórica usada por serviços e testes.

def transcribe_audio_azure(
    audio_file: bytes,
    operator_label: str,
    driver_label: str,
    operator_name: Optional[str] = None,
    driver_name: Optional[str] = None,
    mime_type: str = "audio/wav",
    endpoint_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    sector_id: Optional[str] = None,
) -> list[dict]:
    """Transcreve via Azure (Fast Transcription ou Whisper, conforme endpoint).

    CUSTO: 1 chamada paga por execução. Sem overrides usa o endpoint Speech
    (Fast Transcription, categoria `transcricao_fast`); com
    endpoint/api_key_override aponta para o deployment Whisper
    (`transcricao_whisper`). Retorna segmentos diarizados já filtrados
    (anti-alucinação, dedupe, correções fonéticas).
    """
    dependencies = AzureTranscriptionDependencies(
        text_corrections_config=TEXT_CORRECTIONS_CONFIG,
        guess_audio_filename=_guess_audio_filename,
        get_transcription_timeout_seconds=_get_transcription_timeout_seconds,
        get_whisper_temperature=_get_whisper_temperature,
        get_whisper_prompt=_resolve_whisper_prompt,
        normalize_company_name=normalize_company_name,
        filter_hallucinations=filter_hallucinations,
        remove_emojis=remove_emojis,
        parse_iso_duration=parse_iso_duration,
        parse_float=_parse_float,
        should_discard_whisper_segment=_should_discard_whisper_segment,
        should_replace_whisper_segment_with_inaudivel=_should_replace_whisper_segment_with_inaudivel,
        extract_phrase_text=_extract_phrase_text,
        extract_phrase_timing_ms=_extract_phrase_timing_ms,
        normalize_speaker_id=_normalize_speaker_id,
        deduplicate_transcription_segments=deduplicate_transcription_segments,
    )
    return run_azure_transcription(
        audio_file,
        operator_label,
        driver_label,
        operator_name,
        driver_name,
        mime_type=mime_type,
        endpoint_override=endpoint_override,
        api_key_override=api_key_override,
        sector_id=sector_id,
        dependencies=dependencies,
    )
def transcribe_audio_assemblyai(
    audio_file: bytes,
    mime_type: str,
    operator_label: str,
    driver_label: str,
    operator_name: Optional[str] = None,
    driver_name: Optional[str] = None,
) -> list[dict]:
    """Stub do provider AssemblyAI (REMOVIDO do projeto): sempre lança RuntimeError.

    Mantido apenas para que chamadas legadas falhem com mensagem clara em vez
    de AttributeError.
    """
    raise RuntimeError(
        "AssemblyAI transcription provider was removed from this project. "
        "Use the Azure Speech, Azure Whisper, or GPT-4o diarize paths."
    )


def _build_azure_merge_client(endpoint: str, api_key: str) -> Any:
    """Cria o cliente Azure OpenAI usado na fusão hybrid_dual (timeout 180s)."""
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-06-01",
        timeout=180.0,
    )


def transcribe_audio_gpt4o_diarize(
    audio_file: bytes,
    mime_type: str,
    operator_label: str,
    driver_label: str,
    *,
    endpoint_override: Optional[str] = None,
    api_key_override: Optional[str] = None,
    operator_name: Optional[str] = None,
    driver_name: Optional[str] = None,
) -> list[dict]:
    """Transcreve com diarização nativa via GPT-4o-transcribe-diarize.

    CUSTO: 1+ chamadas pagas ao Azure OpenAI (categoria `transcricao_diarize`);
    o provider faz retry interno (AZURE_GPT4O_DIARIZE_RETRY_*), então o pior
    caso multiplica o custo. É o engine mais caro por minuto de áudio — usado
    como fallback do fast ou como primário via smart routing/setores
    configurados. Retorna segmentos com prefixo de falante já normalizado.
    """
    endpoint = (endpoint_override or "").strip()
    api_key = (api_key_override or "").strip()
    if not endpoint or not api_key:
        endpoint, api_key = _resolve_azure_gpt4o_diarize_config()
    auth_mode = _get_azure_gpt4o_diarize_auth_mode(endpoint)
    model_name = _get_azure_gpt4o_diarize_model_name()
    dependencies = GPT4oDiarizeTranscriptionDependencies(
        guess_audio_filename=_guess_audio_filename,
        get_transcription_timeout_seconds=_get_transcription_timeout_seconds,
        get_retry_count=_get_gpt4o_diarize_retry_count,
        get_retry_delay_seconds=_get_gpt4o_diarize_retry_delay_seconds,
        build_domain_prompt=lambda op_name, drv_name: build_transcription_domain_prompt(
            TEXT_CORRECTIONS_CONFIG,
            op_name,
            drv_name,
        ),
        normalize_company_name=normalize_company_name,
        filter_hallucinations=filter_hallucinations,
        remove_emojis=remove_emojis,
        deduplicate_transcription_segments=deduplicate_transcription_segments,
        sleep=time.sleep,
    )
    return run_gpt4o_diarize_transcription(
        audio_file,
        mime_type,
        operator_label,
        driver_label,
        endpoint=endpoint or "",
        api_key=api_key or "",
        auth_mode=auth_mode,
        model_name=model_name,
        operator_name=operator_name,
        driver_name=driver_name,
        dependencies=dependencies,
    )
# ── Fusão hybrid_dual (LEGADO opt-in — não recomendar) ──────────────────────

async def merge_transcriptions_with_gpt4o(
    diarized_segments: list[dict],
    accurate_text: str,
    operator_label: str,
    driver_label: str,
    *,
    client: Any = None,
    azure_endpoint: Optional[str] = None,
    azure_key: Optional[str] = None,
    azure_deployment: Optional[str] = None,
    domain_prompt: Optional[str] = None,
    json_parser: Callable[[str, str], Any] = parse_json_with_repair,
) -> tuple[list[dict], str]:
    """Usa GPT-4o para fundir a estrutura do Diarize com a precisão do Whisper.

    CUSTO: 1 chamada paga ao Azure OpenAI GPT-4o (categoria
    `merge_hybrid_dual` no cost_guard). Só roda no engine legado hybrid_dual.

    Retorna (segments, merge_status) onde merge_status é:
      - "merged":   fusão GPT-4o concluída com sucesso
      - "no_credentials": faltou Azure OpenAI config; devolve diarized puro
      - "merge_failed":   exceção na fusão; devolve diarized puro
      - "merge_rejected_diagnostics": fusão respondeu mas alterou estrutura/
        timestamps/falantes ou perdeu/inventou número do Whisper; devolve
        diarized puro (proteção de integridade da evidência)
    """
    from core import config as core_config

    effective_endpoint = core_config.AZURE_OPENAI_ENDPOINT if azure_endpoint is None else azure_endpoint
    effective_key = core_config.AZURE_OPENAI_KEY if azure_key is None else azure_key
    effective_deployment = azure_deployment or core_config.AZURE_OPENAI_DEPLOYMENT

    if client is None and (not effective_endpoint or not effective_key):
        logger.warning("Credenciais Azure OpenAI nao encontradas para fusao. Retornando diarizacao pura.")
        return diarized_segments, "no_credentials"

    merge_client = client or _build_azure_merge_client(effective_endpoint, effective_key)

    diarized_json = json.dumps(diarized_segments, ensure_ascii=False)
    domain_context = domain_prompt or build_transcription_domain_prompt(TEXT_CORRECTIONS_CONFIG)
    
    prompt = f"""Voce e um especialista em fusao de transcricoes de audio.
Recebi duas versoes da mesma ligacao:
1. VERSAO A (Diarizada): Possui a divisao correta de quem fala ({operator_label} vs {driver_label}), mas pode ter erros de digitacao ou termos omitidos.
2. VERSAO B (Whisper): Texto corrido altamente preciso, especialmente para numeros (senhas, CPFs) e termos tecnicos, mas NAO tem divisao de falantes.

CONTEXTO DE DOMINIO:
{domain_context}

TAREFA:
Gere uma nova VERSAO FINAL em formato JSON (objeto contendo a chave 'transcription' que e uma lista de objetos com 'start', 'end', 'text') que:
- Mantenha RIGOROSAMENTE a estrutura de turnos e timestamps da VERSAO A.
- Corrija o conteudo do campo 'text' usando a precisao da VERSAO B.
- Garanta que TODOS os numeros (senhas, CPFs, placas, RGs) detectados na VERSAO B sejam COPIADOS EXATAMENTE COMO ESTAO para a VERSAO A. ESTRITAMENTE PROIBIDO alterar, arredondar ou "corrigir" qualquer numero. Se a VERSAO B diz 09055405655, mantenha 09055405655.
- Mantenha os prefixos "{operator_label}:" e "{driver_label}:" em cada segmento.
- Se não conseguir identificar claramente alguma palavra ou trecho da fala, utilize EXCLUSIVAMENTE a marcação '[Inaudível]'. É ESTRITAMENTE PROIBIDO inventar, deduzir ou adivinhar palavras isoladas que não estejam perfeitamente audíveis.
- Se houver duvida ou conflito entre as versoes, seja conservador: preserve a estrutura da VERSAO A e não invente palavras, numeros ou falantes.

Exemplo de formato:
{{
  "transcription": [
    {{ "start": "00:00", "end": "00:05", "text": "Operador: Ola" }},
    ...
  ]
}}

VERSAO A (Diarizada):
{diarized_json}

VERSAO B (Whisper):
{accurate_text}

Retorne APENAS o JSON final resultante."""

    try:
        from core import cost_guard
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "merge_hybrid_dual")
        response = await asyncio.to_thread(
            merge_client.chat.completions.create,
            model=effective_deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        text = response.choices[0].message.content
        data = await asyncio.to_thread(json_parser, text, diarized_json)
        merged = extract_transcription(data)
        merged = _preserve_diarization_metadata(merged, diarized_segments)
        logger.info("Fusao concluida: %d segmentos gerados.", len(merged))
        if not merged:
            return diarized_segments, "merge_failed"
        structure_check = _validate_merged_structure(merged, diarized_segments)
        if structure_check.get("has_diagnostics"):
            logger.info(
                "Diagnostico interno da fusao: alteracao estrutural/timestamp/falante detectada: %s",
                structure_check.get("issues"),
            )
        evidence_check = _validate_merged_evidence(merged, accurate_text, diarized_segments)
        if evidence_check.get("has_diagnostics"):
            logger.info(
                "Diagnostico interno da fusao: motivos=%s missing=%s unexpected=%s "
                "source_only=%s accurate_only=%s conflict=%s",
                evidence_check.get("diagnostic_reasons"),
                evidence_check.get("missing_numeric_sequences"),
                evidence_check.get("unexpected_numeric_sequences"),
                evidence_check.get("source_only_numeric_sequences"),
                evidence_check.get("accurate_only_numeric_sequences"),
                evidence_check.get("numeric_conflict_between_sources"),
            )

        if structure_check.get("has_diagnostics") or evidence_check.get("is_blocking"):
            logger.warning("Merge GPT-4o rejeitado por seguranca de integridade (estrutura alterada ou numero do whisper perdido/alucinado).")
            return diarized_segments, "merge_rejected_diagnostics"

        return merged, "merged"
    except Exception as exc:
        logger.error("Falha ao fundir transcricoes: %s", exc)
        return diarized_segments, "merge_failed"

# ── Orquestrador principal ───────────────────────────────────────────────────

async def transcribe_audio(
    audio_file: bytes,
    mime_type: str,
    operator_name: Optional[str],
    driver_name: Optional[str],
    alert: Optional[AuditAlert] = None,
    sector_id: Optional[str] = None,
    return_metadata: bool = False,
    allow_degraded_hybrid_fallback: bool = False,
    audio_quality_score: Optional[float] = None,
) -> list[dict] | tuple[list[dict], dict[str, Any]]:
    """Ponto de entrada da transcrição: roda a cadeia de engines e escolhe o resultado.

    Fluxo (rota Azure, a padrão em produção):
    1. Normaliza MIME e prepara o áudio (conversão/compressão se necessário).
    2. Resolve o engine via AZURE_TRANSCRIPTION_ENGINE (default `fast`) e
       monta a ordem de execução — fallback fast → whisper → gpt4o_diarize →
       sdk, condicionado às flags AZURE_*_FALLBACK e credenciais disponíveis.
    3. Executa cada estratégia com timeout; cada resultado vira um candidato
       pontuado. Com o selector LIGADO (default), a decisão final é do
       `transcription_selector` (+ judge GPT-4o no empate); desligado, o
       primeiro candidato aceitável vence.
    4. `hybrid_dual` (LEGADO opt-in) roda Diarize+Whisper em paralelo e funde
       via GPT-4o; em modo estrito não degrada silenciosamente.

    Parâmetros-chave:
    - `alert`/`sector_id`: roteiam smart routing e endurecem gates p/ alertas
      críticos; também definem o rótulo do interlocutor (Motorista etc.).
    - `return_metadata`: True devolve (segments, metadata) com candidatos,
      attempts, decisão do selector e judge — persistido p/ auditoria da escolha.
    - `allow_degraded_hybrid_fallback`: True (fluxo MANUAL) entrega o melhor
      candidato mesmo reprovado pelo selector, p/ o auditor corrigir na tela;
      False (automação) lança RuntimeError e o item vai p/ revisão.
    - `audio_quality_score`: score do QualityAnalyzer, repassado aos gates.

    CUSTO: cada estratégia executada é uma chamada paga (Speech/Whisper/
    GPT-4o); selector/judge podem somar mais 1 chamada GPT-4o. A rota
    não-Azure (Gemini, só quando AI_PROVIDER_PRIORITY != azure) também é paga.

    Levanta RuntimeError quando todas as estratégias falham, quando o selector
    exige revisão manual (automação) ou quando não há provider configurado.
    """
    operator_label = "Operador"
    driver_label = infer_interlocutor_label(alert, driver_name)
    diarization_reference = build_diarization_reference(driver_label)
    gpt4o_diarize_endpoint, gpt4o_diarize_key = _resolve_azure_gpt4o_diarize_config() if AI_PROVIDER_PRIORITY == "azure" else (None, None)

    # ── Stereo Split (Canais Separados) ──────────────────────────────────────────
    # Se o áudio original possui 2 canais (estéreo), aplicamos uma técnica de divisão
    # física de canais em vez de depender da diarização acústica por IA, que falha
    # frequentemente em cenários de interrupção mútua (overlap) e trocas rápidas de turno.
    # Como as chamadas telefônicas da telefonia Huawei AICC gravam o operador (agente) no canal esquerdo
    # e o motorista/cliente no canal direito, a separação dos canais é 100% precisa.
    stereo_splits = await asyncio.to_thread(split_stereo_audio, audio_file)
    if stereo_splits is not None:
        left_audio, right_audio = stereo_splits
        logger.info("[Transcription] Audio estereo detectado. Iniciando processamento Stereo Split.")

        # Dispara a transcrição recursiva de cada canal individualmente em paralelo.
        # Por receberem áudios mono (gerados pelo split_stereo_audio), as chamadas recursivas
        # NÃO acionarão o bloco de split estéreo novamente, evitando recursão infinita.
        left_task = transcribe_audio(
            left_audio,
            "audio/wav",
            operator_name,
            driver_name,
            alert,
            sector_id,
            return_metadata=True,
            allow_degraded_hybrid_fallback=allow_degraded_hybrid_fallback,
            audio_quality_score=audio_quality_score,
        )
        right_task = transcribe_audio(
            right_audio,
            "audio/wav",
            operator_name,
            driver_name,
            alert,
            sector_id,
            return_metadata=True,
            allow_degraded_hybrid_fallback=allow_degraded_hybrid_fallback,
            audio_quality_score=audio_quality_score,
        )

        left_res, right_res = await asyncio.gather(left_task, right_task)

        # Extrai os segmentos textuais e metadados de cada canal
        left_segments = left_res[0] if isinstance(left_res, tuple) else left_res
        right_segments = right_res[0] if isinstance(right_res, tuple) else right_res

        left_meta = left_res[1] if isinstance(left_res, tuple) else {}
        right_meta = right_res[1] if isinstance(right_res, tuple) else {}

        # Expressão regular para limpar qualquer prefixo de speaker incorreto ou inconsistente
        # que o ASR possa ter gerado individualmente nos canais mono (ex: "Condutor:", "Motorista:")
        clean_speaker_pattern = re.compile(
            r"^(?:Operador|Motorista|Telefonia|Cliente|Policia|Atendente|Bas|Vitima|Declarante|Condutor|Speaker\s+\d+):\s*",
            re.IGNORECASE
        )

        # Formata as falas do canal esquerdo (Canal 0) e as atribui compulsoriamente ao Operador.
        # A confiança da diarização é definida como 1.0 (máxima) e o risco de troca como baixo ("low"),
        # dado que o canal físico é estritamente isolado e pertence apenas a um locutor.
        left_formatted = []
        for seg in left_segments:
            raw_text = seg.get("text", "")
            text_clean = clean_speaker_pattern.sub("", raw_text).strip()
            if not text_clean:
                continue
            left_formatted.append({
                **seg,
                "text": f"{operator_label}: {text_clean}",
                "speaker_source_ids": [0],
                "speaker_persona_ids": [0],
                "speaker_confidence": 1.0,
                "speaker_risk": "low",
                "speaker_ambiguous": False
            })

        # Formata as falas do canal direito (Canal 1) e as atribui compulsoriamente ao Motorista / Interlocutor.
        right_formatted = []
        for seg in right_segments:
            raw_text = seg.get("text", "")
            text_clean = clean_speaker_pattern.sub("", raw_text).strip()
            if not text_clean:
                continue
            right_formatted.append({
                **seg,
                "text": f"{driver_label}: {text_clean}",
                "speaker_source_ids": [1],
                "speaker_persona_ids": [1],
                "speaker_confidence": 1.0,
                "speaker_risk": "low",
                "speaker_ambiguous": False
            })

        # Função auxiliar para converter strings de timestamp (ex: "MM:SS.mmm") em segundos
        # para permitir a ordenação temporal exata de ambos os canais de forma unificada.
        def parse_ts_to_seconds(ts_str: str) -> float:
            try:
                parts = ts_str.split(':')
                if len(parts) == 2:
                    return float(parts[0]) * 60 + float(parts[1])
                elif len(parts) == 3:
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            except Exception:
                pass
            return 0.0

        # Une as listas de segmentos do operador e do motorista, e as ordena cronologicamente
        combined = left_formatted + right_formatted
        combined.sort(key=lambda s: parse_ts_to_seconds(s.get("start", "00:00")))

        from datetime import timedelta
        from audio.speaker_models import SegmentoFormatado
        from audio.speaker_identification import mesclar_segmentos_consecutivos
        from audio.speaker_detection import SpeakerDetectionService

        # Converte os dicionários ordenados para objetos SegmentoFormatado para podermos
        # reaproveitar a lógica pura e otimizada de agrupamento do pipeline principal.
        formatados = []
        for seg in combined:
            raw_text = seg.get("text", "")
            # Limpa prefixos dinâmicos baseando-se no primeiro caractere ":"
            if ":" in raw_text:
                text_clean = raw_text.split(":", 1)[1].strip()
            else:
                text_clean = raw_text.strip()
            start_sec = parse_ts_to_seconds(seg.get("start", "00:00"))
            end_sec = parse_ts_to_seconds(seg.get("end", "00:00"))
            duration = max(0.0, end_sec - start_sec)

            formatados.append(SegmentoFormatado(
                timestamp=timedelta(seconds=start_sec),
                speaker=operator_label if seg.get("speaker_source_ids") == [0] else driver_label,
                texto=text_clean,
                texto_normalizado=SpeakerDetectionService.normalizar_texto(text_clean),
                duracao_seconds=duration,
                source_speaker_ids=tuple(seg.get("speaker_source_ids", [])),
                persona_speaker_ids=tuple(seg.get("speaker_persona_ids", [])),
                speaker_confidence=seg.get("speaker_confidence", 1.0),
                diarization_risk=seg.get("speaker_risk", "low"),
                diarization_ambiguous=seg.get("speaker_ambiguous", False)
            ))

        # Funde turnos vizinhos da mesma pessoa que estejam separados por pausas muito curtas
        mesclados = mesclar_segmentos_consecutivos(formatados)

        # Reconstrói a lista final de segmentos formatados no formato aceito downstream pela auditoria
        final_segments = []
        for segment in mesclados:
            if not segment.texto or not segment.texto.strip():
                continue
            is_telephony = SpeakerDetectionService.eh_segmento_telefonia(segment.texto_normalizado)
            speaker_label = "Telefonia" if is_telephony else segment.speaker
            final_segments.append(
                {
                    "start": SpeakerDetectionService.formatar_timestamp(segment.timestamp),
                    "end": SpeakerDetectionService.formatar_timestamp(
                        segment.timestamp + timedelta(seconds=segment.duracao_seconds)
                    ),
                    "text": f"{speaker_label}: {segment.texto}",
                    "speaker_source_ids": list(segment.source_speaker_ids),
                    "speaker_persona_ids": list(segment.persona_speaker_ids),
                    "speaker_confidence": round(segment.speaker_confidence, 3),
                    "speaker_risk": "low" if is_telephony else segment.diarization_risk,
                    "speaker_ambiguous": False if is_telephony else segment.diarization_ambiguous,
                }
            )

        # Retorna o resultado enriquecido com os metadados do Stereo Split se solicitado
        if return_metadata:
            merged_metadata = {
                "stereo_split": True,
                "left_channel": left_meta,
                "right_channel": right_meta,
                "selected_strategy": "stereo_split_dual_channel",
                "selected_provider": "Stereo Split (Left: Agent / Right: Client)"
            }
            return final_segments, merged_metadata
        return final_segments

    if sentry_sdk:
        sentry_sdk.add_breadcrumb(
            category="transcription",
            message=f"Iniciando transcrição de áudio ({mime_type})",
            data={
                "operator_label": operator_label,
                "driver_label": driver_label,
                "sector_id": sector_id,
            },
            level="info"
        )

    # Prioridade de provider: rota Azure só quando há credencial de pelo menos
    # um engine (Speech ou GPT-4o diarize); senão cai na rota da IA primária.
    if AI_PROVIDER_PRIORITY == "azure" and (
        AZURE_SPEECH_KEY
        or bool(gpt4o_diarize_endpoint and gpt4o_diarize_key)
    ):
        normalized_mime_type = detect_audio_mime_type(audio_file, mime_type)
        prepared_audio = await asyncio.to_thread(
            prepare_audio_for_azure,
            audio_file,
            normalized_mime_type,
            preprocess_enabled=_env_flag("AZURE_PREPROCESS_ENABLED", True),
            should_preprocess_audio=_should_preprocess_audio_for_azure,
            convert_to_mp3=lambda payload, source_mime: convert_audio_to_mp3(payload, source_mime_type=source_mime),
            convert_to_wav=convert_audio_to_wav,
            accepted_mime_types=AZURE_ACCEPTED_MIME,
        )
        azure_audio = prepared_audio.audio_file
        azure_mime = detect_audio_mime_type(prepared_audio.audio_file, prepared_audio.mime_type)

        gpt4o_diarize_available = bool(gpt4o_diarize_endpoint and gpt4o_diarize_key)
        
        # Engine Selection
        env_engine = _resolve_transcription_engine(os.getenv("AZURE_TRANSCRIPTION_ENGINE", "fast"))
        allow_smart_engine_routing = env_engine in {"auto", "smart"}
        prefer_gpt4o_primary = False
        if allow_smart_engine_routing:
            prefer_gpt4o_primary = await asyncio.to_thread(
                _should_use_gpt4o_diarize_as_primary_for_audio,
                azure_audio,
                azure_mime,
                alert,
                sector_id,
                operator_label,
                driver_label,
                gpt4o_diarize_available=gpt4o_diarize_available,
            )

        strict_hybrid_dual = _env_flag("AZURE_TRANSCRIPTION_STRICT_HYBRID_DUAL", True)
        block_degraded_hybrid = strict_hybrid_dual and not allow_degraded_hybrid_fallback

        # Provider routing. Explicit engines are respected. Smart routing only
        # applies to the opt-in auto/smart engine, so the default fast path is
        # not promoted to GPT-4o before Azure Fast Transcription runs.
        if strict_hybrid_dual and env_engine == "hybrid_dual":
            engine = "hybrid_dual"
        elif allow_smart_engine_routing:
            engine = "gpt4o_diarize" if prefer_gpt4o_primary else "fast"
        else:
            engine = env_engine
        
        allow_sdk_fallback = _env_flag("AZURE_SDK_FALLBACK", True)

        # 2026-06-30: revertido o corte de 10/06 que deixou o `fast` sem rede de
        # seguranca e degradou a qualidade (alucinacoes + troca de interlocutor).
        # Volta o fallback premium ao padrao LIGADO (estado pre-10/06): o `fast`
        # roda primeiro e so aciona Whisper/GPT-4o Diarize quando o resultado sai
        # ruim (diarizacao fraca / risco de troca alto); o selector escolhe o
        # melhor candidato. Continua desligavel por env
        # (AZURE_PREMIUM_TRANSCRIPTION_FALLBACK=false) se o custo Azure apertar;
        # o teto diario de custo (v1.3.114) segue protegendo contra estouro.
        premium_fallback_enabled = _env_flag("AZURE_PREMIUM_TRANSCRIPTION_FALLBACK", True)
        allow_whisper_fallback = (
            engine in {"hybrid_dual", "whisper"}
            or premium_fallback_enabled
            or _env_flag("AZURE_WHISPER_FALLBACK", False)
        )
        allow_gpt4o_diarize_fallback = (
            engine in {"hybrid_dual", "gpt4o_diarize"}
            or premium_fallback_enabled
            or _env_flag("AZURE_GPT4O_DIARIZE_FALLBACK", False)
        )
        whisper_endpoint, whisper_key = _resolve_azure_whisper_config()
        whisper_available = bool(whisper_endpoint and whisper_key)

        def run_fast() -> list[dict]:
            """Azure Fast Transcription (engine default). 1 chamada paga ao Speech."""
            if not os.getenv("AZURE_SPEECH_ENDPOINT"):
                raise RuntimeError("AZURE_SPEECH_ENDPOINT nao configurado para Fast Transcription")
            return transcribe_audio_azure(
                azure_audio,
                operator_label,
                driver_label,
                operator_name,
                driver_name,
                mime_type=azure_mime,
                sector_id=sector_id,
            )

        def run_whisper() -> list[dict]:
            """Azure Whisper (endpoint próprio). 1 chamada paga; nunca usar isolado p/ telefonia (alucina em silêncio)."""
            if not whisper_available:
                raise RuntimeError("Azure Whisper nao configurado para fallback")
            return transcribe_audio_azure(
                azure_audio,
                operator_label,
                driver_label,
                operator_name,
                driver_name,
                mime_type=azure_mime,
                endpoint_override=whisper_endpoint,
                api_key_override=whisper_key,
                sector_id=sector_id,
            )

        def run_gpt4o_diarize() -> list[dict]:
            """GPT-4o-transcribe-diarize (diarização nativa). 1 chamada paga ao OpenAI."""
            if not gpt4o_diarize_available:
                raise RuntimeError("GPT-4o-transcribe-diarize nao configurado para fallback")
            return transcribe_audio_gpt4o_diarize(
                azure_audio,
                azure_mime,
                operator_label,
                driver_label,
                endpoint_override=gpt4o_diarize_endpoint,
                api_key_override=gpt4o_diarize_key,
                operator_name=operator_name,
                driver_name=driver_name,
            )

        def run_sdk() -> list[dict]:
            """Speech SDK ConversationTranscriber — last resort da cadeia (texto pior em telefonia)."""
            from transcription_providers.speech_sdk_transcriber import transcribe_with_conversation_transcriber

            sdk_audio = azure_audio if azure_mime in WAV_MIME_TYPES else convert_audio_to_wav(azure_audio)
            return transcribe_with_conversation_transcriber(sdk_audio, operator_label, driver_label)

        hybrid_dual_operational_fallback: dict[str, Any] = {}

        async def run_hybrid_dual() -> tuple[list[dict], str]:
            """Executa Diarize e Whisper em paralelo e funde via GPT-4o.

            Sobrevive a falha parcial: se uma estrategia falhar em fluxo manual,
            usa Azure Fast Transcription como fallback operacional. Falha de
            fusao/consenso nao e fallback: bloqueia para evitar transcricao
            degradada parecer auditoria completa.
            Retorna (segments, sub_strategy) onde sub_strategy reflete o que foi
            efetivamente entregue (hybrid_dual / fast).
            """

            async def run_fast_fallback(reason: str) -> tuple[list[dict], str]:
                """Fallback operacional do hybrid_dual: registra o motivo e entrega via Fast."""
                hybrid_dual_operational_fallback.clear()
                hybrid_dual_operational_fallback.update(
                    {
                        "fallback_from": "hybrid_dual",
                        "fallback_type": "operational",
                        "fallback_reason": reason,
                    }
                )
                logger.warning(
                    "[hybrid_dual] %s; usando Azure Fast Transcription como fallback.",
                    reason,
                )
                return await asyncio.to_thread(run_fast), "fast"

            diarize_task = asyncio.to_thread(run_gpt4o_diarize)
            whisper_task = asyncio.to_thread(run_whisper)

            timeout_seconds = _get_transcription_strategy_timeout_seconds()
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(diarize_task, whisper_task, return_exceptions=True),
                    timeout=timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f"hybrid_dual excedeu {timeout_seconds}s") from exc

            diarize_res, whisper_res = results
            diarize_failed = isinstance(diarize_res, BaseException)
            whisper_failed = isinstance(whisper_res, BaseException)
            diarize_ok = not diarize_failed and bool(diarize_res)
            whisper_ok = not whisper_failed and bool(whisper_res)

            if not diarize_ok and not whisper_ok:
                primary_exc = diarize_res if isinstance(diarize_res, BaseException) else whisper_res
                if not block_degraded_hybrid and (diarize_failed or whisper_failed):
                    return await run_fast_fallback(f"Diarize e Whisper falharam ({primary_exc})")
                raise RuntimeError(f"hybrid_dual: Diarize e Whisper falharam ({primary_exc})")

            if not diarize_ok:
                if not block_degraded_hybrid and diarize_failed:
                    return await run_fast_fallback(f"Diarize falhou ({diarize_res})")
                raise RuntimeError(f"hybrid_dual: Diarize falhou em modo estrito ({diarize_res})")

            if not whisper_ok:
                if not block_degraded_hybrid and whisper_failed:
                    return await run_fast_fallback(f"Whisper falhou ({whisper_res})")
                raise RuntimeError(f"hybrid_dual: Whisper falhou em modo estrito ({whisper_res})")

            whisper_text = " ".join([s.get("text", "") for s in whisper_res])
            merged, merge_status = await merge_transcriptions_with_gpt4o(
                diarize_res,
                whisper_text,
                operator_label,
                driver_label,
                domain_prompt=build_transcription_domain_prompt(
                    TEXT_CORRECTIONS_CONFIG,
                    operator_name,
                    driver_name,
                ),
            )
            if merge_status != "merged":
                # Mesma regra dos branches de falha do Diarize/Whisper acima:
                # fluxo manual (allow_degraded_hybrid_fallback=True) degrada
                # para o Azure Fast em vez de barrar a auditoria.
                if not block_degraded_hybrid:
                    return await run_fast_fallback(f"fusao GPT-4o falhou ({merge_status})")
                raise RuntimeError(f"hybrid_dual: fusao GPT-4o falhou em modo estrito ({merge_status})")
            return merged, "hybrid_dual"

        run_order = build_strategy_order(
            engine,
            include_sdk=allow_sdk_fallback or engine == "sdk",
            include_whisper=whisper_available and (allow_whisper_fallback or engine == "whisper"),
            include_gpt4o_diarize=gpt4o_diarize_available and (allow_gpt4o_diarize_fallback or engine == "gpt4o_diarize"),
        )
        if strict_hybrid_dual and engine == "hybrid_dual":
            run_order = ["hybrid_dual"] if gpt4o_diarize_available and whisper_available else []

        async def execute_strategy_async(strategy: str) -> tuple[list[dict], str]:
            """Retorna (segments, effective_strategy).

            effective_strategy reflete o que de fato foi entregue. Em modo
            estrito, hybrid_dual so entrega hybrid_dual completo.
            """
            if strategy == "hybrid_dual":
                segments, sub_strategy = await run_hybrid_dual()
                return segments, sub_strategy
            if strategy == "sdk":
                return await asyncio.to_thread(run_sdk), "sdk"
            if strategy == "whisper":
                return await asyncio.to_thread(run_whisper), "whisper"
            if strategy == "gpt4o_diarize":
                return await asyncio.to_thread(run_gpt4o_diarize), "gpt4o_diarize"
            return await asyncio.to_thread(run_fast), "fast"

        # Bonus mantido apenas para observabilidade historica do selector.
        # Em modo hybrid_dual a ordem agora contem somente hybrid_dual, portanto
        # esse score nao pode mais eleger fast/sdk/gpt4o como fallback.
        HYBRID_DUAL_BONUS = 1500

        candidates: list[tuple[str, list[dict]]] = []
        candidate_artifacts: list[TranscriptionCandidate] = []
        attempts: list[dict[str, Any]] = []

        provider_map = {
            "hybrid_dual": "Hybrid GPT-4o + Whisper",
            "sdk": "Azure Speech SDK",
            "whisper": "Azure Whisper",
            "gpt4o_diarize": "GPT-4o-transcribe-diarize",
            "fast": "Azure Fast Transcription",
        }
        selector_enabled = _is_candidate_selector_enabled()

        async def build_selector_result() -> tuple[list[dict], dict[str, Any]]:
            """Decide o candidato vencedor entre as transcrições coletadas.

            Score determinístico primeiro; empate vai ao judge LLM (1 chamada
            paga GPT-4o, v1.3.80). Devolve (segments, metadata) com a trilha da
            decisão para `audio_quality.transcription_provider`.
            """
            cross_signals = compute_cross_signals(candidate_artifacts)
            decision = select_transcription_candidate(
                candidate_artifacts,
                cross_signals=cross_signals,
                audio_quality_score=audio_quality_score,
                critical_alert=_critical_alert_for_transcription_selector(alert),
            )
            selected = decision.selected_candidate
            judge_results: dict[str, dict[str, Any]] = {}
            judge_meta: Optional[dict[str, Any]] = None

            if decision.reason == "empate_requer_judge" and selected is not None:
                usable_ranked = sorted(
                    [c for c in candidate_artifacts if not c.has_error and c.segment_count > 0],
                    key=lambda c: float(c.deterministic_score or 0.0),
                    reverse=True,
                )
                if len(usable_ranked) >= 2:
                    top_candidate = usable_ranked[0]
                    runner_up = usable_ranked[1]
                    alert_id = (getattr(alert, "id", "") or "").strip() if alert else ""
                    alert_label = (getattr(alert, "label", "") or "").strip() if alert else ""
                    outcome = await asyncio.to_thread(
                        judge_tie_break,
                        top_candidate,
                        runner_up,
                        alert_id=alert_id,
                        alert_label=alert_label,
                        sector_id=sector_id or "",
                        operator_label=operator_label,
                        driver_label=driver_label,
                    )
                    if outcome is not None:
                        judge_meta = {
                            "winner_label": outcome.winner_label,
                            "winner_candidate_id": outcome.winner_candidate_id,
                            "confidence": outcome.confidence,
                            "reason": outcome.reason,
                            "scores": outcome.scores,
                            "hallucinations": outcome.hallucinations,
                            "pair": [top_candidate.candidate_id, runner_up.candidate_id],
                        }
                        for cid in (top_candidate.candidate_id, runner_up.candidate_id):
                            judge_results[cid] = {
                                "score": outcome.scores.get(cid),
                                "reason": outcome.reason if cid == outcome.winner_candidate_id else "",
                            }
                        if outcome.resolved and outcome.winner_candidate_id:
                            winner = next(
                                (c for c in candidate_artifacts if c.candidate_id == outcome.winner_candidate_id),
                                None,
                            )
                            if winner is not None:
                                selected = winner

            metadata = {
                "selected_strategy": selected.provider if selected else "",
                "selected_provider": provider_map.get(selected.provider, "Unknown Provider") if selected else "",
                "selected_reason": "accepted" if decision.status == DECISION_ACCEPTED else decision.reason,
                "selected_candidate_id": selected.candidate_id if selected else decision.selected_candidate_id,
                "selection_status": decision.status,
                "selection_reason": decision.reason,
                "selection_gates": decision.gates,
                "review_reasons": decision.review_reasons,
                "attempts": attempts,
                "cross_signals": cross_signals,
                "candidates": [
                    _candidate_to_metadata(candidate, cross_signals=cross_signals, judge_results=judge_results)
                    for candidate in candidate_artifacts
                ],
            }
            if selected is not None and selected.provider != "hybrid_dual" and hybrid_dual_operational_fallback:
                metadata.update(hybrid_dual_operational_fallback)
            if judge_meta is not None:
                metadata["judge"] = judge_meta
                if judge_meta["winner_candidate_id"] and selected is not None and selected.candidate_id == judge_meta["winner_candidate_id"]:
                    metadata["selected_reason"] = "judge_resolved"

            if decision.status in {DECISION_REJECTED, DECISION_MANUAL_REVIEW} or selected is None:
                if not allow_degraded_hybrid_fallback:
                    raise RuntimeError(
                        "Transcricao requer revisao manual pelo selector de candidatos "
                        f"({decision.reason})"
                    )
                # Para auditorias manuais (allow_degraded_hybrid_fallback=True), não barramos a operação.
                # Entregamos o melhor candidato para o auditor corrigir na tela.
                selected = selected or max(candidate_artifacts, key=lambda c: c.deterministic_score)
                metadata["selected_strategy"] = selected.provider
                metadata["selected_provider"] = provider_map.get(selected.provider, "Unknown Provider")
                metadata["selected_reason"] = f"manual_override_{decision.reason}"
                metadata["selected_candidate_id"] = selected.candidate_id

            return selected.segments, metadata

        def has_pending_whisper_confirmation(current_index: int) -> bool:
            """True se ainda falta rodar o Whisper como candidato de confirmação na cadeia."""
            if not selector_enabled:
                return False
            if any(candidate.provider == "whisper" for candidate in candidate_artifacts):
                return False
            return "whisper" in run_order[current_index + 1 :]

        def has_pending_diarize_confirmation(current_index: int, selection_status: str) -> bool:
            """True se vale rodar o diarize como desempate (só quando a seleção pediu revisão)."""
            if not selector_enabled or selection_status != DECISION_NEEDS_REVIEW:
                return False
            if any(candidate.provider == "gpt4o_diarize" for candidate in candidate_artifacts):
                return False
            return "gpt4o_diarize" in run_order[current_index + 1 :]

        for strategy_index, strategy in enumerate(run_order):
            strategy_started = time.monotonic()
            try:
                strategy_timeout_seconds = _get_transcription_strategy_timeout_seconds()
                logger.info(
                    "[Transcription] Tentando %s timeout=%ss",
                    strategy,
                    strategy_timeout_seconds,
                )
                result, effective_strategy = await asyncio.wait_for(
                    execute_strategy_async(strategy),
                    timeout=strategy_timeout_seconds,
                )
                result = deduplicate_transcription_segments(result)

                is_valid = _transcription_candidate_is_acceptable(result, diarization_reference)
                candidate_score = _score_transcription_candidate(result, diarization_reference)
                candidate_diarization = _build_candidate_diarization(result, diarization_reference)

                # Bonus aplicado APENAS quando a fusao real aconteceu (effective == hybrid_dual).
                if effective_strategy == "hybrid_dual":
                    candidate_score += HYBRID_DUAL_BONUS

                candidates.append((effective_strategy, result, candidate_score))
                candidate_id = f"{effective_strategy}_{len(candidate_artifacts) + 1}"
                candidate_artifacts.append(
                    build_candidate(
                        effective_strategy,
                        result,
                        candidate_id=candidate_id,
                        deterministic_score=candidate_score,
                        status="accepted" if is_valid else "insufficient",
                        provider_metadata={
                            "strategy": strategy,
                            "effective_strategy": effective_strategy,
                            "provider": provider_map.get(effective_strategy, "Unknown Provider"),
                        },
                        quality_flags={
                            "diarization": candidate_diarization,
                            "swap_risk": str(candidate_diarization.get("swap_risk") or "").strip().lower(),
                        },
                        elapsed_seconds=round(time.monotonic() - strategy_started, 3),
                    )
                )
                attempt = {
                    "strategy": strategy,
                    "effective_strategy": effective_strategy,
                    "provider": provider_map.get(effective_strategy, "Unknown Provider"),
                    "status": "accepted" if is_valid else "insufficient",
                    "score": candidate_score,
                    "candidate_id": candidate_id,
                    "elapsed_seconds": round(time.monotonic() - strategy_started, 3),
                }
                if strategy == "hybrid_dual" and effective_strategy != "hybrid_dual" and hybrid_dual_operational_fallback:
                    attempt.update(hybrid_dual_operational_fallback)
                attempts.append(attempt)

                if is_valid and not selector_enabled:
                    metadata = {
                        "selected_strategy": effective_strategy,
                        "selected_provider": provider_map.get(effective_strategy, "Unknown Provider"),
                        "selected_reason": "accepted",
                        "attempts": attempts,
                    }
                    if strategy == "hybrid_dual" and effective_strategy != "hybrid_dual" and hybrid_dual_operational_fallback:
                        metadata.update(hybrid_dual_operational_fallback)
                    return (result, metadata) if return_metadata else result
                if is_valid and selector_enabled and not has_pending_whisper_confirmation(strategy_index):
                    selected_segments, metadata = await build_selector_result()
                    if has_pending_diarize_confirmation(
                        strategy_index,
                        str(metadata.get("selection_status") or ""),
                    ):
                        logger.info(
                            "[Transcription] Selector marcou needs_review; aguardando GPT-4o diarize pendente."
                        )
                        continue
                    return (selected_segments, metadata) if return_metadata else selected_segments
            except Exception as exc:
                logger.exception("Falha na strategy %s: %s", strategy, exc)
                attempts.append({
                    "strategy": strategy,
                    "provider": provider_map.get(strategy, "Unknown Provider"),
                    "status": "error",
                    "error": str(exc),
                    "elapsed_seconds": round(time.monotonic() - strategy_started, 3),
                })

        if selector_enabled and candidate_artifacts:
            selected_segments, metadata = await build_selector_result()
            return (selected_segments, metadata) if return_metadata else selected_segments

        if candidates:
            best_strategy, best_result, _ = max(candidates, key=lambda item: item[2])
            metadata = {
                "selected_strategy": best_strategy,
                "selected_provider": provider_map.get(best_strategy, "Unknown Provider"),
                "selected_reason": "best_candidate",
                "attempts": attempts,
            }
            if best_strategy != "hybrid_dual" and hybrid_dual_operational_fallback:
                metadata.update(hybrid_dual_operational_fallback)
            return (best_result, metadata) if return_metadata else best_result

        failed_attempts = [
            f"{attempt.get('strategy')}: {attempt.get('error') or attempt.get('status')}"
            for attempt in attempts
            if isinstance(attempt, dict)
        ]
        details = " | ".join(failed_attempts)
        raise RuntimeError(
            "Falha em todos os metodos de transcricao"
            + (f" ({details})" if details else "")
        )

    if AI_PROVIDER_PRIORITY == "azure":
        raise RuntimeError(
            "AI_PROVIDER_PRIORITY=azure but no transcription provider configured (AZURE_SPEECH_*, GPT-4o diarize)"
        )

    # Default: primary AI provider (only when the Azure route is not selected)
    prompt_template = PROMPTS_CONFIG.get("transcription", {}).get("ai_prompt", "")
    if prompt_template:
        prompt = prompt_template.format(
            operator_label=operator_label,
            driver_label=driver_label,
        )
    else:
        prompt = (
            f'Transcreva o audio VERBATIM em portugues e retorne somente JSON. '
            f'REGRA CRITICA: A empresa de rastreamento e OPENTECH. '
            f'Prefixe cada segmento com "{operator_label}:" ou "{driver_label}:". '
            "Nao invente trechos e nao duplique frases consecutivas que nao existam no audio. "
            "Se não conseguir identificar alguma palavra ou trecho da fala, utilize exclusivamente o termo '[Inaudível]'. "
            "Se houver repeticao real na fala, mantenha somente a repeticao real. "
            "Saida: LISTA JSON com start (MM:SS), end (MM:SS), text."
        )
    from google.genai import types  # lazy: evita google.genai no boot do servidor
    from core.config import GENERATION_CONFIG  # lazy: depende de google.genai
    response = await asyncio.to_thread(ai_client.models.generate_content, model=AI_MODEL, contents=[prompt, types.Part.from_bytes(data=audio_file, mime_type=mime_type)], config=GENERATION_CONFIG)
    data = await asyncio.to_thread(
        parse_json_with_repair,
        response.text,
        '[{"start":"MM:SS","end":"MM:SS","text":"..."}]',
    )
    normalized = []
    for item in extract_transcription(data):
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        text = normalize_speaker_prefix(text, operator_label, driver_label)
        item["text"] = filter_hallucinations(remove_emojis(normalize_company_name(text)))
        normalized.append(item)
    result = deduplicate_transcription_segments(normalized)
    if not return_metadata:
        return result
    return (
        result,
        {
            "selected_strategy": "primary_ai",
            "selected_provider": "Primary AI",
            "selected_reason": "configured_primary_provider",
            "attempts": [
                {
                    "strategy": "primary_ai",
                    "provider": "Primary AI",
                    "status": "accepted",
                    "score": _score_transcription_segments(result),
                }
            ],
        },
    )
