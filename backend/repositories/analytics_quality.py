"""Indicadores de qualidade — queries analíticas sobre auditorias.

Módulo puramente extrativo: agrega dados já existentes no banco.
Nenhum peso, fórmula ou regra de negócio é inventada aqui.
Tudo vem dos resultados de auditoria já calculados pelo sistema.
"""

from typing import Optional

from db.domain_constants import AUDIT_STATUS_APPROVED


def get_indicators_by_sector(
    get_connection,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> list[dict]:
    """Média e total de auditorias por setor no período."""
    conn = get_connection()
    try:
        
        c = conn.cursor()

        where = ["a.status = %s"]
        params: list = [AUDIT_STATUS_APPROVED]

        if month:
            where.append("EXTRACT(MONTH FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(month)
        if year:
            where.append("EXTRACT(YEAR FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(year)

        sql = f"""
            SELECT
                a.sector_id,
                s.label AS sector_label,
                COUNT(*) AS total_auditorias,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE 0 END)::NUMERIC, 1) AS media_percentual,
                ROUND(AVG(a.score)::NUMERIC, 2) AS media_nota,
                ROUND(AVG(a.max_score)::NUMERIC, 2) AS media_max
            FROM audits a
            LEFT JOIN audit_sectors s ON s.id = a.sector_id
            WHERE {' AND '.join(where)}
            GROUP BY a.sector_id, s.label
            ORDER BY media_percentual DESC
        """
        c.execute(sql, params)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def get_indicators_by_supervisor(
    get_connection,
    month: Optional[int] = None,
    year: Optional[int] = None,
    sector_id: Optional[str] = None,
) -> list[dict]:
    """Média e total de auditorias por supervisor no período."""
    conn = get_connection()
    try:
        
        c = conn.cursor()

        where = ["a.status = %s"]
        params: list = [AUDIT_STATUS_APPROVED]

        if month:
            where.append("EXTRACT(MONTH FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(month)
        if year:
            where.append("EXTRACT(YEAR FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(year)
        if sector_id:
            where.append("a.sector_id = %s")
            params.append(sector_id)

        sql = f"""
            SELECT
                COALESCE(col.supervisor, 'N/A') AS supervisor,
                COUNT(*) AS total_auditorias,
                COUNT(DISTINCT a.operator_name) AS total_operadores,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE 0 END)::NUMERIC, 1) AS media_percentual
            FROM audits a
            LEFT JOIN colaboradores col ON col.nome = a.operator_name
            WHERE {' AND '.join(where)}
            GROUP BY supervisor
            ORDER BY media_percentual DESC
        """
        c.execute(sql, params)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def get_indicators_by_operator(
    get_connection,
    month: Optional[int] = None,
    year: Optional[int] = None,
    sector_id: Optional[str] = None,
    supervisor: Optional[str] = None,
) -> list[dict]:
    """Nota por operador no período (dados brutos para o Planejamento)."""
    conn = get_connection()
    try:
        
        c = conn.cursor()

        where = ["a.status = %s"]
        params: list = [AUDIT_STATUS_APPROVED]

        if month:
            where.append("EXTRACT(MONTH FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(month)
        if year:
            where.append("EXTRACT(YEAR FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(year)
        if sector_id:
            where.append("a.sector_id = %s")
            params.append(sector_id)
        if supervisor:
            where.append("col.supervisor = %s")
            params.append(supervisor)

        sql = f"""
            SELECT
                a.operator_name,
                COALESCE(col.matricula, '') AS matricula,
                COALESCE(col.supervisor, 'N/A') AS supervisor,
                COALESCE(col.setor, a.sector_id) AS setor,
                COALESCE(col.escala, '') AS escala,
                COUNT(*) AS total_ligacoes,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE 0 END)::NUMERIC, 1) AS media_percentual,
                ROUND(AVG(a.score)::NUMERIC, 2) AS media_nota,
                ROUND(AVG(a.max_score)::NUMERIC, 2) AS media_max,
                MIN(CASE WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::NUMERIC, 1) ELSE 0 END) AS menor_nota,
                MAX(CASE WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::NUMERIC, 1) ELSE 0 END) AS maior_nota
            FROM audits a
            LEFT JOIN colaboradores col ON col.nome = a.operator_name
            WHERE {' AND '.join(where)}
            GROUP BY a.operator_name, col.matricula, col.supervisor, col.setor, col.escala
            ORDER BY media_percentual DESC
        """
        c.execute(sql, params)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def get_monthly_trend(
    get_connection,
    months: int = 6,
) -> list[dict]:
    """Média mensal geral (últimos N meses)."""
    conn = get_connection()
    try:
        
        c = conn.cursor()

        sql = f"""
            SELECT
                to_char(COALESCE(a.audit_date, a.timestamp)::TIMESTAMP, 'YYYY-MM') AS mes,
                COUNT(*) AS total_auditorias,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE 0 END)::NUMERIC, 1) AS media_percentual
            FROM audits a
            WHERE a.status = %s
            GROUP BY mes
            ORDER BY mes DESC
            LIMIT %s
        """
        c.execute(sql, [AUDIT_STATUS_APPROVED, months])
        rows = [dict(row) for row in c.fetchall()]
        rows.reverse()  # cronológico
        return rows
    finally:
        conn.close()


def get_top_failures(
    get_connection,
    month: Optional[int] = None,
    year: Optional[int] = None,
    sector_id: Optional[str] = None,
    limit: int = 15,
) -> list[dict]:
    """Critérios com maior taxa de falha no período.

    Extrai dos details_json armazenados nas auditorias.
    """
    conn = get_connection()
    try:
        
        c = conn.cursor()

        where = ["a.status = %s", "a.details_json IS NOT NULL"]
        params: list = [AUDIT_STATUS_APPROVED]

        if month:
            where.append("EXTRACT(MONTH FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(month)
        if year:
            where.append("EXTRACT(YEAR FROM COALESCE(a.audit_date, a.timestamp)::TIMESTAMP)::INTEGER = %s")
            params.append(year)
        if sector_id:
            where.append("a.sector_id = %s")
            params.append(sector_id)

        sql = f"""
            SELECT a.details_json, a.sector_id
            FROM audits a
            WHERE {' AND '.join(where)}
        """
        c.execute(sql, params)
        rows = c.fetchall()

        import json
        failure_counts: dict[str, dict] = {}

        for row in rows:
            try:
                details = json.loads(row["details_json"])
            except (json.JSONDecodeError, TypeError):
                continue

            for detail in details:
                label = detail.get("label", "?")
                status = detail.get("status", "")

                if label not in failure_counts:
                    failure_counts[label] = {"total": 0, "fail": 0}

                failure_counts[label]["total"] += 1
                normalized_status = str(status or "").strip().lower()
                if normalized_status in {"fail", "partial"}:
                    failure_counts[label]["fail"] += 1

        results = []
        for label, data in failure_counts.items():
            if data["total"] == 0:
                continue
            fail_rate = round((data["fail"] / data["total"]) * 100, 1)
            results.append({
                "criterio": label,
                "total_avaliacoes": data["total"],
                "falhas": data["fail"],
                "taxa_falha_percent": fail_rate,
            })

        results.sort(key=lambda x: x["taxa_falha_percent"], reverse=True)
        return results[:limit]
    finally:
        conn.close()
