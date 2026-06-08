"""Matching quality report — analisa qualidade da vinculação audits ↔ colaboradores.

Compara operator_name das auditorias com nomes na tabela colaboradores,
gerando métricas de correspondência (exata, fuzzy, sem match).
"""

import unicodedata
from typing import Optional


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").strip().lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def get_matching_quality_report(
    get_connection,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> dict:
    """Gera relatório de qualidade de correspondência nome ↔ colaborador."""
    conn = get_connection()
    # conn.row_factory handled by DictCursor
    cursor = conn.cursor()

    # Build lookup
    cursor.execute("SELECT id, nome FROM colaboradores WHERE nome IS NOT NULL AND nome != ''")
    colab_names: dict[str, int] = {}
    for row in cursor.fetchall():
        key = _normalize(row["nome"])
        if key:
            colab_names[key] = row["id"]

    # Query audits
    where = ["a.operator_name IS NOT NULL", "a.operator_name != ''"]
    params: list = []

    if month:
        where.append("EXTRACT(MONTH FROM a.timestamp)::INTEGER = %s")
        params.append(month)
    if year:
        where.append("EXTRACT(YEAR FROM a.timestamp)::INTEGER = %s")
        params.append(year)

    sql = f"""
        SELECT DISTINCT a.operator_name, a.colaborador_id
        FROM audits a
        WHERE {' AND '.join(where)}
    """
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    exact_match = 0
    fk_linked = 0
    no_match = 0
    unmatched_names: list[str] = []

    for row in rows:
        name = row["operator_name"]
        has_fk = bool(row["colaborador_id"])

        if has_fk:
            fk_linked += 1
        elif _normalize(name) in colab_names:
            exact_match += 1
        else:
            no_match += 1
            if name not in unmatched_names:
                unmatched_names.append(name)

    total = len(rows)
    linked_total = fk_linked + exact_match

    return {
        "total_operadores_distintos": total,
        "vinculados_por_fk": fk_linked,
        "match_exato_por_nome": exact_match,
        "sem_correspondencia": no_match,
        "taxa_vinculacao_percent": round((linked_total / total * 100) if total > 0 else 0, 1),
        "nomes_sem_match": sorted(unmatched_names),
        "total_colaboradores": len(colab_names),
    }
