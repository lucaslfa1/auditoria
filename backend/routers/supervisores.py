"""Router de supervisores — APIs de consulta por supervisor com KPIs.

Endpoints para listar supervisores e suas equipes com métricas agregadas.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException

from routers.auth import require_authenticated_user
import db.database as database
from db.domain_constants import AUDIT_STATUS_APPROVED

router = APIRouter(prefix="/api/supervisores", tags=["supervisores"])


@router.get("/")
def list_supervisores(
    setor: Optional[str] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    """Lista supervisores com KPIs agregados da equipe."""
    conn = database.get_connection()
    try:
        
        c = conn.cursor()

        where_colab = [
            "c.supervisor IS NOT NULL",
            "c.supervisor != ''",
            "c.status = 'ATIVO'",
        ]
        params: list = []

        if setor:
            where_colab.append("c.setor = %s")
            params.append(setor)

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
                c.supervisor,
                COUNT(DISTINCT c.id) AS total_operadores,
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
            GROUP BY c.supervisor
            ORDER BY media_percentual DESC
        """
        all_params = [AUDIT_STATUS_APPROVED] + audit_params + params
        c.execute(sql, all_params)
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


@router.get("/{supervisor_name}/equipe")
def get_equipe_supervisor(
    supervisor_name: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    """Retorna todos os operadores de um supervisor com KPIs individuais."""
    conn = database.get_connection()
    try:
        
        c = conn.cursor()

        # Verify supervisor exists
        c.execute(
            "SELECT DISTINCT supervisor FROM colaboradores WHERE LOWER(TRIM(supervisor)) = LOWER(TRIM(%s))",
            (supervisor_name,),
        )
        if not c.fetchone():
            raise HTTPException(status_code=404, detail="Supervisor não encontrado")

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
                c.setor,
                c.escala,
                c.matricula,
                c.status,
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
            WHERE LOWER(TRIM(c.supervisor)) = LOWER(TRIM(%s))
              AND c.status = 'ATIVO'
            GROUP BY c.id
            ORDER BY media_percentual DESC
        """
        all_params = [AUDIT_STATUS_APPROVED] + audit_params + [supervisor_name]
        c.execute(sql, all_params)
        equipe = [dict(row) for row in c.fetchall()]

        # Aggregate KPIs for the supervisor
        total_auditorias = sum(op["total_auditorias"] for op in equipe)
        scores = [op["media_percentual"] for op in equipe if op["media_percentual"] is not None]
        media_geral = round(sum(scores) / len(scores), 1) if scores else None

        return {
            "supervisor": supervisor_name,
            "resumo": {
                "total_operadores": len(equipe),
                "total_auditorias": total_auditorias,
                "media_geral_percentual": media_geral,
            },
            "equipe": equipe,
        }
    finally:
        conn.close()
