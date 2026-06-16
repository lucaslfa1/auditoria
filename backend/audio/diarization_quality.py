"""Scoring de qualidade de diarização e helpers de áudio.

Roda DEPOIS da transcrição: recebe os segmentos já rotulados (operador/
interlocutor/telefonia) e produz o bloco `diarization` dentro do dict de
`audio_quality`, além de uma recomendação de revisão para a auditoria. O score
de diarização (0..1) mede a confiança na separação de falantes — NÃO a qualidade
do áudio bruto (volume/silêncio/clipping), que vem do QualityAnalyzer upstream.

Também concentra helpers de parsing/normalização de texto e timestamps usados
nesse cálculo. Extraído de services.py para reduzir tamanho e melhorar coesão.

Sem custo de API (só CPU/processamento de texto); as chaves do dict `diarization`
e `review_*` são contrato consumido pela UI/BI e pela auditoria — não renomear.
"""
from __future__ import annotations

import io
import re
import unicodedata
import logging
from typing import Any, Optional

from audio.speaker_detection import SpeakerDetectionService

logger = logging.getLogger(__name__)


# ── Text helpers ─────────────────────────────────────────────────────────────

def normalize_lookup_text(text: str) -> str:
    """Normaliza texto para comparação: minúsculas, sem acento e espaços colapsados.

    Aplica NFKD + remoção de marcas diacríticas. Função pura.
    """
    normalized = unicodedata.normalize("NFKD", text or "")
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", without_marks).strip().lower()


def extract_segment_speaker(text: str) -> str:
    """Extrai o rótulo do falante do prefixo "Falante: ..." de um segmento.

    Considera apenas um prefixo de até 40 caracteres antes do primeiro ":".
    Retorna o rótulo em minúsculas (ex.: "operador", "telefonia") ou "" se o
    texto não tiver esse prefixo. Função pura.
    """
    if not text:
        return ""
    match = re.match(r"^\s*([^:]{1,40}):\s*", text)
    if not match:
        return ""
    return match.group(1).strip().lower()


def parse_float_value(value: Any) -> Optional[float]:
    """Converte um valor para float aceitando vírgula decimal; None em falha.

    Aceita int/float diretos e strings (troca "," por "."). Função pura.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def extract_segment_body(text: str) -> str:
    """Devolve o corpo do segmento, sem o prefixo "Falante:".

    Se não houver ":", retorna o texto inteiro (apenas com strip). Função pura.
    """
    if not text:
        return ""
    _speaker, separator, remainder = text.partition(":")
    return remainder.strip() if separator else text.strip()


def parse_timestamp_seconds(value: Any) -> float:
    """Converte um timestamp em segundos (float).

    Aceita "HH:MM:SS(.mmm)", "MM:SS(.mmm)" ou um número puro. Retorna 0.0 para
    vazio ou formato inválido. Função pura.
    """
    raw = str(value or "").strip()
    if not raw:
        return 0.0

    parts = raw.split(":")
    try:
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def clone_transcription_segment(segment: dict, *, start: str, end: str, text: str) -> dict:
    """Copia um segmento de transcrição sobrescrevendo start/end/text.

    Faz cópia rasa do dict original (mantém demais chaves) e retorna o novo
    segmento. Não muta o `segment` recebido. Função pura.
    """
    cloned = dict(segment)
    cloned["start"] = start
    cloned["end"] = end
    cloned["text"] = text
    return cloned


def coerce_segment_id_list(value: Any) -> list[int]:
    """Normaliza um valor em lista de speaker_ids inteiros >= 0, únicos e ordenados.

    Aceita list/tuple; ignora itens não conversíveis ou negativos. Para qualquer
    outro tipo, retorna lista vazia. Função pura.
    """
    if not isinstance(value, (list, tuple)):
        return []
    result: list[int] = []
    for item in value:
        try:
            numeric = int(item)
        except (TypeError, ValueError):
            continue
        if numeric >= 0:
            result.append(numeric)
    return sorted(set(result))


# ── Telephony / handoff detection ────────────────────────────────────────────

def is_telephony_segment(text: str) -> bool:
    """Indica se o corpo do segmento é áudio de telefonia/URA (atendimento eletrônico).

    Delega a `SpeakerDetectionService.eh_segmento_telefonia` após extrair e
    normalizar o corpo do segmento. Função pura.
    """
    normalized_body = normalize_lookup_text(extract_segment_body(text))
    return SpeakerDetectionService.eh_segmento_telefonia(normalized_body)


def is_short_opening_human_exchange(start_value: Any, text: str, speaker_name: str) -> bool:
    """Detecta uma saudação humana curta de abertura (alô/bom dia/etc.).

    Usado para reduzir o peso de risco de troca de falante em trechos iniciais.
    Só retorna True quando: há falante humano (não "" nem "telefonia"); o início
    é até 40s; o corpo não é telefonia; tem no máximo 8 palavras; e começa por um
    cumprimento genérico conhecido. Função pura.
    """
    if speaker_name in {"", "telefonia"}:
        return False
    if parse_timestamp_seconds(start_value) > 40.0:
        return False

    normalized_body = normalize_lookup_text(extract_segment_body(text))
    if not normalized_body or SpeakerDetectionService.eh_segmento_telefonia(normalized_body):
        return False

    generic_openers = (
        "alo",
        "ola",
        "oi",
        "bom dia",
        "boa tarde",
        "boa noite",
        "tudo bem",
        "em que posso ajudar",
        "como posso ajudar",
        "com quem eu falo",
        "quem fala",
        "pode falar",
    )
    word_count = len([word for word in normalized_body.split(" ") if word])
    if word_count > 8:
        return False
    return any(normalized_body.startswith(opener) for opener in generic_openers)


def is_support_point_handoff_segment(text: str, speaker_name: str, diarization_reference: dict) -> bool:
    """Detecta passagem de chamada (handoff) a um ponto de apoio/posto.

    Só vale quando: o falante é o interlocutor (não "", "operador" nem
    "telefonia"); a referência de diarização indica conferência possível/esperada;
    o rótulo do interlocutor menciona "ponto de apoio"/"posto"; e o corpo casa um
    marcador de handoff (`eh_handoff_interlocutor`). Função pura.
    """
    if speaker_name in {"", "operador", "telefonia"}:
        return False
    if not bool(diarization_reference.get("conference_possible") or diarization_reference.get("conference_expected")):
        return False
    normalized_label = normalize_lookup_text(str(diarization_reference.get("interlocutor_label") or ""))
    if "ponto de apoio" not in normalized_label and "posto" not in normalized_label:
        return False
    normalized_body = normalize_lookup_text(extract_segment_body(text))
    return SpeakerDetectionService.eh_handoff_interlocutor(normalized_body)


# ── Diarization reference & quality ─────────────────────────────────────────

def build_diarization_reference(
    interlocutor_label: Optional[str] = None,
    *,
    expected_max_speakers: Optional[int] = None,
) -> dict:
    """Monta o dict de referência de diarização (expectativas de falantes).

    A partir do rótulo do interlocutor e do máximo esperado de speakers, calcula
    quantos falantes são esperados para operador e interlocutor e se há
    possibilidade de conferência (ativada quando o rótulo cita "ponto de apoio"/
    "posto"). É consumido por `build_diarization_quality` para julgar
    fragmentação/risco.

    Params:
        interlocutor_label: rótulo do interlocutor (ex.: "Motorista",
            "Ponto de apoio").
        expected_max_speakers: total máximo esperado de falantes; se None ou
            inválido, assume operador(1) + interlocutor(1).

    Retorna dict com as chaves: interlocutor_label, expected_max_speakers,
    expected_operator_speakers, expected_interlocutor_speakers,
    conference_expected, conference_possible. Função pura.
    """
    normalized_label = normalize_lookup_text(interlocutor_label or "")
    expected_operator_speakers = 1
    expected_interlocutor_speakers = 1
    conference_possible = False

    if "ponto de apoio" in normalized_label or "posto" in normalized_label:
        conference_possible = True

    if expected_max_speakers is None:
        expected_max_speakers = expected_operator_speakers + expected_interlocutor_speakers
    else:
        try:
            expected_max_speakers = max(1, int(expected_max_speakers))
        except (TypeError, ValueError):
            expected_max_speakers = expected_operator_speakers + expected_interlocutor_speakers

    expected_interlocutor_speakers = max(
        expected_interlocutor_speakers,
        max(1, expected_max_speakers - expected_operator_speakers),
    )

    return {
        "interlocutor_label": interlocutor_label or "",
        "expected_max_speakers": expected_max_speakers,
        "expected_operator_speakers": expected_operator_speakers,
        "expected_interlocutor_speakers": expected_interlocutor_speakers,
        "conference_expected": conference_possible,
        "conference_possible": conference_possible,
    }


def build_audit_review_recommendation(audio_quality: Optional[dict]) -> dict[str, Any]:
    """Deriva uma recomendação de revisão manual a partir da qualidade do áudio.

    Inspeciona o bloco `diarization` (risco de troca, contagem de speakers,
    fragmentação, trechos ambíguos, score) e o `transcription_provider`
    (provedor selecionado por "best_candidate", falhas em tentativas) e acumula
    motivos com prioridade crescente (low/medium/high).

    Params:
        audio_quality: dict de qualidade do áudio (pode ser None/sem chaves).

    Retorna dict com: review_recommended (bool), review_priority (a maior
    prioridade encontrada) e review_reasons (lista de códigos de motivo, em
    PT-BR snake_case — contrato consumido downstream). Função pura.
    """
    diarization = audio_quality.get("diarization") if isinstance(audio_quality, dict) else None
    provider_meta = audio_quality.get("transcription_provider") if isinstance(audio_quality, dict) else None

    priority_rank = {"low": 0, "medium": 1, "high": 2}
    review_priority = "low"
    review_reasons: list[str] = []

    def add_reason(reason: str, priority: str) -> None:
        nonlocal review_priority
        if reason and reason not in review_reasons:
            review_reasons.append(reason)
        if priority_rank.get(priority, 0) > priority_rank.get(review_priority, 0):
            review_priority = priority

    if isinstance(diarization, dict):
        swap_risk = str(diarization.get("swap_risk") or "").strip().lower()
        raw_speaker_count = int(diarization.get("raw_speaker_count") or 0)
        telephony_segment_count = int(diarization.get("telephony_segment_count") or 0)
        diarization_score = parse_float_value(diarization.get("score")) or 0.0
        fragmented = bool(diarization.get("fragmented"))
        ambiguous_ranges = diarization.get("ambiguous_ranges") or []

        if raw_speaker_count == 0:
            add_reason("sem_ids_nativos_de_speaker", "high")
        elif raw_speaker_count == 1:
            add_reason(
                "apenas_um_speaker_humano_detectado",
                "medium" if telephony_segment_count > 0 else "high",
            )

        if swap_risk == "high":
            add_reason("risco_alto_de_troca_de_falante", "high")
        elif swap_risk == "medium":
            add_reason("risco_medio_de_troca_de_falante", "medium")

        if fragmented:
            add_reason("fragmentacao_de_speaker", "medium")
        if ambiguous_ranges:
            add_reason("trechos_ambiguos_relevantes", "medium")

        if diarization_score < 0.42:
            add_reason("score_de_diarizacao_muito_baixo", "high")
        elif diarization_score < 0.50:
            add_reason("score_de_diarizacao_baixo", "medium")

    if isinstance(provider_meta, dict):
        selected_reason = str(provider_meta.get("selected_reason") or "").strip().lower()
        attempts = provider_meta.get("attempts") or []
        if selected_reason == "best_candidate":
            add_reason("nenhum_provedor_passou_na_validacao_forte", "medium")
        if isinstance(attempts, list) and any(
            isinstance(item, dict) and str(item.get("status") or "").strip().lower() == "error"
            for item in attempts
        ):
            add_reason("falhas_em_provedores_de_transcricao", "medium")

    return {
        "review_recommended": bool(review_reasons),
        "review_priority": review_priority,
        "review_reasons": review_reasons,
    }


def build_diarization_quality(transcription_segments: list[dict], audio_quality: Optional[dict] = None) -> Optional[dict]:
    """Calcula o bloco `diarization` e anexa a recomendação de revisão.

    Percorre os segmentos transcritos contando falantes humanos vs. telefonia,
    risco por segmento, fragmentação por papel e trechos ambíguos; usa a
    referência em `audio_quality["diarization_reference"]` (ver
    `build_diarization_reference`) para os limites esperados. Produz um score
    (0..1), um rótulo de qualidade ("boa"/"regular"/"baixa"/"muito_baixa"), o
    risco de troca de falante ("low"/"medium"/"high") e notas de diagnóstico.

    Importante: NÃO preenche os campos top-level `score`/`quality` (qualidade do
    áudio bruto, populados upstream pelo QualityAnalyzer) — apenas enriquece com
    `base["diarization"]` e os campos `review_*`.

    Params:
        transcription_segments: lista de segmentos (dicts com text, start, end,
            speaker_source_ids, etc.). Vazio gera um bloco com
            notes=["transcricao_vazia"].
        audio_quality: dict base a enriquecer (não é mutado; é copiado).

    Retorna uma cópia de `audio_quality` com as chaves `diarization` e `review_*`
    adicionadas. As chaves do dict são contrato (UI/BI/auditoria). Função pura.
    """
    base = dict(audio_quality or {})
    # score/quality top-level descrevem a qualidade do AUDIO BRUTO (volume, silencio,
    # clipping, sample rate, codec) e devem ser populados upstream via QualityAnalyzer.
    # Esta funcao enriquece com diarization.* (pos-transcricao). NUNCA preencher score/
    # quality com defaults — falsos positivos mascaram problemas reais de audio.
    diarization_reference = base.get("diarization_reference") if isinstance(base.get("diarization_reference"), dict) else {}
    expected_max_speakers = max(1, int(diarization_reference.get("expected_max_speakers", 2) or 2))
    expected_operator_speakers = max(1, int(diarization_reference.get("expected_operator_speakers", 1) or 1))
    expected_interlocutor_speakers = max(1, int(diarization_reference.get("expected_interlocutor_speakers", 1) or 1))
    conference_possible = bool(
        diarization_reference.get("conference_possible", diarization_reference.get("conference_expected", False))
    )

    source_ids: set[int] = set()
    operator_source_ids: set[int] = set()
    interlocutor_source_ids: set[int] = set()
    ambiguous_ranges: list[dict] = []
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    segment_count = 0
    human_segment_count = 0
    telephony_segment_count = 0
    opening_exchange_count = 0
    handoff_segment_count = 0

    for segment in transcription_segments or []:
        if not isinstance(segment, dict):
            continue
        segment_count += 1
        text = str(segment.get("text", "")).strip()
        speaker_name = extract_segment_speaker(text)
        current_source_ids = coerce_segment_id_list(segment.get("speaker_source_ids"))
        is_telephony = speaker_name == "telefonia" or is_telephony_segment(text)
        if is_telephony:
            telephony_segment_count += 1
            continue

        human_segment_count += 1
        source_ids.update(current_source_ids)
        risk = str(segment.get("speaker_risk", "") or segment.get("diarization_risk", "")).strip().lower()
        if risk not in risk_counts:
            risk = "medium" if current_source_ids else "high"
        is_short_opening = is_short_opening_human_exchange(segment.get("start"), text, speaker_name)
        if is_short_opening and risk == "high":
            risk = "medium"
            opening_exchange_count += 1
        is_support_handoff = is_support_point_handoff_segment(text, speaker_name, diarization_reference)
        if is_support_handoff:
            handoff_segment_count += 1
            if risk == "high":
                risk = "medium"
        risk_counts[risk] += 1

        ambiguous = bool(segment.get("speaker_ambiguous", segment.get("diarization_ambiguous", False)))
        if (ambiguous or risk == "high") and not is_short_opening:
            ambiguous_ranges.append(
                {
                    "start": str(segment.get("start", "00:00")),
                    "end": str(segment.get("end", "00:00")),
                    "speaker": speaker_name,
                    "text": text[:180],
                }
            )

        if speaker_name == "operador":
            operator_source_ids.update(current_source_ids)
        elif speaker_name:
            interlocutor_source_ids.update(current_source_ids)

    if not transcription_segments:
        diarization = {
            "score": 0.0,
            "quality": "indefinida",
            "swap_risk": "high",
            "raw_speaker_count": 0,
            "fragmented": False,
            "operator_speaker_ids": [],
            "interlocutor_speaker_ids": [],
            "ambiguous_ranges": [],
            "notes": ["transcricao_vazia"],
        }
        base["diarization"] = diarization
        base.update(build_audit_review_recommendation(base))
        return base

    raw_speaker_count = len(source_ids)
    effective_max_speakers = expected_max_speakers + (1 if conference_possible and handoff_segment_count > 0 else 0)
    effective_interlocutor_speakers = expected_interlocutor_speakers + (
        1 if conference_possible and handoff_segment_count > 0 else 0
    )
    operator_fragmented = len(operator_source_ids) > expected_operator_speakers
    interlocutor_fragmented = len(interlocutor_source_ids) > effective_interlocutor_speakers
    fragmented = raw_speaker_count > effective_max_speakers or operator_fragmented or interlocutor_fragmented
    if raw_speaker_count == 0:
        swap_risk = "high"
    elif raw_speaker_count == 1:
        swap_risk = "medium" if telephony_segment_count > 0 else "high"
    elif risk_counts["high"] > 0:
        swap_risk = "high"
    elif fragmented or risk_counts["medium"] > 0:
        swap_risk = "medium"
    else:
        swap_risk = "low"
    if raw_speaker_count >= 2 and not fragmented and risk_counts["high"] == 0 and risk_counts["medium"] <= 2:
        swap_risk = "low"

    score = 0.94
    if raw_speaker_count == 0:
        score = 0.32
    elif raw_speaker_count == 1:
        score = 0.42
    elif raw_speaker_count > effective_max_speakers or operator_fragmented or interlocutor_fragmented:
        score -= 0.18
    score -= min(0.34, risk_counts["high"] * 0.12)
    score -= min(0.22, risk_counts["medium"] * 0.04)
    score += min(0.08, telephony_segment_count * 0.02)
    score += min(0.04, opening_exchange_count * 0.01)
    score = max(0.08, min(0.98, score))

    if score >= 0.82:
        quality_label = "boa"
    elif score >= 0.62:
        quality_label = "regular"
    elif score >= 0.42:
        quality_label = "baixa"
    else:
        quality_label = "muito_baixa"

    notes: list[str] = []
    if raw_speaker_count == 0:
        notes.append("sem_ids_nativos_de_speaker")
    if raw_speaker_count == 1:
        notes.append("apenas_um_speaker_detectado")
    if fragmented:
        notes.append("fragmentacao_de_speaker_detectada")
    if ambiguous_ranges:
        notes.append("ha_trechos_com_risco_de_troca_de_falante")
    if telephony_segment_count:
        notes.append("segmentos_de_telefonia_ignorados_na_diarizacao")
    if opening_exchange_count:
        notes.append("abertura_humana_curta_com_peso_reduzido")
    if handoff_segment_count:
        notes.append("handoff_interlocutor_detectado")

    diarization = {
        "score": round(score, 3),
        "quality": quality_label,
        "swap_risk": swap_risk,
        "raw_speaker_count": raw_speaker_count,
        "segment_count": segment_count,
        "human_segment_count": human_segment_count,
        "telephony_segment_count": telephony_segment_count,
        "expected_max_speakers": expected_max_speakers,
        "effective_max_speakers": effective_max_speakers,
        "fragmented": fragmented,
        "operator_fragmented": operator_fragmented,
        "interlocutor_fragmented": interlocutor_fragmented,
        "operator_speaker_ids": sorted(operator_source_ids),
        "interlocutor_speaker_ids": sorted(interlocutor_source_ids),
        "conference_possible": conference_possible,
        "handoff_detected": handoff_segment_count > 0,
        "ambiguous_ranges": ambiguous_ranges[:12],
        "risk_counts": risk_counts,
        "notes": notes,
    }
    base["diarization"] = diarization
    review_meta = build_audit_review_recommendation(base)
    base.update(review_meta)
    return base


# ── Audio utilities ──────────────────────────────────────────────────────────

def detect_audio_mime_type(audio_file: bytes, declared_mime_type: str = "audio/wav") -> str:
    safe_declared = (declared_mime_type or "audio/wav").strip().lower() or "audio/wav"
    header = bytes(audio_file[:16] if audio_file else b"")
    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio/wav"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if header.startswith(b"ID3"):
        return "audio/mpeg"
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "audio/mpeg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "audio/mp4"
    if header.startswith(b"fLaC"):
        return "audio/flac"
    if header.startswith(b"\x1A\x45\xDF\xA3"):
        return "audio/webm"
    return safe_declared


def extract_audio_excerpt(
    audio_file: bytes,
    source_mime_type: str = "audio/wav",
    *,
    duration_seconds: int,
) -> bytes:
    """Extract the first N seconds of an audio file as mono 16kHz WAV.
    
    Usa ffmpeg via temp files para evitar carregar o arquivo inteiro na memoria com o pydub,
    resolvendo o gargalo de OOM/lentidao entre o pre-scan e a transcricao completa.
    """
    import tempfile
    import os
    import subprocess

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_path = os.path.join(tmp_dir, "input.bin")
            wav_path = os.path.join(tmp_dir, "output.wav")
            with open(in_path, "wb") as f:
                f.write(audio_file)
            cmd = [
                "ffmpeg", "-y", "-threads", "1", 
                "-i", in_path, 
                "-ac", "1", 
                "-ar", "16000", 
                "-t", str(duration_seconds), 
                "-f", "wav", wav_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            with open(wav_path, "rb") as f:
                return f.read()
    except Exception as exc:
        logger.warning("Falha ao fatiar audio via ffmpeg: %s. Fallback para envio do audio completo.", exc)
        return audio_file
