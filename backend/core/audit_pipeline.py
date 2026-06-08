from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from db.domain_constants import DEFAULT_SOURCE_TYPE, SOURCE_TYPE_AUDIO, SOURCE_TYPE_PDF, SOURCE_TYPES

logger = logging.getLogger(__name__)

AUDIT_ORIGIN_MANUAL_UPLOAD = "manual_upload"
AUDIT_ORIGIN_TELEFONIA_MANUAL = "telefonia_manual"
AUDIT_ORIGIN_AUTOMATION = "automation"

UNKNOWN_VALUES = {
    "",
    "desconhecido",
    "nao identificado",
    "não identificado",
    "unknown",
    "erro",
    "none",
    "null",
}

PIPELINE_METADATA_KEYS = {
    "origem",
    "source_type",
    "classification_status",
    "classification_error",
    "classified_by",
    "huawei_call_id",
    "huawei_begin_time",
    "huawei_duration",
    "huawei_is_call_in",
    "huawei_call_reason",
    "huawei_talk_reason",
    "huawei_talk_remark",
    "huawei_call_reason_code",
    "native_reason_match",
    "native_reason_targets",
    "audio_direction_pre_triage",
    "operator_sector_id",
    "operator_sector_real",
    "operator_name",
    "operator_name_real",
    "operator_id",
    "id_huawei",
    "matricula",
    "operator_matricula",
    "is_manual",
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_unknown_value(value: Any) -> bool:
    return _clean_text(value).lower() in UNKNOWN_VALUES


def normalize_source_type(source_type: Any, filename: str = "") -> str:
    normalized = _clean_text(source_type).lower()
    if normalized in SOURCE_TYPES:
        return normalized
    return SOURCE_TYPE_PDF if _clean_text(filename).lower().endswith(".pdf") else DEFAULT_SOURCE_TYPE


@dataclass
class AuditPipelineContext:
    origin: str
    source_type: str = DEFAULT_SOURCE_TYPE
    filename: str = ""
    sector_id: str = ""
    alert_id: str = ""
    alert_label: str = ""
    operator_name: str = ""
    operator_id: str = ""
    queue_input_hash: str = ""
    media_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    classification_confidence: Optional[float] = None
    review_reasons: list[str] = field(default_factory=list)
    context_repair_applied: bool = False
    context_repair_reasons: list[str] = field(default_factory=list)

    def mark_repaired(self, reason: str) -> None:
        reason = _clean_text(reason)
        if not reason:
            return
        self.context_repair_applied = True
        if reason not in self.context_repair_reasons:
            self.context_repair_reasons.append(reason)

    def to_router_context(self) -> dict[str, Any]:
        return {
            "sector_id": self.sector_id,
            "alert_id": self.alert_id,
            "operator_name": self.operator_name,
            "operator_id": self.operator_id,
            "source_type": self.source_type,
            "filename": self.filename,
            "media_path": self.media_path,
            "pipeline_context": self,
        }

    def to_audit_metadata(self) -> dict[str, Any]:
        source_metadata = {
            key: value
            for key, value in (self.metadata or {}).items()
            if key in PIPELINE_METADATA_KEYS and value not in (None, "")
        }
        return {
            "origin": self.origin,
            "source_type": self.source_type,
            "filename": self.filename,
            "sector_id": self.sector_id,
            "alert_id": self.alert_id,
            "alert_label": self.alert_label,
            "operator_name": self.operator_name,
            "operator_id": self.operator_id,
            "queue_input_hash": self.queue_input_hash,
            "media_path": self.media_path,
            "classification": {
                "confidence": self.classification_confidence,
                "review_reasons": list(self.review_reasons),
            },
            "context_repair": {
                "applied": self.context_repair_applied,
                "reasons": list(self.context_repair_reasons),
            },
            "source_metadata": source_metadata,
        }


def coerce_pipeline_context(value: Any) -> Optional[AuditPipelineContext]:
    if value is None:
        return None
    if isinstance(value, AuditPipelineContext):
        return value
    if not isinstance(value, Mapping):
        return None

    classification = value.get("classification") if isinstance(value.get("classification"), Mapping) else {}
    context_repair = value.get("context_repair") if isinstance(value.get("context_repair"), Mapping) else {}
    source_metadata = value.get("source_metadata") if isinstance(value.get("source_metadata"), Mapping) else {}
    return AuditPipelineContext(
        origin=_clean_text(value.get("origin")),
        source_type=normalize_source_type(value.get("source_type"), _clean_text(value.get("filename"))),
        filename=_clean_text(value.get("filename")),
        sector_id=_clean_text(value.get("sector_id")),
        alert_id=_clean_text(value.get("alert_id")),
        alert_label=_clean_text(value.get("alert_label")),
        operator_name=_clean_text(value.get("operator_name")),
        operator_id=_clean_text(value.get("operator_id")),
        queue_input_hash=_clean_text(value.get("queue_input_hash")),
        media_path=_clean_text(value.get("media_path")),
        metadata=dict(source_metadata),
        classification_confidence=_coerce_float(classification.get("confidence")),
        review_reasons=[
            _clean_text(reason)
            for reason in classification.get("review_reasons", [])
            if _clean_text(reason)
        ] if isinstance(classification.get("review_reasons"), list) else [],
        context_repair_applied=bool(context_repair.get("applied")),
        context_repair_reasons=[
            _clean_text(reason)
            for reason in context_repair.get("reasons", [])
            if _clean_text(reason)
        ] if isinstance(context_repair.get("reasons"), list) else [],
    )


def build_manual_upload_context(
    *,
    filename: str,
    source_type: str,
    sector_id: Optional[str],
    alert_id: Optional[str],
    alert_label: Optional[str],
    operator_name: Optional[str],
    operator_id: Optional[str],
) -> AuditPipelineContext:
    return AuditPipelineContext(
        origin=AUDIT_ORIGIN_MANUAL_UPLOAD,
        source_type=normalize_source_type(source_type, filename),
        filename=_clean_text(filename),
        sector_id=_clean_text(sector_id).lower(),
        alert_id=_clean_text(alert_id),
        alert_label=_clean_text(alert_label),
        operator_name=_clean_text(operator_name),
        operator_id=_clean_text(operator_id),
    )


def build_queue_audit_context(item: dict, *, origin: str) -> AuditPipelineContext:
    metadata = _coerce_metadata((item or {}).get("metadata") or (item or {}).get("metadata_json"))
    filename = _first_text((item or {}).get("nome_arquivo"), metadata.get("filename"), "gravacao.wav")
    motivos = (item or {}).get("motivos_revisao") or metadata.get("review_reasons") or []
    if not isinstance(motivos, list):
        motivos = []
    source_type = normalize_source_type(metadata.get("source_type") or (item or {}).get("source_type"), filename)
    media_path = _first_text(
        metadata.get("classified_audio_path"),
        metadata.get("classified_file_path"),
        (item or {}).get("media_path"),
    )

    return AuditPipelineContext(
        origin=origin,
        source_type=source_type,
        filename=filename,
        sector_id=_first_text(
            (item or {}).get("setor_previsto"),
            metadata.get("sector_id"),
            metadata.get("operator_sector_id"),
            metadata.get("setor"),
        ).lower(),
        alert_id=_first_text(
            (item or {}).get("alerta_previsto"),
            metadata.get("alert_id"),
            metadata.get("alerta_previsto"),
        ),
        alert_label=_first_text((item or {}).get("alerta_label"), metadata.get("alert_label")),
        operator_name=_first_text(
            (item or {}).get("operador_previsto"),
            metadata.get("operator_name"),
            metadata.get("operator_name_real"),
            metadata.get("operador_nome"),
        ),
        operator_id=_first_text(
            (item or {}).get("operator_id"),
            metadata.get("operator_id"),
            metadata.get("id_huawei"),
            metadata.get("operator_id_huawei_real"),
            metadata.get("matricula"),
            metadata.get("operator_matricula"),
            metadata.get("operador_id"),
        ),
        queue_input_hash=_clean_text((item or {}).get("input_hash")),
        media_path=media_path,
        metadata=metadata,
        classification_confidence=_coerce_float((item or {}).get("confianca") or metadata.get("confidence")),
        review_reasons=[_clean_text(reason) for reason in motivos if _clean_text(reason)],
    )


def repair_queue_audit_context(context: AuditPipelineContext) -> AuditPipelineContext:
    """Repair sector/alert using catalog aliases, filename hints and Huawei metadata."""
    if context is None:
        raise ValueError("context is required")

    metadata = context.metadata or {}
    original_sector = context.sector_id
    original_alert = context.alert_id

    candidate_sector = _first_text(
        context.sector_id if not is_unknown_value(context.sector_id) else "",
        metadata.get("operator_sector_id"),
        metadata.get("sector_id"),
        metadata.get("setor"),
    ).lower()
    candidate_alert = _first_text(
        context.alert_id if not is_unknown_value(context.alert_id) else "",
        metadata.get("alert_id"),
        metadata.get("alerta_previsto"),
    )

    try:
        from core.classification import align_classification_with_catalog

        aligned = align_classification_with_catalog(
            {
                "sector_id": candidate_sector,
                "alert_id": candidate_alert,
                "alert_label": context.alert_label,
                "_filename": context.filename,
            }
        )
    except Exception as exc:
        logger.warning(
            "Falha ao reparar contexto de auditoria via catalogo (origin=%s filename=%s): %s",
            context.origin,
            context.filename,
            exc,
        )
        aligned = {}

    aligned_sector = _clean_text(aligned.get("sector_id")).lower()
    aligned_alert = _clean_text(aligned.get("alert_id"))
    aligned_label = _clean_text(aligned.get("alert_label"))

    if aligned_sector and not is_unknown_value(aligned_sector):
        if aligned_sector != context.sector_id:
            context.mark_repaired(f"sector:{context.sector_id or 'empty'}->{aligned_sector}")
        context.sector_id = aligned_sector
    elif candidate_sector and not is_unknown_value(candidate_sector):
        if candidate_sector != context.sector_id:
            context.mark_repaired(f"sector:{context.sector_id or 'empty'}->{candidate_sector}")
        context.sector_id = candidate_sector

    if aligned_alert and not is_unknown_value(aligned_alert):
        if aligned_alert != context.alert_id:
            context.mark_repaired(f"alert:{context.alert_id or 'empty'}->{aligned_alert}")
        context.alert_id = aligned_alert
    elif candidate_alert and not is_unknown_value(candidate_alert):
        if candidate_alert != context.alert_id:
            context.mark_repaired(f"alert:{context.alert_id or 'empty'}->{candidate_alert}")
        context.alert_id = candidate_alert

    if aligned_label and aligned_label != context.alert_label:
        context.alert_label = aligned_label

    if is_unknown_value(original_sector) and context.sector_id and not is_unknown_value(context.sector_id):
        context.mark_repaired("sector_recovered")
    if is_unknown_value(original_alert) and context.alert_id and not is_unknown_value(context.alert_id):
        context.mark_repaired("alert_recovered")

    return context


def apply_resolved_operator(
    context: Optional[AuditPipelineContext],
    resolved_operator: Optional[dict],
    *,
    fallback_operator_name: Optional[str] = None,
    fallback_operator_id: Optional[str] = None,
) -> None:
    if context is None or not resolved_operator:
        return
    resolved_name = _clean_text(resolved_operator.get("name")) or _clean_text(fallback_operator_name)
    resolved_id = (
        _clean_text(resolved_operator.get("matricula"))
        or _clean_text(resolved_operator.get("preferredId"))
        or _clean_text(fallback_operator_id)
    )
    if resolved_name and resolved_name != context.operator_name:
        context.mark_repaired(f"operator_name:{context.operator_name or 'empty'}->{resolved_name}")
        context.operator_name = resolved_name
    if resolved_id and resolved_id != context.operator_id:
        context.operator_id = resolved_id


def attach_pipeline_context_to_audio_quality(
    audio_quality: Optional[dict],
    pipeline_context: Any,
    *,
    transcription_metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    context = coerce_pipeline_context(pipeline_context)
    if context is None:
        return audio_quality

    merged = dict(audio_quality or {})
    audit_pipeline = context.to_audit_metadata()
    if transcription_metadata:
        audit_pipeline["transcription_strategy"] = {
            "selected_strategy": transcription_metadata.get("selected_strategy"),
            "selected_provider": transcription_metadata.get("selected_provider"),
            "selected_reason": transcription_metadata.get("selected_reason"),
        }
    merged["audit_pipeline"] = audit_pipeline
    return merged
