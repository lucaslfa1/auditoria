"""Espelho de Arquivos Salvos — montagem do artefato por auditoria.

Lógica extraída de `db.database` (que segue como fachada fina): helpers que
montam nome de arquivo, conteúdo legível e metadata do Arquivo Salvo de cada
auditoria, mais o corpo síncrono da sincronização
(`_sync_arquivo_salvo_for_audit_inline`). Chamadas a funções que permanecem
na fachada são resolvidas em runtime via `db.database` (import tardio) para
evitar import circular e preservar monkeypatches dos testes.
CUSTO DE API: zero — nenhuma chamada a serviços pagos; somente PostgreSQL.
"""

import json
import logging
import unicodedata
from datetime import datetime, timezone
from typing import Optional, Any
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)
BRASILIA_TZ = ZoneInfo("America/Sao_Paulo")
SAVED_AUDIT_SOURCE_METADATA_KEYS = {
    "origem",
    "source_type",
    "classification_status",
    "huawei_call_id",
    "huawei_begin_time",
    "huawei_end_time",
    "huawei_duration",
    "huawei_is_call_in",
    "huawei_call_reason",
    "huawei_talk_reason",
    "huawei_talk_remark",
    "huawei_call_reason_code",
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


def _as_plain_dicts(items: Any) -> list[dict]:
    """Normaliza lista mista (modelos Pydantic ou dicts) em lista de dicts puros."""
    if not isinstance(items, list):
        return []
    normalized: list[dict] = []
    for item in items:
        if hasattr(item, "model_dump"):
            normalized.append(item.model_dump())
        elif isinstance(item, dict):
            normalized.append(dict(item))
    return normalized


def _json_safe_number(value: Any) -> Optional[float]:
    """Converte para float serializável em JSON; None se não numérico."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _slug_file_part(value: Any, fallback: str, max_len: int = 48) -> str:
    """Gera slug seguro para nome de arquivo (sem acentos/símbolos, '_' como separador)."""
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    parts: list[str] = []
    last_separator = False
    for char in normalized:
        if unicodedata.category(char) == "Mn":
            continue
        if char.isalnum():
            parts.append(char)
            last_separator = False
            continue
        if not last_separator and parts:
            parts.append("_")
            last_separator = True

    slug = "".join(parts).strip("_")
    if not slug:
        slug = fallback
    slug = slug[:max_len].rstrip("_")
    return slug or fallback


def _build_saved_audit_filename(audit: dict) -> str:
    """Nome do arquivo em Arquivos Salvos: Auditoria_<id>_<operador>_<alerta>.json."""
    audit_id = audit.get("id") or "sem_id"
    operator = _slug_file_part(audit.get("operator_name"), "operador")
    alert = _slug_file_part(audit.get("alert_label") or audit.get("alert_id"), "auditoria")
    if operator == "operador" and alert == "auditoria":
        return f"Auditoria_{audit_id}.json"
    return f"Auditoria_{audit_id}_{operator}_{alert}.json"


def _as_dict(value: Any) -> dict:
    """Coage dict ou string-JSON em dict; qualquer outra coisa vira {}."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _find_nested_value(value: Any, keys: tuple[str, ...], *, max_depth: int = 4) -> Any:
    """Busca recursiva da primeira chave preenchida em estruturas aninhadas (dicts/listas, até max_depth)."""
    if max_depth < 0:
        return None
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if candidate not in (None, ""):
                return candidate
        for nested in value.values():
            candidate = _find_nested_value(nested, keys, max_depth=max_depth - 1)
            if candidate not in (None, ""):
                return candidate
    elif isinstance(value, list):
        for nested in value:
            candidate = _find_nested_value(nested, keys, max_depth=max_depth - 1)
            if candidate not in (None, ""):
                return candidate
    return None


def _saved_audit_source_metadata(metadata: Optional[dict]) -> dict:
    """Filtra do metadata de origem só as chaves whitelisted para Arquivos Salvos (SAVED_AUDIT_SOURCE_METADATA_KEYS)."""
    source = _as_dict(metadata)
    return {
        key: value
        for key, value in source.items()
        if key in SAVED_AUDIT_SOURCE_METADATA_KEYS and value not in (None, "")
    }


def _coerce_saved_audit_call_iso(value: Any) -> Optional[str]:
    """Normaliza o horário da ligação para ISO (aceita epoch ms/s ou string ISO)."""
    if value in (None, ""):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    if raw.lstrip("-").isdigit():
        try:
            number = int(raw)
        except (TypeError, ValueError):
            return None
        if number <= 0:
            return None
        seconds = number / 1000.0 if number > 10_000_000_000 else float(number)
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(BRASILIA_TZ).isoformat(timespec="seconds")
        except (OverflowError, OSError, ValueError):
            return None

    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return raw

    normalized = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if dt.tzinfo is not None:
        dt = dt.astimezone(BRASILIA_TZ)
    return dt.isoformat(timespec="seconds")


def _saved_audit_call_timestamp(audit: dict, source_metadata: Optional[dict] = None, existing_metadata: Optional[dict] = None) -> Optional[str]:
    """Resolve o horário da LIGAÇÃO (não da auditoria): Huawei begin_time primeiro, depois fallbacks do audit."""
    metadata_candidates = [
        _as_dict(source_metadata),
        _as_dict(audit.get("source_metadata")),
        _as_dict(audit.get("metadata")),
        _as_dict(audit.get("audio_quality")),
    ]

    huawei_begin_time = _find_nested_value(
        metadata_candidates,
        ("huawei_begin_time", "begin_time"),
    )
    call_timestamp = _coerce_saved_audit_call_iso(huawei_begin_time)
    if call_timestamp:
        return call_timestamp

    existing = _as_dict(existing_metadata)
    for candidate in (
        audit.get("call_started_at"),
        existing.get("call_started_at"),
        audit.get("audio_date"),
        existing.get("audio_date"),
        audit.get("timestamp"),
    ):
        call_timestamp = _coerce_saved_audit_call_iso(candidate)
        if call_timestamp:
            return call_timestamp
    return None


def _format_saved_audit_call_timestamp(value: Optional[str]) -> str:
    """Formata o horário da ligação para exibição (dd/mm/aaaa hh:mm em horário de Brasília)."""
    if not value:
        return ""
    normalized = str(value).strip().replace("Z", "+00:00")
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return str(value).strip()
        return dt.strftime("%d/%m/%Y")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return str(value).strip()
    if dt.tzinfo is not None:
        dt = dt.astimezone(BRASILIA_TZ)
    return dt.strftime("%d/%m/%Y %H:%M")


def _build_saved_audit_content(audit: dict, source_metadata: Optional[dict] = None, existing_metadata: Optional[dict] = None) -> str:
    """Monta o texto legível do Arquivo Salvo (data da ligação, resumo, feedback e critérios)."""
    summary = str(audit.get("summary") or "").strip()
    ai_feedback = str(audit.get("ai_feedback") or "").strip()
    details = _as_plain_dicts(audit.get("details"))

    sections: list[str] = []
    call_timestamp = _saved_audit_call_timestamp(audit, source_metadata, existing_metadata)
    call_timestamp_label = _format_saved_audit_call_timestamp(call_timestamp)
    if call_timestamp_label:
        sections.append(f"Data/hora da ligação\n{call_timestamp_label}")
    if summary:
        sections.append(f"Resumo da auditoria\n{summary}")
    if ai_feedback:
        sections.append(f"Feedback ao operador\n{ai_feedback}")
    if details:
        detail_lines = []
        for detail in details:
            status = str(detail.get("status") or "na").strip()
            label = str(detail.get("label") or "").strip()
            comment = str(detail.get("comment") or "").strip() or "Sem justificativa"
            if label:
                detail_lines.append(f"[{status}] {label}: {comment}")
        if detail_lines:
            sections.append("Critérios avaliados\n" + "\n".join(detail_lines))

    return "\n\n".join(sections).strip() or summary


def _build_saved_audit_metadata(audit: dict, source_metadata: Optional[dict] = None, existing_metadata: Optional[dict] = None) -> dict:
    """Monta o metadata estruturado do Arquivo Salvo (ids, status, score, origem, timestamps)."""
    saved_filename = _build_saved_audit_filename(audit)
    original_filename = str(audit.get("audio_original_filename") or "").strip()
    audit_timestamp = audit.get("timestamp")
    call_timestamp = _saved_audit_call_timestamp(audit, source_metadata, existing_metadata)
    normalized_source_metadata = _saved_audit_source_metadata(source_metadata)
    return {
        "kind": "audit",
        "audit_id": audit.get("id"),
        "saved_filename": saved_filename,
        "audit_status": audit.get("status"),
        "summary": audit.get("summary") or "",
        "ai_feedback": audit.get("ai_feedback") or "",
        "score": _json_safe_number(audit.get("score")),
        "maxPossibleScore": _json_safe_number(audit.get("max_score")),
        "details": _as_plain_dicts(audit.get("details")),
        "transcription": _as_plain_dicts(audit.get("transcription")),
        "source_type": audit.get("source_type"),
        "timestamp": call_timestamp or audit_timestamp,
        "audio_date": call_timestamp or audit.get("audio_date"),
        "call_started_at": call_timestamp,
        "audit_timestamp": audit_timestamp,
        "source_metadata": normalized_source_metadata,
        "operator_id": audit.get("operator_id") or "",
        "operator_name": audit.get("operator_name") or "",
        "sector_id": audit.get("sector_id") or "",
        "alert_id": audit.get("alert_id") or "",
        "alert_label": audit.get("alert_label") or "",
        "audio_original_filename": original_filename,
        "source_filename": original_filename or saved_filename,
    }


def _sync_arquivo_salvo_for_audit_inline(audit_id: int, *, criado_por: str = "") -> bool:
    """Synchronous body of the saved_files sync.

    Public dispatcher is `_sync_arquivo_salvo_for_audit` (queued in production,
    inline under tests). This function performs the actual DB work and is what
    the background worker calls; it is also reused by the inline fallback when
    the worker queue is full.
    """
    from db import database as dbm
    from repositories import audits
    audit = audits.get_audit_by_id(dbm.get_connection, audit_id)
    if not audit:
        logger.warning(
            "Sincronizacao de arquivo salvo ignorada: auditoria %s nao encontrada.",
            audit_id,
        )
        return False

    try:
        from repositories.saved_files import (
            get_arquivo_by_audit_id as repo_get_arquivo,
            update_arquivo_by_audit_id as repo_update_arquivo,
            save_arquivo as repo_save_arquivo,
        )

        existing = repo_get_arquivo(dbm.get_connection, audit_id)
        existing_metadata = _as_dict(existing.get("metadata") if existing else None)
        try:
            queue_item = dbm.obter_fila_revisao_classificacao_por_auditoria(
                audit_id,
                audit.get("input_hash") or None,
            )
        except Exception as queue_exc:
            logger.warning(
                "Nao foi possivel carregar metadata da fila para auditoria %s: %s",
                audit_id,
                queue_exc,
            )
            queue_item = None
        source_metadata = _as_dict((queue_item or {}).get("metadata"))

        content = _build_saved_audit_content(audit, source_metadata, existing_metadata)
        score = audit.get("score")
        filename = _build_saved_audit_filename(audit)
        metadata = _build_saved_audit_metadata(audit, source_metadata, existing_metadata)
        data_analise = metadata.get("call_started_at") or metadata.get("audio_date") or metadata.get("timestamp")

        if existing:
            return repo_update_arquivo(
                dbm.get_connection,
                audit_id,
                content,
                score=score,
                metadata=metadata,
                arquivo=filename,
                data_analise=data_analise,
                criado_por=criado_por or None,
            )
        else:
            saved_id = repo_save_arquivo(
                dbm.get_connection,
                tipo="auditoria",
                conteudo=content,
                arquivo=filename,
                audit_id=audit_id,
                operator_name=audit.get("operator_name", ""),
                sector_id=audit.get("sector_id", ""),
                alert_label=audit.get("alert_label", ""),
                score=score,
                metadata=metadata,
                criado_por=criado_por,
                data_analise=data_analise
            )
            return bool(saved_id)
    except Exception as exc:
        logger.exception("Erro ao sincronizar rascunho de auditoria %s: %s", audit_id, exc)
        return False
