"""
Automation Router — Endpoints para automação de auditoria em lote.
"""

import asyncio
import logging

import os

from fastapi import APIRouter, Depends, HTTPException, Request

import db.database as database
from core.automation import audit_all_pending, cancel_automation, get_automation_status
from db.domain_constants import AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_PENDING_APPROVAL
from routers.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])

_manual_cycle_task: asyncio.Task | None = None


def _clear_manual_cycle_task(task: asyncio.Task) -> None:
    global _manual_cycle_task

    if _manual_cycle_task is task:
        _manual_cycle_task = None

    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("Ciclo manual de automacao cancelado antes de concluir.")
    except RuntimeError as exc:
        if "Automacao ja esta em andamento" in str(exc):
            logger.info("Ciclo manual ignorado: %s", exc)
            return
        logger.exception("Ciclo manual de automacao falhou.")
    except Exception:
        logger.exception("Ciclo manual de automacao falhou.")


def _require_cron_token(request: Request) -> None:
    expected_token = (os.getenv("CRON_SECRET_TOKEN") or "").strip()
    auth_header = (request.headers.get("Authorization") or "").strip()
    if not expected_token or auth_header != f"Bearer {expected_token}":
        raise HTTPException(status_code=403, detail="Acesso nao autorizado ao Cron.")


from pydantic import BaseModel

class ToggleEngineRequest(BaseModel):
    enabled: bool

@router.post("/engine/toggle")
def toggle_automation_engine(
    req: ToggleEngineRequest,
    _user: dict = Depends(require_admin),
):
    """Liga ou desliga o motor de automação híbrida.

    Atualiza atomicamente `automacao_hibrida_ativa`, `huawei_d1_enabled` e
    `telefonia_cron_sync_ativa` na mesma transação. O frontend não precisa
    emitir chamadas separadas para sincronizar os gates do ciclo automático.
    """
    from core.automation_engine import set_automation_enabled_atomic
    try:
        set_automation_enabled_atomic(req.enabled)
    except Exception:
        logger.exception("Falha ao alternar automacao (atomic toggle).")
        raise HTTPException(status_code=500, detail="Falha ao alternar automacao.")
    return {"status": "ok", "enabled": req.enabled}

@router.get("/engine/status")
def get_automation_engine_status(
    _user: dict = Depends(require_admin),
):
    """Retorna o status do motor de automação."""
    from core.automation_engine import get_engine_status
    return get_engine_status()


@router.post("/run-now")
async def run_automation_cycle_now(
    _user: dict = Depends(require_admin),
):
    """Disparo manual de um ciclo completo da Automacao.

    Usa o mesmo lock do cron para impedir duas execucoes simultaneas. Aguarda a 
    conclusão do ciclo no mesmo request para evitar congelamento de CPU em 
    ambientes serverless como o Cloud Run.
    """
    from core.automation_engine import get_engine_status, is_automation_enabled, run_automation_cycle

    current_status = get_engine_status()
    if current_status.get("is_running"):
        return {
            "status": "skipped",
            "message": "Automacao ja esta em andamento.",
        }

    try:
        result = await run_automation_cycle(source="manual_ui")
        return {
            "status": result.get("status", "ok"),
            "message": "Ciclo manual finalizado.",
            "result": result,
        }
    except asyncio.CancelledError:
        logger.warning("Request manual cancelado; propagando cancelamento para finalizar o ciclo com limpeza.")
        raise


@router.post("/cron/run")
async def cron_run_automation_cycle(request: Request):
    """Gatilho do Cloud Scheduler para um ciclo completo de automacao."""
    _require_cron_token(request)

    from core.automation_engine import is_automation_enabled, run_automation_cycle

    if not is_automation_enabled():
        return {
            "status": "disabled",
            "message": "Automacao hibrida desligada.",
        }

    try:
        result = await run_automation_cycle(source="cloud_scheduler")
        return {"status": result.get("status", "ok"), "result": result}
    except RuntimeError as exc:
        if "Automacao ja esta em andamento" in str(exc):
            return {"status": "skipped", "message": str(exc)}
        raise
@router.post("/audit-all")
async def start_audit_all(
    _user: dict = Depends(require_admin),
):
    """Inicia auditoria de todos os itens classificados pendentes.

    Processa 1 por vez em sequência com progresso rastreável.
    """
    try:
        result = await audit_all_pending()
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Erro na automação: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno na automação.")


@router.get("/status")
async def automation_status(
    _user: dict = Depends(require_admin),
):
    """Retorna o progresso atual da automação."""
    return get_automation_status()


@router.post("/cancel")
async def cancel_running_automation(
    _user: dict = Depends(require_admin),
):
    """Cancela a automação em andamento."""
    from core.automation import cancel_automation
    return cancel_automation()


@router.post("/pause")
async def pause_running_automation(
    _user: dict = Depends(require_admin),
):
    """Pausa a automação em andamento."""
    from core.automation import pause_automation
    return pause_automation()


@router.post("/resume")
async def resume_running_automation(
    _user: dict = Depends(require_admin),
):
    """Retoma a automação pausada."""
    from core.automation import resume_automation
    return resume_automation()


@router.post("/flush-awaiting-pairs")
def flush_awaiting_pairs(_user: dict = Depends(require_admin)) -> dict:
    """Promove auditorias presas em `awaiting_pair` de meses anteriores.

    A regra de pareamento segura a 1ª ligação até uma 2ª chegar. Quando o
    operador comete só um erro no mês, a auditoria fica em limbo. Esta rotina
    libera o resíduo do(s) mês(es) anterior(es) para `pending_approval`.
    """
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE audits
            SET status = %s
            WHERE status = %s
              AND COALESCE(audit_date, timestamp) < date_trunc('month', CURRENT_DATE)
            """,
            (AUDIT_STATUS_PENDING_APPROVAL, AUDIT_STATUS_AWAITING_PAIR),
        )
        updated = cursor.rowcount or 0
        conn.commit()
    finally:
        conn.close()

    logger.info("flush-awaiting-pairs: %d auditoria(s) promovida(s).", updated)
    return {"success": True, "updated": updated}


@router.post("/huawei-sync/manual")
async def trigger_huawei_sync_manual(request: Request, _user: dict = Depends(require_admin)):
    """SHIM legado - redireciona para /api/telefonia/sync/manual.

    Mantido por compatibilidade com clientes antigos. Remover apos a migracao
    completa do frontend para o novo modulo Telefonia.
    """
    from routers.telefonia import sync_manual

    logger.info("Shim /api/automation/huawei-sync/manual -> /api/telefonia/sync/manual")
    return await sync_manual(request=request, _user=_user)



