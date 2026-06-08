"""Router de operadores — APIs de consulta por operador com KPIs.

Endpoints para consultar operadores, suas auditorias individuais e performance.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from routers.auth import require_authenticated_user
import db.database as database
from db.domain_constants import AUDIT_STATUS_APPROVED

router = APIRouter(prefix="/api/operadores", tags=["operadores"])


@router.get("/")
def list_operadores(
    supervisor: Optional[str] = None,
    setor: Optional[str] = None,
    escala: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    """Lista operadores com KPIs de auditoria (score médio, total de ligações)."""
    conn = database.get_connection()
    try:
        
        c = conn.cursor()

        where_colab = ["c.nome IS NOT NULL", "c.nome != ''"]
        params: list = []

        if supervisor:
            where_colab.append("c.supervisor = %s")
            params.append(supervisor)
        if setor:
            where_colab.append("c.setor = %s")
            params.append(setor)
        if escala:
            where_colab.append("c.escala = %s")
            params.append(escala)
        if status:
            where_colab.append("c.status = %s")
            params.append(status.upper())
        else:
            where_colab.append("c.status = 'ATIVO'")

        # Build date filter for audit KPIs
        audit_date_filter = ""
        audit_params: list = []
        if month:
            audit_date_filter += " AND EXTRACT(MONTH FROM a.timestamp)::INTEGER = %s"
            audit_params.append(month)
        if year:
            audit_date_filter += " AND EXTRACT(YEAR FROM a.timestamp)::INTEGER = %s"
            audit_params.append(year)

        sql = f"""
            SELECT
                c.id,
                c.nome,
                c.supervisor,
                c.setor,
                c.escala,
                c.status,
                c.matricula,
                c.id_huawei,
                c.auditavel,
                COUNT(a.id) AS total_auditorias,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE NULL END)::numeric, 1) AS media_percentual,
                ROUND(AVG(a.score)::numeric, 2) AS media_nota,
                MIN(CASE WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::numeric, 1) ELSE NULL END) AS menor_nota,
                MAX(CASE WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::numeric, 1) ELSE NULL END) AS maior_nota
            FROM colaboradores c
            LEFT JOIN audits a ON (
                a.colaborador_id = c.id
                AND a.status = %s
                {audit_date_filter}
            )
            WHERE {' AND '.join(where_colab)}
            GROUP BY c.id
            ORDER BY c.nome
        """
        all_params = [AUDIT_STATUS_APPROVED] + audit_params + params
        c.execute(sql, all_params)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


@router.get("/{operador_id}/auditorias")
def get_auditorias_operador(
    operador_id: int,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_authenticated_user),
):
    """Retorna as auditorias de um operador específico."""
    conn = database.get_connection()
    try:
        
        c = conn.cursor()

        # Verify operador exists
        c.execute("SELECT id, nome FROM colaboradores WHERE id = %s", (operador_id,))
        colab = c.fetchone()
        if not colab:
            raise HTTPException(status_code=404, detail="Operador não encontrado")

        # Fetch audits linked by FK or by name
        c.execute(
            """
            SELECT
                a.id, a.timestamp, a.score, a.max_score, a.summary,
                a.alert_id, a.alert_label, a.sector_id, a.status,
                a.source_type, a.ai_feedback,
                CASE WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::numeric, 1) ELSE 0 END AS percentual
            FROM audits a
            WHERE (a.colaborador_id = %s OR LOWER(TRIM(a.operator_name)) = LOWER(TRIM(%s)))
              AND a.status = %s
            ORDER BY a.timestamp DESC
            LIMIT %s
            """,
            (operador_id, colab["nome"], AUDIT_STATUS_APPROVED, limit),
        )
        auditorias = [dict(row) for row in c.fetchall()]

        return {
            "operador": {
                "id": colab["id"],
                "nome": colab["nome"],
            },
            "total": len(auditorias),
            "auditorias": auditorias,
        }
    finally:
        conn.close()


@router.get("/{operador_id}/performance")
def get_performance_operador(
    operador_id: int,
    months: int = Query(6, ge=1, le=24),
    user: dict = Depends(require_authenticated_user),
):
    """Resumo de performance individual: tendência mensal."""
    conn = database.get_connection()
    try:
        
        c = conn.cursor()

        c.execute("SELECT id, nome, supervisor, setor FROM colaboradores WHERE id = %s", (operador_id,))
        colab = c.fetchone()
        if not colab:
            raise HTTPException(status_code=404, detail="Operador não encontrado")

        c.execute(
            """
            SELECT
                to_char(a.timestamp, 'YYYY-MM') AS mes,
                COUNT(*) AS total_auditorias,
                ROUND(AVG(CASE WHEN a.max_score > 0 THEN (a.score * 1.0 / a.max_score) * 100 ELSE 0 END)::numeric, 1) AS media_percentual
            FROM audits a
            WHERE (a.colaborador_id = %s OR LOWER(TRIM(a.operator_name)) = LOWER(TRIM(%s)))
              AND a.status = %s
            GROUP BY mes
            ORDER BY mes DESC
            LIMIT %s
            """,
            (operador_id, colab["nome"], AUDIT_STATUS_APPROVED, months),
        )
        trend = [dict(row) for row in c.fetchall()]
        trend.reverse()

        return {
            "operador": dict(colab),
            "tendencia_mensal": trend,
        }
    finally:
        conn.close()


@router.get("/whitelist/health")
def whitelist_health(_user: dict = Depends(require_authenticated_user)):
    """Healthcheck da whitelist de operadores elegiveis para auditoria.

    Whitelist = colaboradores que passam nas 3 regras simultaneas:
      - status = 'ATIVO'
      - auditavel = true (default 1)
      - id_huawei nao vazio

    Retorna contagens e flags de alerta para detectar config errada
    (ex: whitelist vazia, queda brusca em relacao ao snapshot do dia anterior).
    """
    conn = database.get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT
                COUNT(*) AS total_colaboradores,
                COUNT(*) FILTER (WHERE status = 'ATIVO') AS ativos,
                COUNT(*) FILTER (WHERE COALESCE(auditavel, 1) = 1) AS auditaveis,
                COUNT(*) FILTER (
                    WHERE COALESCE(NULLIF(TRIM(id_huawei), ''), '') <> ''
                ) AS com_id_huawei,
                COUNT(*) FILTER (
                    WHERE status = 'ATIVO'
                      AND COALESCE(auditavel, 1) = 1
                      AND COALESCE(NULLIF(TRIM(id_huawei), ''), '') <> ''
                ) AS elegiveis_whitelist
            FROM colaboradores
            """
        )
        row = c.fetchone()
        stats = dict(row) if row else {}

        # Snapshot do dia anterior (via colaboradores_audit_log)
        c.execute(
            """
            SELECT COUNT(*) AS desativacoes_24h
            FROM colaboradores_audit_log
            WHERE alterado_em >= NOW() - INTERVAL '24 hours'
              AND (
                  payload_depois ->> 'auditavel' = 'False'
                  OR payload_depois ->> 'status' <> 'ATIVO'
              )
              AND (
                  payload_antes ->> 'auditavel' = 'True'
                  OR payload_antes ->> 'status' = 'ATIVO'
              )
            """
        )
        churn_row = c.fetchone()
        desativacoes_24h = (
            churn_row["desativacoes_24h"]
            if churn_row and "desativacoes_24h" in (churn_row.keys() if hasattr(churn_row, 'keys') else {})
            else (churn_row[0] if churn_row else 0)
        )

        # Alertas heuristicos
        alertas: list[str] = []
        elegiveis = int(stats.get("elegiveis_whitelist") or 0)
        ativos = int(stats.get("ativos") or 0)
        if elegiveis == 0:
            alertas.append("critical:whitelist_vazia")
        elif elegiveis < 50:
            alertas.append(f"warning:whitelist_pequena ({elegiveis} elegiveis)")
        if ativos and elegiveis / ativos < 0.7:
            alertas.append(
                f"warning:cobertura_baixa ({elegiveis}/{ativos} = "
                f"{round(100*elegiveis/ativos, 1)}% dos ativos sao elegiveis)"
            )
        if desativacoes_24h > 10:
            alertas.append(f"warning:churn_alto ({desativacoes_24h} desativacoes nas ultimas 24h)")

        return {
            "stats": {
                "total_colaboradores": int(stats.get("total_colaboradores") or 0),
                "ativos": ativos,
                "auditaveis": int(stats.get("auditaveis") or 0),
                "com_id_huawei": int(stats.get("com_id_huawei") or 0),
                "elegiveis_whitelist": elegiveis,
                "desativacoes_24h": int(desativacoes_24h or 0),
            },
            "alertas": alertas,
            "healthy": len([a for a in alertas if a.startswith("critical:")]) == 0,
        }
    finally:
        conn.close()
