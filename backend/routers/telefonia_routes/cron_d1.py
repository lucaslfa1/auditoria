"""Endpoints do gatilho cron e do pipeline D-1 (lote diário do OBS) da Telefonia.

Movidos de routers/telefonia.py sem mudança de comportamento: helpers e
constantes do módulo continuam no orquestrador e são acessados em runtime
via `tf.<nome>` (preserva monkeypatch e estado compartilhado).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

import db.database as database
from repositories import configuration
from routers import telefonia as tf
from routers.auth import require_admin

router = APIRouter()


@router.post("/sync/d-minus-1")
async def sync_d_minus_1(
    request: Request,
    body: Optional[dict] = Body(default=None),
):
    """Dispara o pipeline D-1 (lote diario do OBS) via scheduler externo.

    - Sem `date` no body: roda o pipeline orquestrado (respeita horário,
      lookback e retry configurados no banco).
    - Com `date`: força execução direta de uma data específica (uso legado).

    GCP atual: Cloud Scheduler. Azure equivalente: Container Apps Job agendado
    ou Logic App chamando este endpoint com `Authorization: Bearer <token>`.
    """
    from routers.automation import _require_cron_token
    _require_cron_token(request)

    date_str = None
    if not isinstance(body, dict):
        body = None

    if body and body.get("date"):
        date_str = str(body["date"]).replace("-", "")[:8]

    if date_str:
        from core.huawei_d_minus_1 import executar_d_minus_1
        return await executar_d_minus_1(date_str)

    from core.huawei_d_minus_1 import executar_d_minus_1_pipeline
    return await executar_d_minus_1_pipeline()


@router.post("/cron/sync")
async def cron_sync_d_minus_1(
    request: Request,
    body: Optional[dict] = Body(default=None),
):
    """Gatilho dedicado do scheduler externo para o Coletor D-1/OBS.

    Agendado 1x/dia. Não há gate próprio aqui (a config
    `telefonia_cron_sync_ativa` foi removida em 2026-06-12): o pipeline
    `executar_d_minus_1_pipeline` já se auto-governa — respeita
    `huawei_d1_enabled` (desligado pelo toggle da automação), o horário
    configurado e a tabela de runs por dia (um lote por data; disparos extras
    no mesmo dia não reexecutam lote completo). O kill-switch e o teto diário
    do cost_guard continuam valendo nas fases pagas.
    """
    from routers.automation import _require_cron_token

    _require_cron_token(request)
    if not isinstance(body, dict):
        body = None
    return await sync_d_minus_1(request, body)


@router.post("/sync/d-minus-1/manual")
async def sync_d_minus_1_manual(
    body: Optional[dict] = Body(default=None),
    _user: dict = Depends(require_admin),
):
    """Reprocessa o lote diário de uma data específica a partir da UI.

    Body opcional:
      - {"date": "YYYY-MM-DD" | "YYYYMMDD"} -> data alvo (default: ontem)
      - {"time": "HH:MM"} -> horário de início opcional (default: meia-noite)
      - {"force": true} -> força reprocessamento mesmo se já marcado como completed
    """
    date_str: Optional[str] = None
    begin_time_str: Optional[str] = None
    force = False
    if isinstance(body, dict):
        raw_date = body.get("date")
        if raw_date:
            date_str = str(raw_date).replace("-", "")[:8]
            if not (len(date_str) == 8 and date_str.isdigit()):
                raise HTTPException(
                    status_code=400,
                    detail="Data invalida. Use YYYY-MM-DD ou YYYYMMDD.",
                )
        begin_time_str = body.get("time")
        force = bool(body.get("force", False))

    from core.huawei_d_minus_1 import executar_d_minus_1
    return await executar_d_minus_1(date_str, force=force, begin_time_str=begin_time_str)


@router.get("/sync/d-minus-1/status")
async def get_sync_d_minus_1_status(_user: dict = Depends(require_admin)):
    """Retorna o histórico recente das execuções do lote diário."""
    from db.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM huawei_d_minus_1_runs
                ORDER BY date_str DESC LIMIT 14
                """
            )
            rows = cur.fetchall()
            colnames = [desc[0] for desc in cur.description]
            return [dict(zip(colnames, row)) for row in rows]


@router.get("/sync/d-minus-1/summary")
async def get_sync_d_minus_1_summary(_user: dict = Depends(require_admin)):
    """Resumo único do pipeline D-1 para o painel de Automações.

    Retorna configs ativas, última execução conhecida, próxima execução
    estimada e estado agregado.
    """
    from core.huawei_d_minus_1 import (
        get_pipeline_config,
        PIPELINE_CONFIG_DEFAULTS,
        SP_TZ,
    )

    cfg = get_pipeline_config()

    # Última execução: pega o run mais recente por last_attempt_at
    from db.database import get_connection
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT date_str, status, attempts, last_attempt_at, completed_at,
                       downloaded_count, skipped_quota_count, last_error
                FROM huawei_d_minus_1_runs
                ORDER BY last_attempt_at DESC NULLS LAST
                LIMIT 1
                """
            )
            row = cur.fetchone()
            ultima_execucao = None
            last_attempt_sp = None
            if row:
                colnames = [desc[0] for desc in cur.description]
                ultima_execucao = dict(zip(colnames, row))
                last_attempt_raw = ultima_execucao.get("last_attempt_at")
                if isinstance(last_attempt_raw, datetime):
                    if last_attempt_raw.tzinfo is None:
                        last_attempt_raw = last_attempt_raw.replace(tzinfo=timezone.utc)
                    last_attempt_sp = last_attempt_raw.astimezone(SP_TZ)
                if ultima_execucao.get("last_attempt_at"):
                    ultima_execucao["last_attempt_at"] = (
                        ultima_execucao["last_attempt_at"].isoformat()
                        if hasattr(ultima_execucao["last_attempt_at"], "isoformat")
                        else str(ultima_execucao["last_attempt_at"])
                    )
                if ultima_execucao.get("completed_at"):
                    ultima_execucao["completed_at"] = (
                        ultima_execucao["completed_at"].isoformat()
                        if hasattr(ultima_execucao["completed_at"], "isoformat")
                        else str(ultima_execucao["completed_at"])
                    )

    # Próxima execução estimada: hoje no horário programado, ou amanhã.
    now_sp = datetime.now(SP_TZ)
    horario_raw = cfg.get("huawei_d1_horario_execucao", "06:00")
    proxima = tf._calcular_proxima_execucao_d1_sp(
        now_sp=now_sp,
        horario_raw=horario_raw,
        enabled=cfg["huawei_d1_enabled"].lower() == "true",
        ultima_execucao=ultima_execucao,
        last_attempt_sp=last_attempt_sp,
        max_retries=max(1, tf._safe_int(cfg["huawei_d1_max_retries"], int(PIPELINE_CONFIG_DEFAULTS["huawei_d1_max_retries"]))),
        retry_intervalo_minutos=max(1, tf._safe_int(cfg["huawei_d1_retry_intervalo_minutos"], 60)),
    )
    proxima_iso = proxima.isoformat() if proxima else None

    try:
        audit_target_cfg = configuration.get_config_values(
            database.get_connection,
            ("automacao_audit_target_count", "automacao_audit_batch_size"),
            {"automacao_audit_target_count": "", "automacao_audit_batch_size": "10"},
        )
        raw_audit_target = audit_target_cfg.get("automacao_audit_target_count") or ""
        if raw_audit_target in (None, ""):
            raw_audit_target = audit_target_cfg.get("automacao_audit_batch_size") or "10"
        limite_auditorias = max(1, tf._safe_int(raw_audit_target, 10))
    except Exception:
        limite_auditorias = 10
    # downloads = meta de auditorias (1:1). huawei_d1_limite_ligacoes foi descontinuado.
    limite_ligacoes = max(1, limite_auditorias)

    return {
        "config": {
            "enabled": cfg["huawei_d1_enabled"].lower() == "true",
            "horario_execucao": cfg["huawei_d1_horario_execucao"],
            "max_retries": max(1, tf._safe_int(cfg["huawei_d1_max_retries"], int(PIPELINE_CONFIG_DEFAULTS["huawei_d1_max_retries"]))),
            "retry_intervalo_minutos": max(1, tf._safe_int(cfg["huawei_d1_retry_intervalo_minutos"], 60)),
            "lookback_dias": max(1, tf._safe_int(cfg["huawei_d1_lookback_dias"], 1)),
            "cota_max_por_operador_mes": max(1, tf._safe_int(cfg["huawei_cota_max_por_operador_mes"], 2)),
            "limite_ligacoes": limite_ligacoes,
            "limite_auditorias": limite_auditorias,
        },
        "config_defaults": PIPELINE_CONFIG_DEFAULTS,
        "now_sp": now_sp.isoformat(),
        "proxima_execucao_sp": proxima_iso,
        "ultima_execucao": ultima_execucao,
    }
