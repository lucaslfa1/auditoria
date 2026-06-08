from __future__ import annotations
"""Helpers for Huawei call direction inference.

The OBS Contact_Record manifest does not always expose the Huawei `isCallIn`
flag. These helpers keep the conservative caller/callee/workNo inference in
one place so discovery and sync paths cannot drift.
"""


import re
import unicodedata
from typing import Any, Optional

OUTBOUND_ONLY_RISK_SECTORS = {"uti", "bas", "distribuicao", "fenix", "transferencia"}
NON_TELEFONIA_SECTORS = {"celula_atendimento"}


def normalize_huawei_sector(value: Any) -> str:
    """Normalize HR/Telefonia sector names into automation rule ids."""

    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", str(value or "").strip().lower())
        if unicodedata.category(char) != "Mn"
    )
    normalized = " ".join(re.split(r"[\s_\-/]+", normalized) if normalized else [])
    if not normalized:
        return ""

    if normalized == "unilever" or "unilever" in normalized:
        return "logistica_unilever"
    if "celula" in normalized or normalized == "receptivo":
        return "celula_atendimento"
    if normalized.startswith("uti") or normalized == "grs" or normalized.startswith("grs "):
        return "uti"
    if "gerenciamento de risco" in normalized or "tratativa de incidentes" in normalized:
        return "uti"
    if normalized.startswith("bas") or normalized.startswith("base") or "sinistro" in normalized:
        return "bas"
    if "fenix" in normalized:
        return "fenix"
    if normalized.startswith("dist") or "distribuicao" in normalized:
        return "distribuicao"
    if (
        normalized.startswith("transfer")
        or normalized.startswith("rast")
        or "rastreamento" in normalized
        or "longo percurso" in normalized
    ):
        return "transferencia"
    return normalized


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _digits(value: Any) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def _strip_left_zeroes(value: str) -> str:
    return value.lstrip("0") or value


def _same_endpoint(endpoint: Any, work_no: Any) -> bool:
    endpoint_text = _clean_text(endpoint)
    work_text = _clean_text(work_no)
    if not endpoint_text or not work_text:
        return False
    if endpoint_text == work_text:
        return True

    endpoint_digits = _digits(endpoint_text)
    work_digits = _digits(work_text)
    if not endpoint_digits or not work_digits:
        return False
    if endpoint_digits == work_digits:
        return True

    # Allow harmless zero padding for short internal extensions, but avoid
    # suffix matching an external phone number that happens to end in a ramal.
    if len(endpoint_digits) <= 6 and len(work_digits) <= 6:
        return _strip_left_zeroes(endpoint_digits) == _strip_left_zeroes(work_digits)

    if len(endpoint_digits) > 6 and len(work_digits) > 6:
        return _strip_left_zeroes(endpoint_digits) == _strip_left_zeroes(work_digits)

    return False


def _looks_internal_endpoint(value: Any) -> bool:
    digits = _digits(value)
    return 2 <= len(digits) <= 6


def _looks_external_endpoint(value: Any) -> bool:
    digits = _digits(value)
    return len(digits) >= 8


def infer_huawei_is_call_in(caller_no: Any, callee_no: Any, work_no: Any) -> Optional[bool]:
    """Infer Huawei `isCallIn` from endpoint metadata.

    Return True for inbound/receptiva, False for outbound/efetuada, or None
    when the metadata is ambiguous.
    """

    caller_matches_work = _same_endpoint(caller_no, work_no)
    callee_matches_work = _same_endpoint(callee_no, work_no)

    if caller_matches_work and not callee_matches_work:
        return False
    if callee_matches_work and not caller_matches_work:
        return True
    if caller_matches_work and callee_matches_work:
        return None

    caller_known = bool(str(caller_no or "").strip())
    callee_known = bool(str(callee_no or "").strip())
    if not caller_known or not callee_known:
        return None

    caller_internal = _looks_internal_endpoint(caller_no)
    callee_internal = _looks_internal_endpoint(callee_no)
    caller_external = _looks_external_endpoint(caller_no)
    callee_external = _looks_external_endpoint(callee_no)

    if caller_internal and callee_external and not callee_internal:
        return False
    if callee_internal and caller_external and not caller_internal:
        return True

    return None


def coerce_huawei_is_call_in(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = normalize_huawei_sector(value)
    if not text:
        return None
    if text in {"true", "1", "sim", "yes", "y", "in", "inbound", "receptiva", "recebida", "entrada"}:
        return True
    if text in {"false", "0", "nao", "no", "n", "out", "outbound", "ativa", "efetuada", "realizada", "saida"}:
        return False
    return None


def resolve_huawei_is_call_in(payload: dict[str, Any]) -> Optional[bool]:
    """Resolve call direction, preferring endpoint evidence over query labels.

    `querycalls` often does not return `isCallIn`; the sync layer then adds it
    from the requested query direction. When a VDN row is merged with OBS
    manifest caller/callee/workNo data, endpoint evidence is more specific than
    that synthetic query label.
    """

    explicit_direction = None
    for key in (
        "huawei_is_call_in",
        "isCallIn",
        "is_call_in",
        "is_call_inbound",
        "callDirection",
        "call_direction",
        "direction",
    ):
        if key not in payload:
            continue
        explicit_direction = coerce_huawei_is_call_in(payload.get(key))
        if explicit_direction is not None:
            break

    inferred_direction = infer_huawei_is_call_in(
        payload.get("callerNo") or payload.get("caller") or payload.get("caller_no") or payload.get("huawei_caller_no"),
        payload.get("calleeNo") or payload.get("called") or payload.get("callee_no") or payload.get("huawei_callee_no"),
        payload.get("workNo") or payload.get("work_no") or payload.get("huawei_work_no") or payload.get("huawei_agent_id"),
    )
    if explicit_direction is not None:
        return explicit_direction
    return inferred_direction


def format_huawei_is_call_in(value: Optional[bool]) -> Optional[str]:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return None


def extract_is_call_in_from_response(data: Any) -> Optional[bool]:
    """Varre recursivamente uma resposta da Huawei (querydetailcallinfo/
    querybasiccallinfo) procurando o campo `isCallIn` em qualquer nivel e
    devolve True (inbound/receptiva), False (outbound/ativa) ou None.

    Defensivo: o formato exato dessas respostas ainda NAO foi validado contra a
    Huawei real (a auth so funciona em producao — ver script
    backend/scripts/diag_huawei_direcao_callid.py). Se nao achar um isCallIn
    reconhecivel, devolve None e o chamador deve cair nas defesas seguintes."""
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).strip().lower().replace("_", "") == "iscallin" and not isinstance(
                value, (dict, list)
            ):
                direction = coerce_huawei_is_call_in(value)
                if direction is not None:
                    return direction
        for value in data.values():
            direction = extract_is_call_in_from_response(value)
            if direction is not None:
                return direction
    elif isinstance(data, list):
        for item in data:
            direction = extract_is_call_in_from_response(item)
            if direction is not None:
                return direction
    return None
