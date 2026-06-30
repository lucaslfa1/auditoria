"""Initial-month coverage helpers for Huawei operator selection.

These helpers are pure: they do not read the database or call Huawei. The sync
orchestrator passes the monthly audit counts in, and the helpers compute how many
audits each operator still needs before the early-month minimum is satisfied.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

ChaveCoberturaOperador = tuple[str, str]


def _text(value: Any) -> str:
    return str(value or "").strip()


def chave_operador_cobertura(operador: dict) -> ChaveCoberturaOperador:
    """Key used by audit quota counts: operator name + matricula.

    Production `audits.operator_id` stores matricula, not Huawei id. Keeping the
    same key as the UI panel avoids a coverage mismatch between display and sync.
    """

    nome = _text(operador.get("nome") or operador.get("name")).lower()
    matricula = _text(operador.get("matricula") or operador.get("operator_matricula")).lower()
    return nome, matricula


def chaves_operadores_cobertura(operadores: list[dict]) -> list[tuple[str, str]]:
    """Raw keys for `get_operator_audit_counts_for_month_bulk`."""

    return [
        (
            _text(operador.get("nome") or operador.get("name")),
            _text(operador.get("matricula") or operador.get("operator_matricula")),
        )
        for operador in operadores
    ]


def cobertura_inicial_ativa(
    agora: datetime,
    *,
    dias_iniciais: int,
    minimo_por_operador: int,
    divida_total: int = 0,
) -> bool:
    """Whether coverage prioritization should keep running.

    The first days are the critical window. After that, any remaining coverage
    debt keeps the focus active until every operator reaches the minimum.
    """

    dias = int(dias_iniciais or 0)
    minimo = int(minimo_por_operador or 0)
    if dias <= 0 or minimo <= 0:
        return False
    return agora.day <= dias or int(divida_total or 0) > 0


def calcular_dividas_cobertura(
    operadores: list[dict],
    contagens_mes: dict[ChaveCoberturaOperador, int],
    *,
    minimo_por_operador: int,
) -> dict[ChaveCoberturaOperador, int]:
    """Return how many audits each operator still needs to hit the minimum."""

    minimo = max(1, int(minimo_por_operador or 1))
    dividas: dict[ChaveCoberturaOperador, int] = {}
    for operador in operadores:
        chave = chave_operador_cobertura(operador)
        if not any(chave):
            continue
        atual = int(contagens_mes.get(chave, 0) or 0)
        dividas[chave] = max(0, minimo - atual)
    return dividas


def divida_cobertura_operador(operador: dict, dividas: dict[ChaveCoberturaOperador, int]) -> int:
    """Coverage debt for a resolved operator dict."""

    return int(dividas.get(chave_operador_cobertura(operador), 0) or 0)


def teto_por_cobertura(teto_por_operador: int, divida: int) -> int:
    """During coverage, cap an under-covered operator at its remaining debt.

    `0` still means unlimited for covered operators. For under-covered operators,
    unlimited would let one person consume many slots before peers get their two
    calls, so the effective cap becomes exactly the remaining debt.
    """

    divida = max(0, int(divida or 0))
    teto = max(0, int(teto_por_operador or 0))
    if divida <= 0:
        return teto
    if teto == 0:
        return divida
    return min(teto, divida)
