"""Contagens de cota mensal de auditorias por operador.

Estas funções só CONTAM; quem aplica o limite (2/operador/mês) são os
chamadores: sync Huawei (pré-filtro), automação e o endpoint de promoção.
Há duas réguas distintas:
- PRODUÇÃO (`get_operator_audit_count_for_month` / `_bulk`): conta auditorias
  do mês no escopo de qualidade, sem descartadas (inclui awaiting_pair).
- PAINEL (`get_supervisor_audit_count_for_month`): conta o que já OCUPA vaga no
  painel do supervisor (exclui awaiting_pair e descartadas) — é a régua do gate
  de promoção (commit 77299af5).

Extraído de `repositories/audits.py` (v1.3.145) sem mudança de comportamento;
os nomes seguem reexportados de `repositories.audits` (e patcháveis lá).
"""

from typing import Callable, Optional, Any

from db.domain_constants import AUDIT_STATUS_DISCARDED
from repositories.common import CALL_QUALITY_SCOPE
from repositories.audits_helpers import (
    _normalize_operator_name,
    _normalize_operator_id,
)


ConnectionFactory = Callable[[], Any]


def get_operator_audit_counts_for_month_bulk(
    get_connection: ConnectionFactory,
    operator_keys: list[tuple[str, str]],   # [(name, id), ...]
    year: int,
    month: int,
) -> dict[tuple[str, str], int]:
    """Retorna {(name_lower, id_lower): count} para todos os operadores em UMA query.

    Conta auditorias do mês no escopo de qualidade (`call_quality`) que não
    foram descartadas, deduplicando por uid composto (operador|timestamp|
    alerta|origem) para não contar re-auditorias do mesmo evento duas vezes.

    Parâmetros:
        operator_keys: pares (nome, id_telefonia) crus — são normalizados aqui.
        year/month: mês-calendário de referência (usa audit_date com fallback
            para timestamp).

    Retorno: dict com TODAS as chaves de entrada (operador sem auditoria
    aparece com 0, graças ao LEFT JOIN). Usado pelo sync Huawei para aplicar
    a cota em lote sem N+1 de queries.
    """
    if not operator_keys:
        return {}

    conn = get_connection()
    try:
        cursor = conn.cursor()
        date_start = f"{year:04d}-{month:02d}-01"
        date_end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"

        # Prepara chaves normalizadas para matching
        # Usamos uma CTE VALUES para fazer join com a tabela de auditorias
        from psycopg2.extras import execute_values

        # Filtramos para pegar apenas auditorias do mes/ano atual que nao foram descartadas
        # e estao no escopo de qualidade.
        # Identidade e baseada em operator_id (prioridade) ou operator_name.

        # Para facilitar o join, normalizamos as chaves de entrada
        normalized_keys = [
            (str(name or "").strip().lower(), str(oid or "").strip().lower())
            for name, oid in operator_keys
        ]

        # Note: A query de contagem aqui segue a mesma logica da get_operator_audit_count_for_month
        # mas agrupa por operador.
        # VALUES montado manualmente (via mogrify, que escapa cada par) por ser
        # mais seguro/previsível que execute_values em joins complexos com CTE.
        values_list = ",".join(cursor.mogrify("(%s, %s)", k).decode('utf-8') for k in normalized_keys)

        final_query = f"""
            WITH input_keys(search_name, search_id) AS (
                VALUES {values_list}
            ),
            relevant_audits AS (
                SELECT
                    LOWER(TRIM(COALESCE(operator_name, ''))) as op_name,
                    LOWER(TRIM(COALESCE(operator_id, ''))) as op_id,
                    CONCAT_WS(
                        '|',
                        COALESCE(NULLIF(TRIM(operator_id), ''), LOWER(TRIM(COALESCE(operator_name, '')))),
                        COALESCE(timestamp::text, ''),
                        COALESCE(alert_id, ''),
                        COALESCE(source_type, '')
                    ) as audit_uid
                FROM audits
                WHERE COALESCE(audit_date, timestamp) >= %s
                  AND COALESCE(audit_date, timestamp) < %s
                  AND COALESCE(audit_scope, %s) = %s
                  AND COALESCE(status, '') <> %s
            )
            SELECT
                ik.search_name,
                ik.search_id,
                COUNT(DISTINCT ra.audit_uid)
            FROM input_keys ik
            LEFT JOIN relevant_audits ra ON (
                (ik.search_id <> '' AND ra.op_id = ik.search_id)
                OR (ik.search_id = '' AND ra.op_id = '' AND ra.op_name = ik.search_name)
            )
            GROUP BY ik.search_name, ik.search_id
        """

        cursor.execute(final_query, (date_start, date_end, CALL_QUALITY_SCOPE, CALL_QUALITY_SCOPE, AUDIT_STATUS_DISCARDED))


        results = {}
        for row in cursor.fetchall():
            results[(row[0], row[1])] = int(row[2])
        return results
    finally:
        conn.close()


def get_operator_audit_count_for_month(
    get_connection: ConnectionFactory,
    operator_name: str,
    year: int,
    month: int,
    operator_id: Optional[str] = None,
) -> int:
    """Conta auditorias do mês para UM operador (escopo qualidade, sem descartadas).

    Delega para o bulk para manter consistência de critérios entre o caminho
    unitário (automação/telefonia) e o caminho em lote (sync Huawei).
    """
    counts = get_operator_audit_counts_for_month_bulk(
        get_connection,
        [(operator_name, operator_id)],
        year,
        month
    )
    key = (_normalize_operator_name(operator_name).lower() if operator_name else "",
           _normalize_operator_id(operator_id).lower() if operator_id else "")
    return counts.get(key, 0)


def get_supervisor_audit_count_for_month(
    get_connection: ConnectionFactory,
    operator_name: str,
    year: int,
    month: int,
    operator_id: Optional[str] = None,
) -> int:
    """Conta auditorias do operador visíveis no painel do supervisor no mês.

    Exclui `awaiting_pair` (ainda não enviadas) e `discarded` (soft-delete) —
    ou seja, conta o que já OCUPA vaga no painel. É esta contagem que o
    endpoint de promoção usa para aplicar o gate de cota 2/operador/mês
    (commit 77299af5): atingiu a cota, o auditor precisa deletar uma auditoria
    do painel para liberar espaço.

    Difere da contagem de `get_operator_audit_count_for_month` (cota de
    PRODUÇÃO de auditorias, inclui awaiting_pair): aqui a régua é o painel.
    """
    import calendar
    from datetime import date
    from db.domain_constants import AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_DISCARDED

    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])

    conn = get_connection()
    try:
        cursor = conn.cursor()
        op_id_norm = _normalize_operator_id(operator_id)
        op_name_norm = _normalize_operator_name(operator_name)

        query = """
            SELECT COUNT(*)
            FROM audits
            WHERE CAST(COALESCE(audit_date, timestamp) AS DATE) >= %s
              AND CAST(COALESCE(audit_date, timestamp) AS DATE) <= %s
              AND status NOT IN (%s, %s)
              AND (
                  (TRIM(COALESCE(operator_id, '')) <> '' AND TRIM(COALESCE(operator_id, '')) = %s)
                  OR
                  (TRIM(COALESCE(operator_id, '')) = '' AND LOWER(TRIM(COALESCE(operator_name, ''))) = LOWER(%s))
              )
        """
        cursor.execute(query, (start_date, end_date, AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_DISCARDED, op_id_norm, op_name_norm))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()
