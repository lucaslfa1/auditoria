from typing import Any, Optional, Dict, List
import re
import unicodedata
from collections import defaultdict
import logging

from core.huawei_discovery import HuaweiDiscoveryService

from core.automation_rules import get_call_duration_seconds
from repositories.common import normalize_huawei_agent_id

_DURATION_KEYS = ("duration", "callDuration", "huawei_duration")

logger = logging.getLogger(__name__)

def _slug_filename_part(value: Any, fallback: str, max_len: int = 64) -> str:
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

def _call_duration_is_known(interacao: dict) -> bool:
    for key in _DURATION_KEYS:
        value = interacao.get(key)
        if value in (None, ""):
            continue
        try:
            int(float(str(value).strip()))
            return True
        except (TypeError, ValueError):
            continue

    start = (
        HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("callBegin"))
        or HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("beginTime"))
        or HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("ackBegin"))
        or HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("waitBegin"))
    )
    end = (
        HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("callEnd"))
        or HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("endTime"))
        or HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("logDate"))
    )
    return start is not None and end is not None and end >= start

def _clean_huawei_operator_id(value: Any) -> str:
    return normalize_huawei_agent_id(value)

def _obs_prefix_candidates(interacao: dict, agent_id: Any) -> list[str]:
    caller_no = interacao.get("callerNo")
    if not _clean_obs_prefix(caller_no):
        caller_no = interacao.get("caller_no")
    callee_no = interacao.get("calleeNo")
    if not _clean_obs_prefix(callee_no):
        callee_no = interacao.get("callee_no")
    raw_candidates = [
        caller_no,
        callee_no,
        agent_id,
        interacao.get("workNo"),
    ]
    prefixes: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        prefix = _clean_obs_prefix(raw)
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        prefixes.append(prefix)
    return prefixes

def _obs_match_ids(interacao: dict, call_id: str) -> list[str]:
    call_id_text = _clean_obs_prefix(call_id)
    call_id_parts = call_id_text.split("-")
    call_id_suffix = (
        call_id_parts[-1]
        if len(call_id_parts) > 1 and all(part.isdigit() for part in call_id_parts)
        else ""
    )
    raw_candidates = [
        call_id_text,
        call_id_suffix,
        interacao.get("recordId"),
        interacao.get("recordID"),
        interacao.get("record_id"),
        interacao.get("contactId"),
        interacao.get("contact_id"),
        interacao.get("callSerialno"),
        interacao.get("callSerialNo"),
        interacao.get("call_no"),
        interacao.get("callNo"),
    ]
    match_ids: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        value = _clean_obs_prefix(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        match_ids.append(value)
    return match_ids

def _download_id_candidates(interacao: dict, call_id: str) -> list[str]:
    """IDs que podem resolver midia na Huawei/OBS, em ordem de menor risco."""
    return _obs_match_ids(interacao, call_id)

def _clean_obs_prefix(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text

def _download_candidate_sort_key(interacao: dict) -> tuple[int, int, int]:
    # Chamadas com recordId preenchido tendem a resolver mais rapido no OBS/FS.
    # As sem recordId ainda sao tentadas, porque a VDN pode omitir esse campo
    # mesmo quando o Contact_Record ou o objeto Voice existe.
    record_id = str(interacao.get("recordId") or "").strip()
    return (
        1 if record_id else 0,
        get_call_duration_seconds(interacao),
        HuaweiDiscoveryService._coerce_huawei_time_ms(interacao.get("beginTime")) or 0,
    )

def _make_filename(op_nome: str, call_id: str, extensao: str) -> str:
    operator_name = str(op_nome or "").strip()
    if _normalize_identity_text(operator_name) == "nao identificado":
        operator_part = "operador_nao_identificado"
    else:
        operator_part = _slug_filename_part(operator_name, "operador")
    call_part = _slug_filename_part(call_id, "call", max_len=48)
    extension = _slug_filename_part(extensao, "wav", max_len=12)
    return f"ligacao_huawei_{operator_part}_{call_part}.{extension}"

def _resolve_call_key(chamada: dict) -> str:
    return str(
        chamada.get("callId")
        or chamada.get("callid")
        or chamada.get("id")
        or ""
    ).strip()


def _normalize_identity_text(value: Any) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return " ".join(part for part in normalized.replace("_", " ").split() if part)

