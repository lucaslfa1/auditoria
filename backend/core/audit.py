"""Núcleo da auditoria de uma ligação/documento (transcrição + avaliação por IA).

Orquestra o pipeline de auditoria de UM item: resolve os critérios oficiais do
alerta (sempre do banco, módulo IA > Critérios), transcreve o áudio (ou faz parse
do documento), avalia com a IA e monta o ``AuditResult``. É o ponto chamado tanto
pela auditoria manual (via routers/services) quanto pela automação em lote.

CUSTO DE API: ``process_audit_with_ai`` dispara chamadas PAGAS ao Azure —
transcrição (Azure Speech Fast Transcription, + Whisper/GPT-4o no fallback) e
avaliação (Azure OpenAI GPT-4o). ``process_pdf_audit`` e ``reevaluate_audit``
gastam apenas a avaliação GPT-4o (sem transcrição de áudio). Em ``DETERMINISTIC_MODE``
um hit de cache por ``input_hash`` evita totalmente o custo de API. As funções de
parse de documento (``extract_text_from_pdf``, ``parse_whatsapp_log``) não têm
custo de API.
"""

import io
import logging
from datetime import datetime
from typing import Any, Optional

import re

logger = logging.getLogger(__name__)

from schemas import AuditAlert, AuditCriterion, AuditResult
import db.database as database
from repositories import audits
from audio.diarization_quality import (
    build_diarization_quality,
    build_diarization_reference,
)
from core.transcription_orchestrator import (
    infer_interlocutor_label,
)

from core.config import DETERMINISTIC_MODE, load_criteria_for_sector
from core.quality_analyzer import QualityAnalyzer
from core.runtime_flags import allow_official_criteria_test_fallback
from core.transcription import compute_input_hash, transcribe_audio
from core.evaluation import evaluate_with_ai_priority, result_from_raw
from core.quality_observability import (
    build_internal_quality_trace,
    emit_internal_quality_trace,
)
from core.transcription_quality import attach_transcription_quality_gate
from core.audit_pipeline import (
    attach_pipeline_context_to_audio_quality,
    coerce_pipeline_context,
)


def _is_operational_hybrid_fallback(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    return (
        str(metadata.get("fallback_from") or "").strip().lower() == "hybrid_dual"
        and str(metadata.get("fallback_type") or "").strip().lower() == "operational"
    )


def _analyze_raw_audio_quality(audio_file: bytes) -> dict[str, Any]:
    """Roda QualityAnalyzer sobre os bytes do audio para popular score/quality/notes/details
    pre-transcricao. O analyze ja tem try/except interno; este wrapper protege contra falhas
    de import (pydub ausente) sem quebrar o pipeline."""
    try:
        return QualityAnalyzer().analyze(audio_file) or {}
    except Exception as exc:
        logger.warning("[audio_quality] falha ao analisar audio bruto: %s", exc)
        return {
            "score": None,
            "quality": "desconhecida",
            "notes": [f"falha_quality_analyzer: {exc}"],
            "details": {},
        }


def _row_to_audit_criterion(row: dict[str, Any]) -> AuditCriterion:
    chave = str(row.get("chave") or "").strip() or None
    criterion_id = chave or f"crit_{row.get('id', 'unknown')}"
    evaluation_type = str(row.get("evaluation_type") or "auto").strip().lower()
    if evaluation_type not in {"auto", "manual"}:
        evaluation_type = "auto"
    return AuditCriterion(
        id=str(criterion_id),
        chave=chave,
        label=str(row.get("label") or "Criterio"),
        weight=float(row.get("weight") or 0),
        deflator=float(row.get("deflator")) if row.get("deflator") is not None else None,
        evaluation_type=evaluation_type,
        description=str(row.get("description") or ""),
    )


def _load_official_alert_metadata(alert_id: str) -> dict[str, Any]:
    try:
        from repositories.admin_criteria import get_alerts

        for row in get_alerts(database.get_connection):
            if str(row.get("id") or "").strip() == alert_id:
                return row
    except Exception:
        logger.exception("Falha ao carregar metadados oficiais do alerta %s", alert_id)
        if not allow_official_criteria_test_fallback():
            raise
    return {}


def _resolve_official_audit_alert(alert: AuditAlert, sector_id: Optional[str]) -> AuditAlert:
    """Resolve alert and criteria from Inteligencia Artificial > Criterios.

    The frontend may hold a stale criteria payload. Official scoring must always
    come from audit_alerts/audit_criteria at evaluation time.
    """

    original_alert_id = str(getattr(alert, "id", "") or "").strip()
    candidate_ids: list[str] = []
    try:
        from core.classification import canonicalize_alert_id

        canonical = canonicalize_alert_id(original_alert_id)
        if canonical:
            candidate_ids.append(canonical)
    except Exception:
        logger.exception("Falha ao canonicalizar alerta %s", original_alert_id)
        if not allow_official_criteria_test_fallback():
            raise
    if original_alert_id and original_alert_id not in candidate_ids:
        candidate_ids.append(original_alert_id)

    criteria_rows: list[dict[str, Any]] = []
    resolved_alert_id = original_alert_id
    try:
        from repositories.admin_criteria import get_criteria

        for candidate_id in candidate_ids:
            rows = get_criteria(database.get_connection, candidate_id)
            if rows:
                criteria_rows = rows
                resolved_alert_id = candidate_id
                break
    except Exception:
        logger.exception("Falha ao carregar criterios oficiais do alerta %s", original_alert_id)
        if not allow_official_criteria_test_fallback():
            raise

    if criteria_rows:
        metadata = _load_official_alert_metadata(resolved_alert_id)
        expected_direction = str(metadata.get("expected_direction") or alert.expected_direction or "").strip().lower() or None
        if expected_direction not in {"efetivada", "receptiva"}:
            expected_direction = None
        return AuditAlert(
            id=resolved_alert_id,
            label=str(metadata.get("label") or alert.label or resolved_alert_id),
            context=str(metadata.get("context") or alert.context or metadata.get("label") or resolved_alert_id),
            expected_direction=expected_direction,
            criteria=[_row_to_audit_criterion(row) for row in criteria_rows],
        )

    if allow_official_criteria_test_fallback():
        if alert.criteria:
            return alert
        loaded = load_criteria_for_sector(sector_id)
        if loaded:
            return AuditAlert(
                id=original_alert_id or str(sector_id or "alerta"),
                label=alert.label,
                context=alert.context,
                expected_direction=alert.expected_direction,
                criteria=loaded,
            )

    raise RuntimeError(
        "Alerta sem criterios oficiais cadastrados no modulo Inteligencia Artificial > Criterios "
        f"(alert_id={original_alert_id or 'vazio'}, sector_id={sector_id or 'vazio'})."
    )

__all__ = [
    "process_audit_with_ai",
    "extract_text_from_pdf",
    "parse_whatsapp_log",
    "process_pdf_audit",
    "reevaluate_audit",
]

async def process_audit_with_ai(
    audio_file: bytes,
    mime_type: str,
    alert: AuditAlert,
    operator_name: Optional[str],
    operator_id: Optional[str],
    sector_id: Optional[str],
    pipeline_context: Optional[Any] = None,
    allow_degraded_hybrid_fallback: Optional[bool] = None,
) -> tuple[AuditResult, str, bool]:
    """Audita uma ligação em ÁUDIO: transcreve, avalia com a IA e monta o resultado.

    Fluxo: resolve os critérios oficiais do alerta (do banco); calcula o
    ``input_hash``; em ``DETERMINISTIC_MODE`` retorna a auditoria do cache se
    houver; analisa a qualidade bruta do áudio; transcreve; avalia com IA; monta
    o ``AuditResult`` e emite o trace interno de qualidade.

    Parâmetros: ``audio_file``/``mime_type`` são os bytes e o tipo do áudio;
    ``alert`` é o alerta (será reescrito com os critérios oficiais);
    ``operator_name``/``operator_id``/``sector_id`` identificam o operador e setor;
    ``pipeline_context`` carrega metadados da esteira; ``allow_degraded_hybrid_fallback``
    (default ``True``) libera fallback degradado de transcrição.

    CUSTO DE API: transcrição (Azure Speech) + avaliação (GPT-4o), salvo hit de cache.
    Retorna ``(AuditResult, input_hash, from_cache)``. Sem persistência aqui (o
    chamador persiste); emite log/trace de observabilidade.
    """
    alert = _resolve_official_audit_alert(alert, sector_id)
    input_hash = compute_input_hash(audio_file, mime_type, alert, operator_name, operator_id, sector_id)
    coerced_pipeline_context = coerce_pipeline_context(pipeline_context)
    if allow_degraded_hybrid_fallback is None:
        allow_degraded_hybrid_fallback = True

    if DETERMINISTIC_MODE:
        cached = audits.get_audit_by_hash(database.get_connection, input_hash)
        if cached:
            emit_internal_quality_trace(
                logger,
                build_internal_quality_trace(
                    input_hash=input_hash,
                    source_type="audio",
                    alert=alert,
                    sector_id=sector_id,
                    criteria_list=alert.criteria or [],
                    result=cached,
                    audio_quality=getattr(cached, "audio_quality", None),
                    from_cache=True,
                    stage="process_audit_with_ai",
                ),
            )
            return cached, input_hash, True

    raw_audio_quality = _analyze_raw_audio_quality(audio_file)
    raw_audio_score = raw_audio_quality.get("score") if isinstance(raw_audio_quality, dict) else None

    transcription_result = await transcribe_audio(
        audio_file,
        mime_type,
        operator_name,
        None,
        alert,
        sector_id,
        return_metadata=True,
        allow_degraded_hybrid_fallback=allow_degraded_hybrid_fallback,
        audio_quality_score=raw_audio_score,
    )
    if isinstance(transcription_result, tuple):
        transcription, transcription_provider = transcription_result
    else:
        transcription = transcription_result
        transcription_provider = {}

    selected_engine = str(transcription_provider.get("selected_strategy") or "unknown").strip().lower()
    # Migracao fast: fast e o engine padrao; hybrid_dual virou legado opt-in.
    # A exigencia de "hybrid_dual obrigatorio" foi removida — qualquer engine
    # valido (fast, hybrid_dual, gpt4o_diarize, whisper...) e aceito.
    logger.info("==================================================")
    logger.info(f"🎤 TRANSCRIPTION ENGINE SELECTED: {selected_engine.upper()}")
    logger.info("==================================================")

    interlocutor_label = infer_interlocutor_label(alert, None)
    audio_quality = build_diarization_quality(
        transcription,
        {
            "diarization_reference": build_diarization_reference(interlocutor_label),
            "transcription_provider": transcription_provider,
            "score": raw_audio_quality.get("score") if isinstance(raw_audio_quality, dict) else None,
            "quality": raw_audio_quality.get("quality") if isinstance(raw_audio_quality, dict) else None,
            "notes": raw_audio_quality.get("notes") if isinstance(raw_audio_quality, dict) else None,
            "details": raw_audio_quality.get("details") if isinstance(raw_audio_quality, dict) else None,
        },
    )
    audio_quality = attach_transcription_quality_gate(audio_quality, transcription)
    audio_quality = attach_pipeline_context_to_audio_quality(
        audio_quality,
        coerced_pipeline_context,
        transcription_metadata=transcription_provider,
    )
    criteria_list = alert.criteria
            
    evaluation = await evaluate_with_ai_priority(transcription, alert, criteria_list, operator_name, audio_quality, sector_id)
    data = result_from_raw(
        evaluation,
        criteria_list,
        transcription,
        operator_name,
        operator_id,
        source_type="audio",
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    emit_internal_quality_trace(
        logger,
        build_internal_quality_trace(
            input_hash=input_hash,
            source_type="audio",
            alert=alert,
            sector_id=sector_id,
            transcription_metadata=transcription_provider,
            audio_quality=audio_quality,
            evaluation=evaluation,
            criteria_list=criteria_list,
            result=data,
            from_cache=False,
            stage="process_audit_with_ai",
        ),
    )
    return data, input_hash, False
def extract_text_from_pdf(file_content: bytes) -> str:
    """Extrai o texto cru de um PDF (delega a ``core.document_parsing.extract_raw_text``).

    Recebe os bytes do arquivo e retorna o texto extraído. Sem custo de API
    (extração local). Fase 1 usa pypdf; Fase 2, pdfplumber.
    """
    # Extração isolada em core.document_parsing (Fase 1: pypdf; Fase 2: pdfplumber).
    from core.document_parsing import extract_raw_text
    return extract_raw_text(file_content)
def parse_whatsapp_log(text: str) -> list[dict]:
    """Faz parse de um log de conversa no formato WhatsApp em segmentos por locutor.

    Reconhece linhas ``[DD/MM/AAAA HH:MM:SS] Fulano: mensagem``; converte o
    timestamp para ``HH:MM`` (usa ``"00:00"`` se não parsear). Linhas sem cabeçalho
    são anexadas ao segmento anterior; texto antes da primeira mensagem vira um
    segmento de preâmbulo. Retorna lista de dicts ``{"start", "end", "text"}``,
    ou ``[]`` se o texto não casar com o formato WhatsApp. Função pura, sem custo
    de API.
    """
    pattern = r"\[(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s+(.*)"
    if not re.search(pattern, text):
        return []
    lines = text.split('\n'); segments = []; current = None
    preamble = []
    for line in lines:
        line = line.strip()
        if not line: continue
        match = re.match(pattern, line)
        if match:
            if preamble:
                segments.append({"start": "00:00", "end": "00:00", "text": "\n".join(preamble)})
                preamble = []
            if current: segments.append(current)
            ts, speaker, content = match.group(1), match.group(2), match.group(3)
            try: time_str = datetime.strptime(ts, "%d/%m/%Y %H:%M:%S").strftime("%H:%M")
            except ValueError: time_str = "00:00"
            current = {"start": time_str, "end": time_str, "text": f"{speaker}: {content}"}
        elif current: current["text"] += f"\n{line}"
        else: preamble.append(line)
    if preamble:
        segments.append({"start": "00:00", "end": "00:00", "text": "\n".join(preamble)})
    if current: segments.append(current)
    return segments
async def process_pdf_audit(
    file_content: bytes,
    mime_type: str,
    alert: AuditAlert,
    operator_name: Optional[str],
    operator_id: Optional[str],
    sector_id: Optional[str],
    pipeline_context: Optional[Any] = None,
) -> tuple[AuditResult, str, bool]:
    """Audita um DOCUMENTO (PDF/chat): extrai o texto, estrutura por locutor e avalia com a IA.

    Fluxo análogo a ``process_audit_with_ai`` mas sem transcrição de áudio:
    resolve critérios oficiais; calcula ``input_hash``; usa cache em
    ``DETERMINISTIC_MODE``; extrai o texto do PDF e o estrutura via
    ``core.document_parsing.parse_document`` (dispatcher Service Cloud/WhatsApp/
    genérico, com fallback para bloco único); avalia com a IA e monta o resultado.

    CUSTO DE API: apenas avaliação GPT-4o (sem áudio), salvo hit de cache.
    Retorna ``(AuditResult, input_hash, from_cache)``. Não persiste; emite trace
    interno de qualidade.
    """
    alert = _resolve_official_audit_alert(alert, sector_id)
    input_hash = compute_input_hash(file_content, mime_type, alert, operator_name, operator_id, sector_id)
    if DETERMINISTIC_MODE:
        cached = audits.get_audit_by_hash(database.get_connection, input_hash)
        if cached:
            emit_internal_quality_trace(
                logger,
                build_internal_quality_trace(
                    input_hash=input_hash,
                    source_type="pdf",
                    alert=alert,
                    sector_id=sector_id,
                    criteria_list=alert.criteria or [],
                    result=cached,
                    audio_quality=getattr(cached, "audio_quality", None),
                    from_cache=True,
                    stage="process_pdf_audit",
                ),
            )
            return cached, input_hash, True
    # Dispatcher de formato (Service Cloud / WhatsApp / genérico) com limpeza e
    # estruturação por locutor; fallback para bloco único preserva o conteúdo cru.
    from core.document_parsing import parse_document
    raw_text = extract_text_from_pdf(file_content)
    transcription = parse_document(raw_text, operator_name) or [{"start": "00:00", "end": "00:00", "text": raw_text}]
    criteria_list = alert.criteria

    audio_quality = attach_pipeline_context_to_audio_quality(None, pipeline_context)
    evaluation = await evaluate_with_ai_priority(
        transcription,
        alert,
        criteria_list,
        operator_name,
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    data = result_from_raw(
        evaluation,
        criteria_list,
        transcription,
        operator_name,
        operator_id,
        source_type="pdf",
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    emit_internal_quality_trace(
        logger,
        build_internal_quality_trace(
            input_hash=input_hash,
            source_type="pdf",
            alert=alert,
            sector_id=sector_id,
            audio_quality=audio_quality,
            evaluation=evaluation,
            criteria_list=criteria_list,
            result=data,
            from_cache=False,
            stage="process_pdf_audit",
        ),
    )
    return data, input_hash, False
async def reevaluate_audit(transcription: list[dict], alert: AuditAlert, operator_name: Optional[str], operator_id: Optional[str], sector_id: Optional[str], source_type: Optional[str] = "audio", audio_quality: Optional[dict] = None) -> AuditResult:
    """Reavalia uma auditoria a partir de uma transcrição já editada (sem re-transcrever).

    Usado quando o auditor corrige a transcrição: resolve os critérios oficiais,
    reconstrói a qualidade de diarização (só para ``source_type='audio'``) e roda
    de novo a avaliação por IA sobre o texto fornecido.

    CUSTO DE API: avaliação GPT-4o (não há transcrição de áudio aqui).
    Retorna o ``AuditResult`` reavaliado. Não persiste; emite trace interno de qualidade.
    """
    alert = _resolve_official_audit_alert(alert, sector_id)
    if (source_type or "audio") == "audio":
        audio_quality = build_diarization_quality(transcription, audio_quality)
        audio_quality = attach_transcription_quality_gate(audio_quality, transcription)
    criteria_list = alert.criteria
            
    evaluation = await evaluate_with_ai_priority(transcription, alert, criteria_list, operator_name, audio_quality, sector_id)
    normalized_source_type = source_type or "audio"
    result = result_from_raw(
        evaluation,
        criteria_list,
        transcription,
        operator_name,
        operator_id,
        source_type=normalized_source_type,
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    emit_internal_quality_trace(
        logger,
        build_internal_quality_trace(
            source_type=normalized_source_type,
            alert=alert,
            sector_id=sector_id,
            audio_quality=audio_quality,
            evaluation=evaluation,
            criteria_list=criteria_list,
            result=result,
            from_cache=False,
            stage="reevaluate_audit",
        ),
    )
    return result
