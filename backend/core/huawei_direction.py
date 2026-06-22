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
    """True se `endpoint` (caller/callee) corresponde ao ramal do agente `work_no`.

    Compara por texto e por dígitos, tolerando zeros à esquerda apenas quando
    AMBOS são curtos (<=6 dígitos, ramais internos) ou ambos longos. Evita
    casar um número externo só porque ele termina com os dígitos de um ramal.
    """
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
    """Converte um rótulo de direção variado para bool (ou None se irreconhecível).

    Aceita bool direto, ou strings/valores que, normalizados, batam com termos
    de entrada (true/1/sim/inbound/receptiva/...) -> True, ou de saída
    (false/0/nao/outbound/ativa/efetuada/...) -> False. Qualquer outra coisa
    devolve None. True = inbound/receptiva, False = outbound/efetuada.
    """
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


def infer_is_call_in_from_central(
    caller: Any, callee: Any, central_numbers: Optional[set] = None
) -> Optional[bool]:
    """Resolve a direção pelos números da CENTRAL quando rótulo/heurística falham.

    Regra (provada nos dados de prod): a central é a linha fixa da empresa (ex.:
    47 3481-6122 / 47 2101-6122 e ramais do mesmo bloco). Se a central é quem
    LIGOU (caller) -> ligação FEITA (outbound) -> False; se é quem RECEBEU
    (callee) -> RECEBIDA (inbound) -> True. Central nos dois lados (interna) ou
    em nenhum -> None (na dúvida, o chamador cai nas defesas seguintes). Isso
    cobre as ligações vindas só do manifesto OBS, que chegam sem `isCallIn`.

    `central_numbers`: dígitos canônicos (ex.: "4734816122"). Match por sufixo
    (em qualquer sentido) para tolerar DDI 55 e zero de tronco à esquerda.
    """
    central = {d for d in (_digits(n) for n in (central_numbers or set())) if len(d) >= 8}
    if not central:
        return None

    def _is_central(value: Any) -> bool:
        d = _digits(value)
        if len(d) < 8:
            return False
        return any(d.endswith(c) or c.endswith(d) for c in central)

    caller_central = _is_central(caller)
    callee_central = _is_central(callee)
    if caller_central == callee_central:
        return None
    return True if callee_central else False


def format_huawei_is_call_in(value: Optional[bool]) -> Optional[str]:
    """Serializa a direção booleana para a string que a Huawei usa.

    True -> "true" (inbound), False -> "false" (outbound), None -> None.
    Inverso de `coerce_huawei_is_call_in` para os casos canônicos.
    """
    if value is True:
        return "true"
    if value is False:
        return "false"
    return None


def is_brazilian_mobile(value: Any) -> bool:
    """Heurística: o número parece um celular brasileiro?

    Oitiva da BAS é, em regra, ligação para o celular do caminhoneiro; números
    policiais/institucionais são fixos ou códigos curtos (ex: 011190). Normaliza
    os dígitos, remove DDI 55 e zeros de tronco/operadora à esquerda e reconhece
    o 9º dígito do celular (DDD + 9 + 8 dígitos, ou 9 + 8 dígitos sem DDD).
    """
    digits = _digits(value)
    if not digits:
        return False
    if digits.startswith("55") and len(digits) >= 12:
        digits = digits[2:]
    digits = digits.lstrip("0")
    if len(digits) == 11 and digits[2] == "9":
        return True
    if len(digits) == 9 and digits[0] == "9":
        return True
    return False


def resolve_counterpart_number(payload: dict[str, Any]) -> Optional[str]:
    """Número da outra ponta da ligação (não o ramal do agente).

    Em ligação ativa (outbound) é o número discado (callee); em receptiva
    (inbound) é o número de origem (caller). Com direção desconhecida, devolve a
    ponta que NÃO casa com o ramal do agente (workNo), caindo no callee/caller.
    """
    caller = payload.get("callerNo") or payload.get("caller") or payload.get("caller_no") or payload.get("huawei_caller_no")
    callee = payload.get("calleeNo") or payload.get("called") or payload.get("callee_no") or payload.get("huawei_callee_no")
    work = payload.get("workNo") or payload.get("work_no") or payload.get("huawei_work_no") or payload.get("huawei_agent_id")

    direction = resolve_huawei_is_call_in(payload)
    if direction is False:
        return str(callee or "").strip() or None
    if direction is True:
        return str(caller or "").strip() or None

    if work:
        if _same_endpoint(caller, work) and not _same_endpoint(callee, work):
            return str(callee or "").strip() or None
        if _same_endpoint(callee, work) and not _same_endpoint(caller, work):
            return str(caller or "").strip() or None
    return str(callee or caller or "").strip() or None


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
