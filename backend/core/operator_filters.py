"""Filtros para distinguir operadores reais de contas técnicas/operações
excluídas no cadastro e na integração de telefonia (Huawei).

Usado para decidir quem é auditável: operações terceirizadas/sem auditoria
(``EXCLUDED_OPERATION_TERMS``) e contas técnicas da telefonia (filas de
contenção, agentes sem nome com apenas metadata de telefonia) são filtradas
para fora da auditoria. Toda comparação é feita sobre texto normalizado
(sem acento, minúsculo, espaços colapsados).

Sem custo de API (só CPU).
"""
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
    """Normaliza texto para comparação de filtros: minúsculo, sem acentos
    (decomposição NFD removendo marcas), com espaços internos colapsados em um.
    Aceita qualquer valor (``None`` vira string vazia)."""
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", without_accents)


def is_excluded_operation_values(*values: Any) -> bool:
    """Retorna ``True`` se algum dos valores informados (nome, operação, etc.)
    contiver um termo de operação excluída da auditoria (ver
    ``EXCLUDED_OPERATION_TERMS``: profarma, sanofi, tora pa, etc.).

    Os valores são normalizados e concatenados antes da busca por substring.
    Sem efeitos colaterais.
    """
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
    """Detecta contas técnicas/de serviço da telefonia (não-operadores reais),
    que não devem ser tratadas como colaboradores auditáveis.

    Considera técnica quando:
    - é uma fila de "contenção" sem identidade de operador (sem matrícula nem
      supervisor) — nome ou conta de telefonia igual/começando com "contencao"; ou
    - é um serviço de telefonia sem nome, mas com algum metadado de telefonia
      (conta, organização, tipo de agente, status, id ou softphone).

    Todos os parâmetros são keyword-only e opcionais. Sem efeitos colaterais.
    """
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
