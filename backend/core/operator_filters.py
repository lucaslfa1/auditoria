import re
import unicodedata
from typing import Any


EXCLUDED_OPERATION_TERMS = (
    "comandolog",
    "gestao e coordenacao",
    "operacao profarma",
    "profarma",
    "operacao tora pa",
    "tora pa",
    "operacao tora",
    "tora",
    "sanofi",
)


def normalize_filter_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents)


def is_excluded_operation_values(*values: Any) -> bool:
    text = " ".join(normalize_filter_text(value) for value in values if value is not None)
    if not text:
        return False
    return any(term in text for term in EXCLUDED_OPERATION_TERMS)


def is_technical_telephony_values(
    *,
    nome: Any = "",
    matricula: Any = "",
    supervisor: Any = "",
    telefonia_account: Any = "",
    organizacao_telefonia: Any = "",
    tipo_agente: Any = "",
    status_telefonia: Any = "",
    id_telefonia: Any = "",
    softphone_number: Any = "",
) -> bool:
    normalized_name = normalize_filter_text(nome)
    normalized_account = normalize_filter_text(telefonia_account)
    has_operator_identity = bool(str(matricula or "").strip() or str(supervisor or "").strip())
    has_telephony_metadata = any(
        str(value or "").strip()
        for value in (
            telefonia_account,
            organizacao_telefonia,
            tipo_agente,
            status_telefonia,
            id_telefonia,
            softphone_number,
        )
    )

    is_contencao_service = (
        not has_operator_identity
        and (
            normalized_name == "contencao"
            or normalized_name.startswith("contencao ")
            or normalized_account == "contencao"
            or normalized_account.startswith("contencao ")
        )
    )
    is_nameless_telephony_service = not normalized_name and has_telephony_metadata
    return is_contencao_service or is_nameless_telephony_service
