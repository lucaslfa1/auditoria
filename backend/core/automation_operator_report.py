"""Relatório de leitura: auditorias do mês por operador (painel de Automação).

Monta a lista que a tela de Automação mostra abaixo do total do mês: para cada
operador auditável que a coleta realmente tenta baixar (ativo, auditável, com
`id_huawei`), quantas auditorias ele já teve no mês corrente frente à cota mensal.

Papel no fluxo: serviço somente-leitura, sem custo de API. Junta três fontes já
existentes — o roster (`operators.listar_auditaveis_com_id_huawei`), a contagem em
lote (`get_operator_audit_counts_for_month_bulk`, uma query só) e a cota
(`_get_monthly_audit_quota`). Não aplica nem altera nenhuma regra de negócio; só
exibe contagem × cota.

Ponto sensível (verificado no banco real em 2026-06-30): `audits.operator_id` guarda
a MATRÍCULA do operador (ex.: `11123`), não `id_telefonia`/`id_huawei`. Por isso a
chave de contagem é `(nome, matrícula)` — casar por outro id zeraria a contagem.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Callable, Optional

from repositories import operators
from repositories.audits_quota import get_operator_audit_counts_for_month_bulk
from core.automation_config import _get_monthly_audit_quota

_SP_TZ = ZoneInfo("America/Sao_Paulo")


def build_operadores_mes(
    get_connection: Callable[[], Any],
    *,
    agora: Optional[datetime] = None,
) -> dict:
    """Monta `{mes, cota, operadores[]}` para o painel de auditorias por operador.

    `agora` (default: agora em São Paulo) define o mês de referência; é injetável
    para tornar os testes determinísticos. Cada item de `operadores` traz
    `{nome, setor, operator_id (matrícula), auditorias_mes, cheio}`, ordenado por
    `auditorias_mes` desc e depois nome. `cheio = auditorias_mes >= cota`.

    Efeito colateral: leitura de banco (roster + contagem em lote). Não escreve.
    """
    agora = agora or datetime.now(_SP_TZ)
    year, month = agora.year, agora.month

    roster = operators.listar_auditaveis_com_id_huawei(get_connection)

    # Chave (nome, matrícula) normalizada igual ao bulk (`strip().lower()`), para
    # bater com as chaves que ele devolve no dict de contagens.
    keys: list[tuple[str, str]] = []
    meta_by_norm: dict[tuple[str, str], dict] = {}
    for op in roster:
        nome = str(op.get("nome") or "").strip()
        matricula = str(op.get("matricula") or "").strip()
        keys.append((nome, matricula))
        norm = (nome.lower(), matricula.lower())
        meta_by_norm.setdefault(
            norm,
            {
                "nome": nome,
                "setor": str(op.get("setor") or "").strip(),
                "operator_id": matricula,
            },
        )

    counts = (
        get_operator_audit_counts_for_month_bulk(get_connection, keys, year, month)
        if keys
        else {}
    )
    cota = _get_monthly_audit_quota()

    operadores = []
    for norm, meta in meta_by_norm.items():
        n = int(counts.get(norm, 0) or 0)
        operadores.append(
            {
                "nome": meta["nome"],
                "setor": meta["setor"],
                "operator_id": meta["operator_id"],
                "auditorias_mes": n,
                "cheio": n >= cota,
            }
        )

    operadores.sort(key=lambda o: (-o["auditorias_mes"], o["nome"].lower()))

    return {
        "mes": f"{year:04d}-{month:02d}",
        "cota": cota,
        "operadores": operadores,
    }
