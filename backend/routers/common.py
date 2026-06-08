from __future__ import annotations

import logging
import re
import secrets

from fastapi import HTTPException, UploadFile, status

import db.database as database
from repositories import audits
from routers.auth import _normalize_auth_lookup
from schemas import AuditResult

logger = logging.getLogger(__name__)


SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/mpeg",
    "audio/mp3",
    "audio/ogg",
    "audio/webm",
    "audio/mp4",
    "audio/x-m4a",
}
SUPPORTED_DOCUMENT_MIME_TYPES = {"application/pdf"}
MIME_BY_EXTENSION = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".m4a": "audio/mp4",
    ".pdf": "application/pdf",
}


def resolve_user_supervisor_name(user: dict) -> str:
    return str(user.get("supervisor_name") or user.get("username") or "").strip()


def generate_temporary_password(length: int = 16) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%*?"
    return "".join(secrets.choice(alphabet) for _ in range(max(12, length)))


def _safe_filename(name: str, fallback: str = "arquivo") -> str:
    """Sanitiza uma string para uso seguro em Content-Disposition filename.

    Por que isso importa:
      O header HTTP Content-Disposition: attachment; filename="..." usa aspas.
      Se 'name' contiver '"', newline ou outros caracteres de controle, o browser
      pode interpretar erroneamente o header (header injection).

    A regex abaixo mantém apenas: letras, números, ponto, hífen e underscore.
    Qualquer outro caractere é substituído por '_'.
    """
    safe = re.sub(r'[^\w.\-]', '_', str(name or fallback))
    return safe or fallback




def can_access_supervisor_audit(user: dict, audit: dict) -> bool:
    if user.get("role") != "supervisor":
        return True
    return _normalize_auth_lookup(audit.get("supervisor", "")) == _normalize_auth_lookup(
        resolve_user_supervisor_name(user)
    )


def get_supervisor_audit_for_user(user: dict, audit_id: int) -> dict:
    audit = audits.get_audit_by_id(database.get_connection, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditoria não encontrada.")
    if not can_access_supervisor_audit(user, audit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a esta auditoria.")
    return audit


def resolve_upload_mime_type(upload_file: UploadFile) -> str:
    filename = (upload_file.filename or "").lower().strip()
    for extension, mime_type in MIME_BY_EXTENSION.items():
        if filename.endswith(extension):
            return mime_type
    return (upload_file.content_type or "").split(";", 1)[0].strip().lower()


def ensure_supported_upload(upload_file: UploadFile, *, allow_pdf: bool) -> str:
    mime_type = resolve_upload_mime_type(upload_file)
    supported_types = SUPPORTED_AUDIO_MIME_TYPES | (SUPPORTED_DOCUMENT_MIME_TYPES if allow_pdf else set())
    if mime_type in supported_types:
        return mime_type

    if allow_pdf:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato de arquivo não suportado. Envie áudio (WAV, MP3, M4A, OGG, WEBM) ou PDF.",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Formato de arquivo não suportado para triagem. Envie apenas áudio (WAV, MP3, M4A, OGG, WEBM).",
    )


def estimate_stream_size(stream) -> int | None:
    try:
        if hasattr(stream, "getbuffer"):
            return int(stream.getbuffer().nbytes)
        if hasattr(stream, "getvalue"):
            return len(stream.getvalue())
    except Exception:
        return None
    return None


def safe_log_report_export(
    *,
    report_kind: str,
    file_format: str,
    filename: str,
    media_type: str,
    user: dict,
    result: AuditResult | None = None,
    alert_id: str | None = None,
    alert_label: str | None = None,
    sector_id: str | None = None,
    file_size_bytes: int | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        database.save_report_export(
            report_kind=report_kind,
            file_format=file_format,
            filename=filename,
            media_type=media_type,
            generated_by=str(user.get("username", "")),
            operator_name=str(getattr(result, "operatorName", "") or ""),
            operator_id=str(getattr(result, "operatorId", "") or ""),
            alert_id=str(alert_id or ""),
            alert_label=str(alert_label or ""),
            sector_id=str(sector_id or ""),
            score=getattr(result, "score", None) if result else None,
            max_score=getattr(result, "maxPossibleScore", None) if result else None,
            source_type=str(getattr(result, "source_type", "") or "") if result else "",
            audit_timestamp=str(getattr(result, "timestamp", "") or "") if result else "",
            file_size_bytes=file_size_bytes,
            metadata=metadata or {},
        )
    except Exception as exc:
        logger.warning("Report export log warning: %s", exc)
