"""Router de indicadores de qualidade.

Endpoints puramente extrativos — retornam dados calculados pelo sistema.
Nenhum peso ou regra de negócio inventada.
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional

from routers.auth import require_authenticated_user
import db.database as database
from repositories.analytics_quality import (
    get_indicators_by_sector,
    get_indicators_by_supervisor,
    get_indicators_by_operator,
    get_monthly_trend,
    get_top_failures,
)
from repositories.report_powerbi import (
    get_powerbi_flat_audits,
    get_powerbi_detailed_failures,
)
from repositories.matching_report import get_matching_quality_report

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/indicators")
def indicators_overview(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    """Resumo geral: por setor, tendência mensal, e top falhas."""
    return {
        "by_sector": get_indicators_by_sector(database.get_connection, month, year),
        "trend": get_monthly_trend(database.get_connection),
        "top_failures": get_top_failures(database.get_connection, month, year, limit=10),
    }

# --- PowerBI External Reporting ---

@router.get("/external/powerbi/audits")
def powerbi_audits_report(user: dict = Depends(require_authenticated_user)):
    """Tabela plana de auditorias para PowerBI."""
    return get_powerbi_flat_audits(database.get_connection)

@router.get("/external/powerbi/details")
def powerbi_details_report(user: dict = Depends(require_authenticated_user)):
    """Tabela detalhada de falhas por critério para PowerBI."""
    return get_powerbi_detailed_failures(database.get_connection)


@router.get("/indicators/sectors")
def indicators_by_sector(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    return get_indicators_by_sector(database.get_connection, month, year)


@router.get("/indicators/supervisors")
def indicators_by_supervisor(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    sector_id: Optional[str] = None,
    user: dict = Depends(require_authenticated_user),
):
    return get_indicators_by_supervisor(database.get_connection, month, year, sector_id)


@router.get("/indicators/operators")
def indicators_by_operator(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    sector_id: Optional[str] = None,
    supervisor: Optional[str] = None,
    user: dict = Depends(require_authenticated_user),
):
    return get_indicators_by_operator(database.get_connection, month, year, sector_id, supervisor)


@router.get("/trend")
def monthly_trend(
    months: int = Query(6, ge=1, le=24),
    user: dict = Depends(require_authenticated_user),
):
    return get_monthly_trend(database.get_connection, months)


@router.get("/top-failures")
def top_failures(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    sector_id: Optional[str] = None,
    limit: int = Query(15, ge=1, le=50),
    user: dict = Depends(require_authenticated_user),
):
    return get_top_failures(database.get_connection, month, year, sector_id, limit)


@router.get("/matching-quality")
def matching_quality(
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020),
    user: dict = Depends(require_authenticated_user),
):
    """Relatório de qualidade de correspondência operadores ↔ colaboradores."""
    return get_matching_quality_report(database.get_connection, month, year)
