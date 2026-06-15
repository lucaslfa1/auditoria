import json
import unicodedata
from typing import Optional

from db.domain_constants import (
    AUDIT_SCOPES,
    AUDIT_SCOPE_CALL_QUALITY,
    AUDIT_STATUSES,
    DEFAULT_AUDIT_SCOPE,
    DEFAULT_AUDIT_STATUS,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_USER_ROLE,
    REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    REVIEW_QUEUE_PRIORITIES,
    REVIEW_QUEUE_QUERY_STATUSES,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    SOURCE_TYPES,
    USER_ROLES,
)
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


INVALID_AUDIO_QUALITY_THRESHOLD = 0.4
CALL_QUALITY_SCOPE = AUDIT_SCOPE_CALL_QUALITY


def json_dumps(value):
    return json.dumps(value) if value is not None else None


def json_loads(value, default=None):
    if value in (None, ""):
        return default
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        import logging
        logging.getLogger(__name__).warning("Failed to decode JSON: %s (value: %s)", exc, repr(value)[:100])
        return default


def get_row_value(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, 'keys'):
        return row[key] if key in row.keys() else default
    return default


def extract_returning_id(row) -> int:
    if row is None:
        raise ValueError("insert did not return an id")
    value = get_row_value(row, "id")
    if value is None:
        try:
            value = row[0]
        except (KeyError, IndexError, TypeError):
            value = row
    return int(value)


def normalize_lookup_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn")


def normalize_huawei_agent_id(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nan"}:
        return ""
    if "." in text:
        integer_part, decimal_part = text.split(".", 1)
        if integer_part.isdigit() and decimal_part and set(decimal_part) == {"0"}:
            return integer_part
    return text


def extract_audio_quality(row) -> Optional[dict]:
    parsed = json_loads(get_row_value(row, "audio_quality"), None)
    return parsed if isinstance(parsed, dict) else None


def is_invalid_audio_quality(audio_quality: Optional[dict]) -> bool:
    if not isinstance(audio_quality, dict):
        return False
    try:
        return float(audio_quality.get("score", 1.0)) < INVALID_AUDIO_QUALITY_THRESHOLD
    except (TypeError, ValueError):
        return False


def derive_audit_scope(source_type: Optional[str], audio_quality: Optional[dict]) -> str:
    return CALL_QUALITY_SCOPE


def get_audit_scope(row) -> str:
    stored_scope = normalize_audit_scope(get_row_value(row, "audit_scope"), default=None)
    if stored_scope == CALL_QUALITY_SCOPE:
        return stored_scope
    return CALL_QUALITY_SCOPE


def normalize_user_role(role: Optional[str], default: Optional[str] = DEFAULT_USER_ROLE) -> Optional[str]:
    normalized = str(role or "").strip().lower()
    if normalized in USER_ROLES:
        return normalized
    return default


def normalize_source_type(source_type: Optional[str], default: Optional[str] = DEFAULT_SOURCE_TYPE) -> Optional[str]:
    normalized = str(source_type or "").strip().lower()
    if normalized in SOURCE_TYPES:
        return normalized
    return default


def normalize_audit_scope(scope: Optional[str], default: Optional[str] = DEFAULT_AUDIT_SCOPE) -> Optional[str]:
    normalized = str(scope or "").strip().lower()
    if normalized in AUDIT_SCOPES:
        return normalized
    return default


def normalize_audit_status(status: Optional[str], default: Optional[str] = DEFAULT_AUDIT_STATUS) -> Optional[str]:
    normalized = str(status or "").strip().lower()
    if normalized in AUDIT_STATUSES:
        return normalized
    return default


def normalize_review_priority(
    priority: Optional[str],
    default: Optional[str] = REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
) -> Optional[str]:
    normalized = str(priority or "").strip().lower()
    if normalized in REVIEW_QUEUE_PRIORITIES:
        return normalized
    return default


def normalize_quality_reference(qualidade: Optional[str]) -> str:
    if not qualidade:
        return "indefinida"
    valor = qualidade.strip().lower()
    if valor in ("boa", "boas"):
        return "boa"
    if valor in ("ruim", "ruins"):
        return "ruim"
    if valor in ("zerada", "zeradas"):
        return "zerada"
    if valor in ("indefinida", "na", "n/a"):
        return "indefinida"
    return "indefinida"


def normalize_sector_id(value: Optional[str]) -> Optional[str]:
    """Normaliza id de setor (trim + minúsculas); vazio/None vira None."""
    normalized = str(value or "").strip().lower()
    return normalized or None


def normalize_review_status(status: Optional[str]) -> str:
    valor = str(status or REVIEW_QUEUE_STATUS_PENDING).strip().lower()
    legacy_aliases = {
        "classificado": REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
        "auditado": REVIEW_QUEUE_STATUS_AUDITED,
        "ignorado": REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
        "ready": REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    }
    valor = legacy_aliases.get(valor, valor)
    if valor in REVIEW_QUEUE_QUERY_STATUSES:
        return valor
    return REVIEW_QUEUE_STATUS_PENDING


def row_to_audit_result(row) -> Optional[AuditResult]:
    if not row:
        return None
    details = [AuditResultDetail(**detail) for detail in json.loads(row["details_json"])]
    transcription = [TranscriptionSegment(**segment) for segment in json.loads(row["transcription_json"])]
    ai_feedback = None
    try:
        ai_feedback = row["ai_feedback"] if "ai_feedback" in row.keys() else None
    except Exception:
        pass

    return AuditResult(
        score=row["score"],
        maxPossibleScore=row["max_score"],
        summary=row["summary"],
        details=details,
        transcription=transcription,
        operatorName=row["operator_name"],
        operatorId=row["operator_id"] or "",
        timestamp=row["timestamp"],
        input_hash=get_row_value(row, "input_hash"),
        source_type=normalize_source_type(row["source_type"], default=DEFAULT_SOURCE_TYPE),
        audit_scope=get_audit_scope(row),
        audio_quality=extract_audio_quality(row),
        audio_date=get_row_value(row, "audit_date"),
        ai_feedback=ai_feedback,
    )
