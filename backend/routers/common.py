"""Helpers compartilhados entre os routers FastAPI da auditoria.

Reúne utilidades reaproveitadas por vários routers (classifier, supervisor,
review, etc.) para não duplicar lógica:

- Validação de upload por MIME (áudio x PDF) — ``resolve_upload_mime_type`` /
  ``ensure_supported_upload``.
- Autorização de supervisor sobre uma auditoria específica
  (``can_access_supervisor_audit`` / ``get_supervisor_audit_for_user``).
- Geração de senha temporária e sanitização de nome de arquivo para
  Content-Disposition.
- Registro best-effort de exportações de relatório (``safe_log_report_export``).

Sem custo de API paga: este módulo só faz validação em memória, geração de
strings e acesso a banco (PostgreSQL). Não chama Azure OpenAI/Speech.
"""

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
    """Extrai o nome de supervisor associado a um usuário autenticado.

    Usa ``supervisor_name`` se presente; senão cai para ``username``. Retorna
    string vazia se nenhum estiver disponível. Usado para filtrar/autorizar
    auditorias pelo supervisor dono.
    """
    return str(user.get("supervisor_name") or user.get("username") or "").strip()


def generate_temporary_password(length: int = 16) -> str:
    """Gera uma senha temporária aleatória criptograficamente forte.

    Usa ``secrets.choice`` sobre um alfabeto sem caracteres ambíguos (sem I/O/l/0/1).
    O comprimento efetivo é ``max(12, length)`` (mínimo de 12 caracteres).
    """
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
    """Indica se ``user`` pode acessar a auditoria ``audit``.

    Regra: admins (qualquer role != "supervisor") têm acesso total. Supervisores
    só acessam auditorias cujo campo ``supervisor`` casa (após normalização de
    lookup) com o seu próprio nome de supervisor.
    """
    if user.get("role") != "supervisor":
        return True
    return _normalize_auth_lookup(audit.get("supervisor", "")) == _normalize_auth_lookup(
        resolve_user_supervisor_name(user)
    )


def get_supervisor_audit_for_user(user: dict, audit_id: int) -> dict:
    """Busca uma auditoria por id aplicando a autorização de supervisor.

    Lê a auditoria no banco. Levanta HTTP 404 se ela não existir e HTTP 403 se
    o supervisor não tiver permissão (via ``can_access_supervisor_audit``).
    Retorna o dict da auditoria quando o acesso é permitido.
    """
    audit = audits.get_audit_by_id(database.get_connection, audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Auditoria não encontrada.")
    if not can_access_supervisor_audit(user, audit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a esta auditoria.")
    return audit


def resolve_upload_mime_type(upload_file: UploadFile) -> str:
    """Determina o MIME type efetivo de um upload.

    Primeiro tenta inferir pela extensão do nome do arquivo (via
    ``MIME_BY_EXTENSION``, mais confiável que o header do browser); se nenhuma
    extensão conhecida casar, cai para o ``content_type`` declarado no upload
    (sem o parâmetro ``;charset=...``, em minúsculas).
    """
    filename = (upload_file.filename or "").lower().strip()
    for extension, mime_type in MIME_BY_EXTENSION.items():
        if filename.endswith(extension):
            return mime_type
    return (upload_file.content_type or "").split(";", 1)[0].strip().lower()


def ensure_supported_upload(upload_file: UploadFile, *, allow_pdf: bool) -> str:
    """Valida o tipo do upload e retorna o MIME resolvido.

    Aceita sempre os formatos de áudio em ``SUPPORTED_AUDIO_MIME_TYPES``;
    quando ``allow_pdf=True``, aceita também PDF (``SUPPORTED_DOCUMENT_MIME_TYPES``).
    Levanta HTTP 400 com mensagem apropriada se o formato não for suportado
    (a mensagem muda conforme PDF seja permitido ou não).
    """
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
    """Estima o tamanho em bytes de um stream em memória (ex.: BytesIO).

    Tenta ``getbuffer().nbytes`` e depois ``getvalue()``. Retorna ``None`` se o
    objeto não expuser nenhum desses métodos ou se ocorrer qualquer erro
    (best-effort, usado só para logar o tamanho de exports).
    """
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
    """Registra uma exportação de relatório na trilha de auditoria (best-effort).

    Persiste em ``database.save_report_export`` os metadados do arquivo gerado
    (tipo, formato, nome, quem gerou, operador, alerta, setor, score, tamanho,
    etc.), extraindo campos do ``AuditResult`` quando fornecido.

    Efeito colateral: escrita no banco. Falhas são engolidas e apenas logadas em
    nível warning — nunca interrompem o download do relatório que está sendo
    servido ao usuário.
    """
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
