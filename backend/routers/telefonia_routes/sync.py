"""Endpoints de controle do sync manual e de operação do módulo Telefonia.

Movidos de routers/telefonia.py sem mudança de comportamento: helpers,
constantes e estado compartilhado continuam no orquestrador e são acessados
em runtime via `tf.<nome>` (preserva monkeypatch e estado de módulo).
"""

import asyncio
import logging
import os
import threading
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

import db.database as database
from repositories import configuration, telefonia
from routers import telefonia as tf
from routers.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/manual")
async def sync_manual(
    request: Request,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Dispara sincronizacao manual (botao do painel).

    Body opcional:
      - {"begin_at": "ISO datetime", "end_at": "ISO datetime"} -> janela explicita.
      - {"horas_retroativas": 0.5..720} -> override do default da configuracao.
      - {} -> usa horas_retroativas da configuracao (modo "ultima sincronizacao").
    """
    cred = tf._credentials_status()
    if not cred["configured"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Credenciais Huawei ausentes: "
                + ", ".join(cred["missing"])
                + ". Preencha em Telefonia > Configuracoes."
            ),
        )

    if tf._is_sync_running():
        raise HTTPException(
            status_code=409,
            detail="Já existe uma coleta em andamento (iniciada por outro usuário ou agendamento). Aguarde a conclusão antes de solicitar um novo intervalo."
        )

    begin_ms: Optional[int] = None
    end_ms: Optional[int] = None
    horas_override: Optional[float] = None
    try:
        body = await request.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        begin_ms = tf._parse_iso_to_ms(body.get("begin_at"))
        end_ms = tf._parse_iso_to_ms(body.get("end_at"))
        if (begin_ms is None) ^ (end_ms is None):
            raise HTTPException(
                status_code=400,
                detail="Para usar janela manual, envie begin_at e end_at juntos.",
            )
        if begin_ms is not None and end_ms is not None and begin_ms >= end_ms:
            raise HTTPException(
                status_code=400,
                detail="Data inicial deve ser anterior a data final.",
            )
        raw_horas = body.get("horas_retroativas")
        if raw_horas is not None:
            try:
                horas_override = float(raw_horas)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="horas_retroativas deve ser numerico (ex.: 24, 0.5).",
                )
            if not (0 < horas_override <= 720):
                raise HTTPException(
                    status_code=400,
                    detail="horas_retroativas fora do intervalo permitido (0 < h <= 720).",
                )
            if begin_ms is not None or end_ms is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Use begin_at/end_at OU horas_retroativas, nao ambos.",
                )

    if horas_override is not None:
        horas = horas_override
    else:
        horas = float(str(configuration.get_config_value(database.get_connection, "huawei_horas_retroativas", "1") or "1"))
    tf._LAST_SYNC["status"] = "running"
    tf._LAST_SYNC["started_at"] = tf._utc_now_iso()
    tf._LAST_SYNC["finished_at"] = None
    tf._LAST_SYNC["result"] = None
    tf._LAST_SYNC["cancel_requested"] = False
    tf._LAST_SYNC_CANCEL_EVENT = threading.Event()
    tf._LAST_SYNC_PAUSE_EVENT = threading.Event()
    try:
        tf._LAST_SYNC_RUN_ID = telefonia.start_telefonia_sync_run(
            database.get_connection,
            started_at=tf._LAST_SYNC["started_at"],
            horas_retroativas=horas,
            trigger_type="manual",
        )
    except Exception:
        logger.exception("Falha ao iniciar persistencia do sync; segue com estado em memoria.")
        tf._LAST_SYNC_RUN_ID = None
    if begin_ms is not None and end_ms is not None:
        logger.info("Sync Huawei manual iniciado (janela explicita: %s -> %s)", begin_ms, end_ms)
    else:
        logger.info("Sync Huawei manual iniciado em background (horas_retroativas=%s)", horas)
    tf._LAST_SYNC_TASK = asyncio.create_task(
        tf._run_manual_sync(
            horas,
            tf._LAST_SYNC_CANCEL_EVENT,
            begin_ms,
            end_ms,
            pause_event=tf._LAST_SYNC_PAUSE_EVENT,
        ),
        name="telefonia_sync_manual",
    )

    return {
        "status": "accepted",
        "message": "Sync iniciado em segundo plano. Acompanhe o status nesta tela.",
        "result": {
            "status": "running",
            "horas_retroativas": horas,
            "begin_time_ms": begin_ms,
            "end_time_ms": end_ms,
        },
    }


@router.post("/sync/cancel")
async def cancel_sync(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Solicita cancelamento HARD da coleta manual de ligacoes.

    v1.3.89: alem de setar o evento (soft cancel via checkpoints), aborta a
    asyncio.Task diretamente pra parar requests em andamento. Estado fica
    consistente porque downloads incompletos sao retentados no proximo sync
    (huawei_sync_logs nao marca como sucesso ate o arquivo gravar).
    """
    if not tf._is_sync_running() or tf._LAST_SYNC_CANCEL_EVENT is None:
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": tf._LAST_SYNC.get("result"),
        }

    tf._LAST_SYNC_CANCEL_EVENT.set()
    # Limpar pause se existir — cancelar tem prioridade sobre pausar.
    if tf._LAST_SYNC_PAUSE_EVENT is not None:
        tf._LAST_SYNC_PAUSE_EVENT.clear()

    tf._LAST_SYNC["status"] = "cancelling"
    tf._LAST_SYNC["cancel_requested"] = True

    # Persiste o pedido de cancel para sobreviver restart do pod (v1.3.95).
    if tf._LAST_SYNC_RUN_ID is not None and tf._LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_cancel(database.get_connection, tf._LAST_SYNC_RUN_ID, True)
            telefonia.set_telefonia_sync_pause(database.get_connection, tf._LAST_SYNC_RUN_ID, False)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, tf._LAST_SYNC_RUN_ID, status="cancelling")
        except Exception:
            logger.exception("Falha ao persistir cancel_requested (run_id=%s).", tf._LAST_SYNC_RUN_ID)

    # Hard cancel: aborta a task asyncio. CancelledError sera tratado em
    # _run_manual_sync e gravara status='cancelled' no history.
    if tf._LAST_SYNC_TASK is not None and not tf._LAST_SYNC_TASK.done():
        tf._LAST_SYNC_TASK.cancel()

    logger.info("Cancelamento HARD da coleta Huawei solicitado pelo usuario.")
    return {
        "status": "cancelling",
        "message": "Cancelamento imediato solicitado.",
        "result": tf._LAST_SYNC.get("result"),
    }


@router.post("/sync/pause")
async def pause_sync(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Pausa a coleta manual em andamento. Diferente do cancelar, pode retomar.

    v1.3.89: estado em memoria. Se o pod reiniciar (Cloud Run), a pausa eh
    perdida e a coleta nao retoma sozinha — auditor precisaria disparar novo
    sync manual."""
    if not tf._is_sync_running():
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": tf._LAST_SYNC.get("result"),
        }
    if tf._LAST_SYNC.get("status") == "cancelling":
        return {
            "status": "cancelling",
            "message": "Coleta esta sendo cancelada; pausar nao aplica.",
            "result": tf._LAST_SYNC.get("result"),
        }
    if tf._LAST_SYNC_PAUSE_EVENT is None:
        tf._LAST_SYNC_PAUSE_EVENT = threading.Event()
    tf._LAST_SYNC_PAUSE_EVENT.set()
    tf._LAST_SYNC["status"] = "paused"
    # Persiste para a UI mostrar 'paused' apos restart e para o resume vir do DB.
    if tf._LAST_SYNC_RUN_ID is not None and tf._LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_pause(database.get_connection, tf._LAST_SYNC_RUN_ID, True)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, tf._LAST_SYNC_RUN_ID, status="paused")
        except Exception:
            logger.exception("Falha ao persistir pause_requested (run_id=%s).", tf._LAST_SYNC_RUN_ID)
    logger.info("Pausa da coleta Huawei solicitada pelo usuario.")
    return {
        "status": "paused",
        "message": "Coleta pausada. Use Retomar para continuar.",
        "result": tf._LAST_SYNC.get("result"),
    }


@router.post("/sync/resume")
async def resume_sync(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Retoma a coleta pausada (mesma execucao de onde parou)."""
    if not tf._is_sync_running():
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": tf._LAST_SYNC.get("result"),
        }
    if tf._LAST_SYNC_PAUSE_EVENT is not None:
        tf._LAST_SYNC_PAUSE_EVENT.clear()
    tf._LAST_SYNC["status"] = "running"
    if tf._LAST_SYNC_RUN_ID is not None and tf._LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_pause(database.get_connection, tf._LAST_SYNC_RUN_ID, False)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, tf._LAST_SYNC_RUN_ID, status="running")
        except Exception:
            logger.exception("Falha ao persistir resume (run_id=%s).", tf._LAST_SYNC_RUN_ID)
    logger.info("Retomada da coleta Huawei solicitada pelo usuario.")
    return {
        "status": "running",
        "message": "Coleta retomada.",
        "result": tf._LAST_SYNC.get("result"),
    }


@router.post("/sync/clear")
async def clear_sync_report(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Limpa o resultado do ultimo sync manual da memoria (para ocultar o relatorio na UI)."""
    if tf._is_sync_running():
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel limpar o relatorio enquanto um sync esta em andamento."
        )
    tf._LAST_SYNC["result"] = None
    tf._LAST_SYNC["started_at"] = None
    tf._LAST_SYNC["finished_at"] = None
    tf._LAST_SYNC["status"] = "idle"
    return {"status": "ok", "message": "Relatorio de execucao limpo com sucesso."}


@router.get("/sync/status")
async def sync_status(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Status consolidado do sync para a UI: última run, progresso e credenciais."""
    engine_enabled = (os.getenv("ENABLE_HUAWEI_SYNC", "false") or "").strip().lower() == "true"
    cron_token_configured = bool((os.getenv("CRON_SECRET_TOKEN", "") or "").strip())

    status_dict = dict(tf._LAST_SYNC)
    if tf._is_sync_running() and status_dict.get("status") not in ("running", "cancelling"):
        status_dict["status"] = "running"
        status_dict["message"] = "Coleta em andamento (background/outro worker)."

    return {
        **status_dict,
        "credentials": tf._credentials_status(),
        "engine_enabled": engine_enabled,
        "cron_token_configured": cron_token_configured,
    }


@router.get("/sync/history")
async def sync_history(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Retorna historico de execucoes."""
    try:
        items = telefonia.list_telefonia_sync_history(database.get_connection, limit=50)
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"Erro ao listar historico: {e}")
        return {"items": [tf._LAST_SYNC] if tf._LAST_SYNC.get("started_at") else [], "total": 0}


@router.get("/sync/diagnostics")
async def sync_diagnostics(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Devolve uma visao operacional rapida para diagnosticar 'parou de baixar'.

    Inclui:
      - se o sync esta travado em memoria
      - estado atual do sync_lock no banco (e quem o segura)
      - presenca do CRON_SECRET_TOKEN
      - flag ENABLE_HUAWEI_SYNC (gate do executar_sync_huawei)
    """
    info: Dict[str, Any] = {
        "in_memory_sync_running": tf._is_sync_running(),
        "last_sync_status": tf._LAST_SYNC.get("status"),
        "last_sync_started_at": tf._LAST_SYNC.get("started_at"),
        "last_sync_finished_at": tf._LAST_SYNC.get("finished_at"),
        "cron_secret_token_set": bool((os.getenv("CRON_SECRET_TOKEN") or "").strip()),
        "enable_huawei_sync_env": (os.getenv("ENABLE_HUAWEI_SYNC", "") or "").strip().lower() == "true",
    }
    try:
        info["automacao_hibrida_ativa"] = str(
            configuration.get_config_value(database.get_connection, "automacao_hibrida_ativa", "false") or ""
        ).strip().lower() == "true"
    except Exception:  # noqa: BLE001
        info["automacao_hibrida_ativa"] = None
    try:
        info["sync_lock_db_value"] = str(
            configuration.get_config_value(database.get_connection, "sync_lock", "false") or ""
        ).strip().lower()
    except Exception:  # noqa: BLE001
        info["sync_lock_db_value"] = None
    # Guardrail de orcamento: consumo pago do dia, tetos e kill-switch —
    # visibilidade de "quanto do orcamento de hoje ja foi usado".
    try:
        from core import cost_guard
        info["custo_diario"] = cost_guard.get_today_usage()
    except Exception:  # noqa: BLE001
        info["custo_diario"] = None
    return info


@router.post("/sync/reset-lock")
async def sync_reset_lock(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Forca a liberacao do sync_lock no banco quando ele ficou travado por
    deploy/crash no meio de uma sincronizacao. Existe a expiracao automatica
    de 30 min mas em emergencia o admin pode destravar manualmente."""
    if tf._is_sync_running():
        raise HTTPException(
            status_code=409,
            detail=(
                "Existe um sync em andamento neste processo. Cancele via /sync/cancel "
                "antes de destravar o lock do banco."
            ),
        )
    try:
        configuration.update_config(
            database.get_connection,
            "sync_lock",
            "false",
            alterado_por=_user.get("username", "admin"),
            motivo="destravar sync_lock via endpoint admin",
            origem="ui",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao destravar sync_lock: {exc}")
    logger.warning("sync_lock no banco foi forcado para 'false' por solicitacao admin.")
    return {"status": "ok", "message": "sync_lock destravado. Pode disparar uma nova coleta."}


# Os endpoints POST /automacao/toggle e POST /sync/cron-toggle foram removidos
# em 2026-06-12 (revisao item 4) junto com a config `telefonia_cron_sync_ativa`:
# ligar/desligar a automacao agora e SO pelo toggle atomico
# POST /api/automation/engine/toggle (gates automacao_hibrida_ativa +
# huawei_d1_enabled). O coletor D-1 respeita huawei_d1_enabled por conta propria.
