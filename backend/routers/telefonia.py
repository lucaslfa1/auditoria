from __future__ import annotations
"""Router do modulo Telefonia — sincronizacao com Huawei AICC.

Endpoints expostos:
    POST /api/telefonia/sync/manual      - admin dispara sync manual
    GET  /api/telefonia/sync/status      - status do ultimo sync
    GET  /api/telefonia/sync/history     - historico (placeholder)
    GET  /api/telefonia/recordings       - lista ligacoes baixadas (placeholder)
    POST /api/telefonia/cron/sync        - gatilho do Cloud Scheduler

O router antigo em `routers/automation.py` mantem shims para nao quebrar o
frontend legado ate a migracao completa.
"""


import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import db.database as database
from repositories import classification_review, configuration, telefonia
from repositories import audits
from repositories import operators
from core.automation import (
    _build_alert_from_classification,
    _get_monthly_audit_quota,
    load_classified_audio,
    open_classified_audio_stream,
)
from core.automation_operator import QuotaGatekeeper
from core.audit import process_audit_with_ai
from core.audit_rules import get_sector_prompt_rules
from core.audit_pipeline import (
    AUDIT_ORIGIN_TELEFONIA_MANUAL,
    apply_resolved_operator,
    build_queue_audit_context,
    coerce_pipeline_context,
    is_unknown_value,
    repair_queue_audit_context,
)
from core.classification import get_mime_type
from core.huawei_client import OAUTH_DIRECT_MODES
from core.huawei_direction import (
    NON_TELEFONIA_SECTORS,
    OUTBOUND_ONLY_RISK_SECTORS,
    normalize_huawei_sector,
    resolve_huawei_is_call_in,
)
from core.huawei_sync import executar_sync_huawei
from db.domain_constants import (
    AUDIT_STATUS_AWAITING_PAIR,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_REVIEWED,
    REVIEW_QUEUE_STATUS_DOWNLOADED,
    SOURCE_TYPE_AUDIO,
    SOURCE_TYPE_PDF,
)
from routers.auth import require_admin
from routers.common import _safe_filename
from repositories.common import json_loads

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/telefonia", tags=["telefonia"])
TELEFONIA_CRON_SYNC_CONFIG_KEY = "telefonia_cron_sync_ativa"
TELEFONIA_SYNC_INTERVAL_CONFIG_KEY = "telefonia_sync_intervalo_segundos"
D1_RETRY_PENDING_STATUSES = {
    "empty",
    "error",
    "partial",
    "obs_voice_empty_will_retry",
    "obs_manifest_empty_will_retry",
}
TELEFONIA_TRIAGE_REASON = "enviado_para_triagem_telefonia"


_ACTIVE_AUDIT_TASKS: Dict[str, asyncio.Task] = {}

def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


# Estado em memoria do ultimo sync — substituivel por tabela dedicada no futuro.
_LAST_SYNC: Dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "result": None,
}
_LAST_SYNC_TASK: asyncio.Task | None = None
_LAST_SYNC_CANCEL_EVENT: threading.Event | None = None
# Pause/Resume — em memoria. Pausar nao aborta a task, apenas faz o loop dormir
# entre iteracoes ate o evento ser limpo (resume) ou cancel ser solicitado.
_LAST_SYNC_PAUSE_EVENT: threading.Event | None = None
# id da row em `telefonia_sync_history` representando o run em progresso (v1.3.95).
# Persistir o estado de pause/cancel/heartbeat permite que a UI reconcilie o
# status correto depois de reinicio do pod (que perde os globals acima).
_LAST_SYNC_RUN_ID: int | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_telefonia_cron_sync_enabled() -> bool:
    raw = configuration.get_config_value(database.get_connection, TELEFONIA_CRON_SYNC_CONFIG_KEY, "true")
    return str(raw or "").strip().lower() == "true"


def _get_telefonia_sync_interval_seconds() -> int:
    legacy_default = configuration.get_config_value(database.get_connection, "automacao_intervalo_segundos", "600")
    raw = configuration.get_config_value(database.get_connection, TELEFONIA_SYNC_INTERVAL_CONFIG_KEY, legacy_default or "600")
    try:
        return max(1, int(str(raw or "600")))
    except ValueError:
        return 600


def _calcular_proxima_execucao_d1_sp(
    *,
    now_sp: datetime,
    horario_raw: str,
    enabled: bool,
    ultima_execucao: Optional[dict],
    last_attempt_sp: Optional[datetime],
    max_retries: int,
    retry_intervalo_minutos: int,
) -> Optional[datetime]:
    try:
        hh, mm = horario_raw.split(":")
        proxima = now_sp.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return None

    if proxima <= now_sp:
        proxima = proxima + timedelta(days=1)

    status_atual = str((ultima_execucao or {}).get("status") or "").strip().lower()
    attempts = int((ultima_execucao or {}).get("attempts") or 0)
    retry_min = max(1, retry_intervalo_minutos)
    if (
        enabled
        and status_atual in D1_RETRY_PENDING_STATUSES
        and attempts < max(1, max_retries)
        and last_attempt_sp is not None
    ):
        retry_at = last_attempt_sp + timedelta(minutes=retry_min)
        # Retry ainda no futuro: usa ele. Retry ja vencido: NAO reagenda para
        # "now + 1 min" (isso prendia o aviso "Proxima: em 1 min" na UI, pois o
        # status era recalculado a cada polling) — cai para o proximo horario
        # diario real, que e a proxima execucao garantida.
        return retry_at if retry_at > now_sp else proxima

    return proxima


def _is_sync_running() -> bool:
    if _LAST_SYNC_TASK is not None and not _LAST_SYNC_TASK.done():
        return True
    
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT valor 
            FROM configuracoes 
            WHERE chave = 'sync_lock' 
              AND valor = 'true'
              AND (atualizado_em IS NULL OR atualizado_em::timestamp >= NOW() - INTERVAL '30 minutes')
        """)
        row = cursor.fetchone()
        if row:
            return True
        return False
    except Exception:
        return False
    finally:
        conn.close()


_TRIAGE_STATUS_LABELS = {
    REVIEW_QUEUE_STATUS_DOWNLOADED: "Retida (Aguardando Envio)",
    REVIEW_QUEUE_STATUS_PENDING: "Aguardando classificacao",
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED: "Classificada",
    REVIEW_QUEUE_STATUS_REVIEWED: "Revisada",
    REVIEW_QUEUE_STATUS_AUDITED: "Auditada",
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED: "Cota mensal",
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE: "Triagem manual",
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR: "Operador bloqueado",
}


def _queue_metadata(item: dict) -> dict:
    metadata = (item or {}).get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _resolve_audit_created_by_for_queue_item(item: dict, user: dict) -> str:
    metadata = _queue_metadata(item)
    if metadata.get("is_manual") is False:
        return "automacao"

    user_info = user or {}
    return user_info.get("username") or user_info.get("sub") or "telefonia_manual"


def _is_audit_task_cancel_requested(input_hash: str) -> bool:
    try:
        item = classification_review.obter_fila_revisao_classificacao_por_hash(
            database.get_connection,
            input_hash,
        )
    except Exception:
        logger.warning("Falha ao verificar cancelamento da auditoria %s", input_hash, exc_info=True)
        return False

    metadata = _queue_metadata(item or {})
    return str(metadata.get("audit_task_status") or "").strip().lower() == "canceled"


def _raise_if_audit_task_cancel_requested(input_hash: str) -> None:
    if _is_audit_task_cancel_requested(input_hash):
        raise asyncio.CancelledError(f"Auditoria cancelada para input_hash={input_hash}")


def _cleanup_audit_task(input_hash: str, task: asyncio.Task) -> None:
    if _ACTIVE_AUDIT_TASKS.get(input_hash) is task:
        _ACTIVE_AUDIT_TASKS.pop(input_hash, None)
    if task.cancelled():
        logger.info("Task de auditoria para %s foi cancelada.", input_hash)
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.info("Task de auditoria para %s foi cancelada.", input_hash)
        return
    if exc:
        logger.error(
            "Task de auditoria para %s terminou com erro inesperado.",
            input_hash,
            exc_info=(type(exc), exc, exc.__traceback__),
        )


def _start_audit_task(input_hash: str, **kwargs) -> asyncio.Task:
    task = asyncio.create_task(
        _process_audit_background_task(input_hash=input_hash, **kwargs),
        name=f"telefonia_audit_{input_hash[:12]}",
    )
    _ACTIVE_AUDIT_TASKS[input_hash] = task
    task.add_done_callback(lambda finished_task: _cleanup_audit_task(input_hash, finished_task))
    return task


def _metadata_flag(metadata: dict, key: str) -> bool:
    value = (metadata or {}).get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim"}


def _recording_sent_to_triage(item: dict) -> bool:
    metadata = _queue_metadata(item)
    motivos = (item or {}).get("motivos_revisao") or []
    if not isinstance(motivos, list):
        motivos = []
    motivos_normalizados = {str(motivo).strip() for motivo in motivos if str(motivo).strip()}
    return bool(
        metadata.get("telefonia_triage_requested_at")
        or metadata.get("telefonia_triage_requested_by")
        or TELEFONIA_TRIAGE_REASON in motivos_normalizados
    )


def _is_huawei_queue_item(item: dict) -> bool:
    return str(_queue_metadata(item).get("origem") or "").lower() == "huawei_sync"


def _recording_media_path(item: dict) -> str:
    metadata = _queue_metadata(item)
    return str(metadata.get("classified_audio_path") or metadata.get("classified_file_path") or "").strip()


def _recording_source_type(item: dict) -> str:
    metadata = _queue_metadata(item)
    return str(metadata.get("source_type") or "").strip().lower()


def _recording_is_audio(item: dict) -> bool:
    source_type = _recording_source_type(item)
    filename = str((item or {}).get("nome_arquivo") or "").lower()
    if source_type == SOURCE_TYPE_PDF or filename.endswith(".pdf"):
        return False
    return True


def _resolve_registered_huawei_operator(metadata: dict, item: dict) -> Optional[dict]:
    candidates = (
        metadata.get("id_huawei"),
        metadata.get("operator_id"),
        metadata.get("operator_id_huawei_real"),
        metadata.get("huawei_agent_id"),
        metadata.get("huawei_work_no"),
        (item or {}).get("operator_id"),
    )
    seen: set[str] = set()
    for raw_id in candidates:
        operator_id = str(raw_id or "").strip()
        if not operator_id or operator_id in seen:
            continue
        seen.add(operator_id)
        rh = operators.buscar_colaborador_por_id_huawei(database.get_connection, operator_id)
        if not rh:
            continue
        return {
            "nome": rh.get("name") or "",
            "id_huawei": rh.get("idHuawei") or operator_id,
            "id_telefonia": rh.get("idTelefonia") or rh.get("idHuawei") or operator_id,
            "setor": rh.get("setor") or "",
            "escala": rh.get("escala") or "",
            "matricula": rh.get("matricula") or "",
            "supervisor": rh.get("supervisor") or "",
            "huawei_registered": True,
        }
    return None


def _is_huawei_recording_item(item: dict) -> bool:
    return _is_huawei_queue_item(item) and _recording_is_audio(item)


def _huawei_recording_direction_block(item: dict) -> Optional[tuple[str, str]]:
    if not _is_huawei_queue_item(item):
        return None

    metadata = _queue_metadata(item)
    sector = normalize_huawei_sector(
        (item or {}).get("setor_previsto")
        or metadata.get("operator_sector_id")
        or metadata.get("operator_sector_real")
        or metadata.get("sector_id")
        or metadata.get("setor")
    )
    if sector in NON_TELEFONIA_SECTORS:
        return "setor_nao_telefonia", sector
    if sector not in OUTBOUND_ONLY_RISK_SECTORS:
        return None

    audio_pre_triage = str(metadata.get("audio_direction_pre_triage") or "").strip().lower()
    if audio_pre_triage == "inbound_quarantine":
        return "receptiva_pretriagem_audio", sector

    direction = resolve_huawei_is_call_in(metadata)
    if direction is True:
        return "receptiva_setor_risco", sector
    if direction is False or audio_pre_triage == "outbound":
        return None
    return "direcao_desconhecida_setor_risco", sector


def _raise_if_huawei_direction_blocked(item: dict) -> None:
    direction_block = _huawei_recording_direction_block(item)
    if not direction_block:
        return
    reason, sector = direction_block
    if reason == "setor_nao_telefonia":
        raise HTTPException(
            status_code=409,
            detail=(
                "Gravacao Huawei bloqueada: setor nao pertence ao modulo Telefonia. "
                f"Setor={sector}; motivo={reason}."
            ),
        )
    raise HTTPException(
        status_code=409,
        detail=(
            "Gravacao Huawei bloqueada: setores de risco aceitam somente "
            f"ligacoes ativas/efetuadas. Setor={sector}; motivo={reason}."
        ),
    )


def _is_visible_telefonia_recording(item: dict) -> bool:
    metadata = _queue_metadata(item)
    status = str((item or {}).get("status") or "").strip().lower()
    if not _is_huawei_recording_item(item):
        return False
    if _metadata_flag(metadata, "archived"):
        return False
    if status in {
        REVIEW_QUEUE_STATUS_AUDITED,
        REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
        REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
        REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    }:
        return False
    if _recording_sent_to_triage(item):
        return False
    if _huawei_recording_direction_block(item):
        return False
    return True


def _coerce_call_started_at(metadata: dict) -> Optional[str]:
    raw = metadata.get("huawei_begin_time") or metadata.get("begin_time")
    if raw is None:
        return None
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _recording_item_from_queue(item: dict) -> dict:
    metadata = _queue_metadata(item)
    input_hash = str((item or {}).get("input_hash") or "").strip()
    status = str((item or {}).get("status") or "").strip()
    media_path = _recording_media_path(item)
    audio_available = bool(input_hash and media_path and _recording_is_audio(item))
    confianca_raw = (item or {}).get("confianca")
    try:
        confianca = float(confianca_raw) if confianca_raw is not None else None
    except (TypeError, ValueError):
        confianca = None
    motivos = (item or {}).get("motivos_revisao") or []
    precisa_revisao = bool(motivos) or (confianca is not None and confianca < 0.6)
    direction_block = _huawei_recording_direction_block(item)
    can_send_to_audit = (
        audio_available
        and status not in {
            REVIEW_QUEUE_STATUS_AUDITED,
            REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
            REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
            REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
        }
        and not direction_block
    )
    call_started_at = _coerce_call_started_at(metadata)
    classification_status = str(metadata.get("classification_status") or "").strip().lower() or None
    return {
        **(item or {}),
        "created_at": (item or {}).get("criado_em") or (item or {}).get("atualizado_em"),
        "call_started_at": call_started_at,
        "operator_name": (item or {}).get("operator_name") or (item or {}).get("operador_previsto") or metadata.get("operator_name"),
        "sector": (item or {}).get("setor_previsto"),
        "classification": (item or {}).get("alerta_previsto"),
        "duration": metadata.get("huawei_duration") or metadata.get("duration") or metadata.get("duracao"),
        "huawei_call_reason": (
            metadata.get("huawei_call_reason")
            or metadata.get("huawei_talk_reason")
            or metadata.get("huawei_talk_remark")
            or metadata.get("talkReason")
            or metadata.get("talkRemark")
        ),
        "huawei_call_reason_code": metadata.get("huawei_call_reason_code"),
        "audio_path": media_path,
        "audio_available": audio_available,
        "audio_url": f"/api/telefonia/recordings/{input_hash}/audio" if audio_available else None,
        "triage_status": status,
        "triage_status_label": _TRIAGE_STATUS_LABELS.get(status, status or "Indefinido"),
        "confianca": confianca,
        "precisa_revisao": precisa_revisao,
        "motivos_revisao": motivos,
        "classification_status": classification_status,
        "classification_error": metadata.get("classification_error") or None,
        "direction_block_reason": direction_block[0] if direction_block else None,
        "direction_block_sector": direction_block[1] if direction_block else None,
        "is_oficial": (item or {}).get("is_oficial", True),
        # Auditor pode auditar diretamente qualquer gravacao com audio disponivel,
        # exceto as ja auditadas ou bloqueadas pela cota mensal.
        "can_send_to_audit": can_send_to_audit,
        # Mantido temporariamente por compat retroativa — sera removido apos
        # remocao do endpoint POST /recordings/{hash}/triage.
        "can_send_to_triage": can_send_to_audit,
    }


def _get_huawei_queue_item_or_404(input_hash: str, *, require_audio: bool = True) -> dict:
    clean_hash = str(input_hash or "").strip()
    if not clean_hash:
        raise HTTPException(status_code=400, detail="Hash da gravacao e obrigatorio.")

    item = classification_review.obter_fila_revisao_classificacao_por_hash(database.get_connection, clean_hash)
    if not item or not _is_huawei_queue_item(item):
        raise HTTPException(status_code=404, detail="Gravacao Huawei nao encontrada.")
    if require_audio and not _recording_is_audio(item):
        raise HTTPException(status_code=404, detail="Gravacao Huawei nao encontrada.")
    return item


def _get_recording_queue_item_or_404(input_hash: str, *, require_audio: bool = True) -> dict:
    clean_hash = str(input_hash or "").strip()
    if not clean_hash:
        raise HTTPException(status_code=400, detail="Hash da gravacao e obrigatorio.")

    item = classification_review.obter_fila_revisao_classificacao_por_hash(database.get_connection, clean_hash)
    if not item:
        raise HTTPException(status_code=404, detail="Gravacao nao encontrada na fila de triagem.")
    if require_audio and not _recording_is_audio(item):
        raise HTTPException(status_code=404, detail="Gravacao de audio nao encontrada na fila de triagem.")
    return item


async def _sync_saved_file_for_manual_audit(audit_id: int, *, criado_por: str) -> bool:
    try:
        return bool(
            await asyncio.to_thread(
                database._sync_arquivo_salvo_for_audit_inline,
                int(audit_id),
                criado_por=criado_por,
            )
        )
    except Exception:
        logger.exception("Falha ao sincronizar auditoria %s em arquivos salvos.", audit_id)
        return False


def _credentials_status() -> Dict[str, Any]:
    aliases = {
        "ak": (("HUAWEI_AK",), ("huawei_ak",)),
        "sk": (("HUAWEI_SK",), ("huawei_sk",)),
        "ccid": (("HUAWEI_CCID", "HUAWEI_CC_ID"), ("huawei_ccid", "huawei_cc_id")),
        "vdn": (("HUAWEI_VDN",), ("huawei_vdn",)),
        "app_key": (("HUAWEI_APP_KEY",), ("huawei_app_key",)),
        "auth_mode": (("HUAWEI_AUTH_MODE",), ("huawei_auth_mode",)),
        "direct_app_key": (("HUAWEI_DIRECT_APP_KEY",), ("huawei_direct_app_key",)),
        "direct_app_secret": (("HUAWEI_DIRECT_APP_SECRET",), ("huawei_direct_app_secret",)),
        "obs_ak": (("HUAWEI_OBS_AK",), ("huawei_obs_ak",)),
        "obs_sk": (("HUAWEI_OBS_SK",), ("huawei_obs_sk",)),
        "obs_bucket": (("HUAWEI_OBS_BUCKET",), ("huawei_obs_bucket",)),
    }
    res = {}
    values: dict[str, str] = {}
    missing = []

    def first_env_value(keys: tuple[str, ...]) -> str:
        for env_key in keys:
            value = str(os.getenv(env_key) or "").strip()
            if value:
                return value
        return ""

    def first_config_value(keys: tuple[str, ...]) -> str:
        for db_key in keys:
            value = str(configuration.get_config_value(database.get_connection, db_key, "") or "").strip()
            if value:
                return value
        return ""

    for k, (env_keys, db_keys) in aliases.items():
        env_val = first_env_value(env_keys)
        db_val = first_config_value(db_keys)

        is_from_env = bool(env_val)
        value = env_val if is_from_env else db_val
        has_value = bool(str(value or "").strip())
        values[k] = str(value or "").strip()

        res[f"huawei_{k}"] = {
            "has_value": has_value,
            "from_env": is_from_env
        }

    auth_mode = (values.get("auth_mode") or "proxy").lower()
    required = ["ccid", "vdn"]
    if auth_mode in OAUTH_DIRECT_MODES:
        required.extend(["direct_app_key", "direct_app_secret"])
    else:
        required.extend(["ak", "sk"])

    for key in required:
        if not values.get(key):
            missing.append(f"huawei_{key}")

    return {
        "configured": not missing,
        "missing": missing,
        "auth_mode": auth_mode,
        "fields": res
    }


def _parse_iso_to_ms(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        # datetime-local do navegador chega sem TZ — assume horario local de Sao Paulo (UTC-3)
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return int(dt.timestamp() * 1000)


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
    global _LAST_SYNC_TASK, _LAST_SYNC_CANCEL_EVENT, _LAST_SYNC_PAUSE_EVENT

    cred = _credentials_status()
    if not cred["configured"]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Credenciais Huawei ausentes: "
                + ", ".join(cred["missing"])
                + ". Preencha em Telefonia > Configuracoes."
            ),
        )

    if _is_sync_running():
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
        begin_ms = _parse_iso_to_ms(body.get("begin_at"))
        end_ms = _parse_iso_to_ms(body.get("end_at"))
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
    global _LAST_SYNC_RUN_ID
    _LAST_SYNC["status"] = "running"
    _LAST_SYNC["started_at"] = _utc_now_iso()
    _LAST_SYNC["finished_at"] = None
    _LAST_SYNC["result"] = None
    _LAST_SYNC["cancel_requested"] = False
    _LAST_SYNC_CANCEL_EVENT = threading.Event()
    _LAST_SYNC_PAUSE_EVENT = threading.Event()
    try:
        _LAST_SYNC_RUN_ID = telefonia.start_telefonia_sync_run(
            database.get_connection,
            started_at=_LAST_SYNC["started_at"],
            horas_retroativas=horas,
            trigger_type="manual",
        )
    except Exception:
        logger.exception("Falha ao iniciar persistencia do sync; segue com estado em memoria.")
        _LAST_SYNC_RUN_ID = None
    if begin_ms is not None and end_ms is not None:
        logger.info("Sync Huawei manual iniciado (janela explicita: %s -> %s)", begin_ms, end_ms)
    else:
        logger.info("Sync Huawei manual iniciado em background (horas_retroativas=%s)", horas)
    _LAST_SYNC_TASK = asyncio.create_task(
        _run_manual_sync(
            horas,
            _LAST_SYNC_CANCEL_EVENT,
            begin_ms,
            end_ms,
            pause_event=_LAST_SYNC_PAUSE_EVENT,
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
    global _LAST_SYNC_PAUSE_EVENT
    if not _is_sync_running() or _LAST_SYNC_CANCEL_EVENT is None:
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": _LAST_SYNC.get("result"),
        }

    _LAST_SYNC_CANCEL_EVENT.set()
    # Limpar pause se existir — cancelar tem prioridade sobre pausar.
    if _LAST_SYNC_PAUSE_EVENT is not None:
        _LAST_SYNC_PAUSE_EVENT.clear()

    _LAST_SYNC["status"] = "cancelling"
    _LAST_SYNC["cancel_requested"] = True

    # Persiste o pedido de cancel para sobreviver restart do pod (v1.3.95).
    if _LAST_SYNC_RUN_ID is not None and _LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_cancel(database.get_connection, _LAST_SYNC_RUN_ID, True)
            telefonia.set_telefonia_sync_pause(database.get_connection, _LAST_SYNC_RUN_ID, False)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, _LAST_SYNC_RUN_ID, status="cancelling")
        except Exception:
            logger.exception("Falha ao persistir cancel_requested (run_id=%s).", _LAST_SYNC_RUN_ID)

    # Hard cancel: aborta a task asyncio. CancelledError sera tratado em
    # _run_manual_sync e gravara status='cancelled' no history.
    if _LAST_SYNC_TASK is not None and not _LAST_SYNC_TASK.done():
        _LAST_SYNC_TASK.cancel()

    logger.info("Cancelamento HARD da coleta Huawei solicitado pelo usuario.")
    return {
        "status": "cancelling",
        "message": "Cancelamento imediato solicitado.",
        "result": _LAST_SYNC.get("result"),
    }


@router.post("/sync/pause")
async def pause_sync(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Pausa a coleta manual em andamento. Diferente do cancelar, pode retomar.

    v1.3.89: estado em memoria. Se o pod reiniciar (Cloud Run), a pausa eh
    perdida e a coleta nao retoma sozinha — auditor precisaria disparar novo
    sync manual."""
    global _LAST_SYNC_PAUSE_EVENT
    if not _is_sync_running():
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": _LAST_SYNC.get("result"),
        }
    if _LAST_SYNC.get("status") == "cancelling":
        return {
            "status": "cancelling",
            "message": "Coleta esta sendo cancelada; pausar nao aplica.",
            "result": _LAST_SYNC.get("result"),
        }
    if _LAST_SYNC_PAUSE_EVENT is None:
        _LAST_SYNC_PAUSE_EVENT = threading.Event()
    _LAST_SYNC_PAUSE_EVENT.set()
    _LAST_SYNC["status"] = "paused"
    # Persiste para a UI mostrar 'paused' apos restart e para o resume vir do DB.
    if _LAST_SYNC_RUN_ID is not None and _LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_pause(database.get_connection, _LAST_SYNC_RUN_ID, True)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, _LAST_SYNC_RUN_ID, status="paused")
        except Exception:
            logger.exception("Falha ao persistir pause_requested (run_id=%s).", _LAST_SYNC_RUN_ID)
    logger.info("Pausa da coleta Huawei solicitada pelo usuario.")
    return {
        "status": "paused",
        "message": "Coleta pausada. Use Retomar para continuar.",
        "result": _LAST_SYNC.get("result"),
    }


@router.post("/sync/resume")
async def resume_sync(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Retoma a coleta pausada (mesma execucao de onde parou)."""
    global _LAST_SYNC_PAUSE_EVENT
    if not _is_sync_running():
        return {
            "status": "idle",
            "message": "Nao existe coleta de ligacoes em andamento.",
            "result": _LAST_SYNC.get("result"),
        }
    if _LAST_SYNC_PAUSE_EVENT is not None:
        _LAST_SYNC_PAUSE_EVENT.clear()
    _LAST_SYNC["status"] = "running"
    if _LAST_SYNC_RUN_ID is not None and _LAST_SYNC_RUN_ID >= 0:
        try:
            telefonia.set_telefonia_sync_pause(database.get_connection, _LAST_SYNC_RUN_ID, False)
            telefonia.heartbeat_telefonia_sync_run(database.get_connection, _LAST_SYNC_RUN_ID, status="running")
        except Exception:
            logger.exception("Falha ao persistir resume (run_id=%s).", _LAST_SYNC_RUN_ID)
    logger.info("Retomada da coleta Huawei solicitada pelo usuario.")
    return {
        "status": "running",
        "message": "Coleta retomada.",
        "result": _LAST_SYNC.get("result"),
    }


@router.post("/sync/clear")
async def clear_sync_report(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Limpa o resultado do ultimo sync manual da memoria (para ocultar o relatorio na UI)."""
    global _LAST_SYNC
    if _is_sync_running():
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel limpar o relatorio enquanto um sync esta em andamento."
        )
    _LAST_SYNC["result"] = None
    _LAST_SYNC["started_at"] = None
    _LAST_SYNC["finished_at"] = None
    _LAST_SYNC["status"] = "idle"
    return {"status": "ok", "message": "Relatorio de execucao limpo com sucesso."}


async def _run_manual_sync(
    horas: float,
    cancel_event: threading.Event | None = None,
    begin_time_ms: Optional[int] = None,
    end_time_ms: Optional[int] = None,
    pause_event: threading.Event | None = None,
) -> None:
    global _LAST_SYNC_CANCEL_EVENT, _LAST_SYNC_PAUSE_EVENT, _LAST_SYNC_RUN_ID
    run_id = _LAST_SYNC_RUN_ID

    def _finalize(*, status: str, baixadas: int, enfileiradas: int, erros: int, mensagem: Optional[str]) -> None:
        finished_at = _utc_now_iso()
        _LAST_SYNC["finished_at"] = finished_at
        if run_id is not None and run_id >= 0:
            try:
                telefonia.finalize_telefonia_sync_run(
                    database.get_connection,
                    run_id=run_id,
                    finished_at=finished_at,
                    status=status,
                    baixadas=baixadas,
                    enfileiradas=enfileiradas,
                    erros_totais=erros,
                    mensagem_erro=mensagem,
                )
            except Exception:
                logger.exception("Falha ao finalizar persistencia do sync (run_id=%s).", run_id)
        else:
            # Fallback (run_id nao foi obtido na criacao): mantem o INSERT historico.
            try:
                telefonia.save_telefonia_sync_history(
                    database.get_connection,
                    started_at=_LAST_SYNC["started_at"],
                    finished_at=finished_at,
                    status=status,
                    horas_retroativas=horas,
                    baixadas=baixadas,
                    enfileiradas=enfileiradas,
                    erros_totais=erros,
                    mensagem_erro=mensagem,
                    trigger_type="manual",
                )
            except Exception:
                logger.exception("Falha ao gravar history de sync (fallback).")

    try:
        def _update_progress(stage: str, completed: int, total: int) -> None:
            _LAST_SYNC["progress"] = {
                "stage": stage,
                "completed": completed,
                "total": total,
            }
            # Heartbeat: garante que o reconcile do startup nao marque o run como interrupted.
            if run_id is not None and run_id >= 0:
                try:
                    telefonia.heartbeat_telefonia_sync_run(database.get_connection, run_id=run_id)
                except Exception:
                    logger.debug("Heartbeat falhou (run_id=%s); ignorado.", run_id, exc_info=True)

        result = await executar_sync_huawei(
            horas_retroativas=horas,
            should_cancel=cancel_event.is_set if cancel_event is not None else None,
            should_pause=pause_event.is_set if pause_event is not None else None,
            begin_time_ms=begin_time_ms,
            end_time_ms=end_time_ms,
            progress_callback=_update_progress,
            is_manual=True,
        )
    except asyncio.CancelledError:
        # Hard cancel via _LAST_SYNC_TASK.cancel() — finalizar com estado consistente.
        logger.info("Coleta Huawei manual cancelada (hard) pelo usuario.")
        _LAST_SYNC["status"] = "cancelled"
        _LAST_SYNC["result"] = {
            "status": "cancelled",
            "message": "Coleta cancelada pelo usuario antes de concluir.",
            "cancelado": True,
        }
        _LAST_SYNC["cancel_requested"] = False
        _finalize(status="cancelled", baixadas=0, enfileiradas=0, erros=0, mensagem="cancelado_pelo_usuario")
        if _LAST_SYNC_CANCEL_EVENT is cancel_event:
            _LAST_SYNC_CANCEL_EVENT = None
        if _LAST_SYNC_PAUSE_EVENT is pause_event:
            _LAST_SYNC_PAUSE_EVENT = None
        if _LAST_SYNC_RUN_ID == run_id:
            _LAST_SYNC_RUN_ID = None
        # Nao re-raise: a task termina graciosamente.
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao executar sync Huawei manual")
        _LAST_SYNC["status"] = "failed"
        _LAST_SYNC["result"] = {"status": "error", "message": str(exc)}
        _LAST_SYNC["cancel_requested"] = False
        _finalize(status="failed", baixadas=0, enfileiradas=0, erros=1, mensagem=str(exc))
        if _LAST_SYNC_CANCEL_EVENT is cancel_event:
            _LAST_SYNC_CANCEL_EVENT = None
        if _LAST_SYNC_PAUSE_EVENT is pause_event:
            _LAST_SYNC_PAUSE_EVENT = None
        if _LAST_SYNC_RUN_ID == run_id:
            _LAST_SYNC_RUN_ID = None
        return

    _LAST_SYNC["status"] = result.get("status", "ok")
    _LAST_SYNC["result"] = result
    _LAST_SYNC["cancel_requested"] = False

    _finalize(
        status=_LAST_SYNC["status"],
        baixadas=result.get("baixadas", 0),
        enfileiradas=result.get("enfileiradas", 0),
        erros=1 if _LAST_SYNC["status"] == "error" else 0,
        mensagem=result.get("message") or result.get("erro"),
    )
    if _LAST_SYNC_CANCEL_EVENT is cancel_event:
        _LAST_SYNC_CANCEL_EVENT = None
    if _LAST_SYNC_PAUSE_EVENT is pause_event:
        _LAST_SYNC_PAUSE_EVENT = None
    if _LAST_SYNC_RUN_ID == run_id:
        _LAST_SYNC_RUN_ID = None


@router.get("/sync/status")
async def sync_status(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    engine_enabled = (os.getenv("ENABLE_HUAWEI_SYNC", "false") or "").strip().lower() == "true"
    cron_token_configured = bool((os.getenv("CRON_SECRET_TOKEN", "") or "").strip())
    try:
        raw_val = configuration.get_config_value(database.get_connection, "telefonia_cron_sync_ativa", "true")
        cron_db_flag = str(raw_val or "").strip().lower() == "true"
    except Exception:
        cron_db_flag = True

    status_dict = dict(_LAST_SYNC)
    if _is_sync_running() and status_dict.get("status") not in ("running", "cancelling"):
        status_dict["status"] = "running"
        status_dict["message"] = "Coleta em andamento (background/outro worker)."

    return {
        **status_dict,
        "credentials": _credentials_status(),
        "engine_enabled": engine_enabled,
        "cron_token_configured": cron_token_configured,
        "cron_db_flag": cron_db_flag,
    }


@router.get("/sync/history")
async def sync_history(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Retorna historico de execucoes."""
    try:
        items = telefonia.list_telefonia_sync_history(database.get_connection, limit=50)
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"Erro ao listar historico: {e}")
        return {"items": [_LAST_SYNC] if _LAST_SYNC.get("started_at") else [], "total": 0}


@router.get("/recordings")
async def listar_gravacoes(
    limit: Optional[int] = None,
    operator: Optional[str] = None,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Lista itens recentes vindos da Huawei na fila de revisao de triagem."""
    try:
        fila = classification_review.listar_fila_revisao_classificacao(database.get_connection,
            limit=limit,
            status="all",
            origem="huawei_sync",
            order_by="recent"
        )
    except Exception:
        logger.exception("Falha ao listar fila de revisao")
        fila = []

    vindos_huawei = []
    search_term = operator.strip().lower() if operator else None

    for item in (fila or []):
        if not _is_visible_telefonia_recording(item):
            continue

        parsed_item = _recording_item_from_queue(item)
        if search_term:
            op_name = str(parsed_item.get("operator_name") or "").strip().lower()
            if search_term not in op_name:
                continue

        vindos_huawei.append(parsed_item)

    return {"items": vindos_huawei, "total": len(vindos_huawei)}
@router.delete("/recordings")
def remover_todas_gravacoes(_user: dict = Depends(require_admin)):
    """
    Remove da tela e da fila todas as ligações que ainda não foram para triagem
    (que não estão em status terminal nem em triagem manual).
    """
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        
        # Pega as hashes e os IDs do Huawei para apagar em lote
        cursor.execute(
            """
            SELECT input_hash, metadata_json 
            FROM fila_revisao_classificacao 
            WHERE status NOT IN ('audited', 'monthly_capped', 'reviewed', 'needs_manual_triage', 'blocked_operator')
            """
        )
        rows = cursor.fetchall()
        
        hashes_to_delete = []
        huawei_ids_to_delete = []
        
        for row in rows:
            input_hash = row["input_hash"]
            raw_meta = row["metadata_json"]
            meta = json_loads(raw_meta, {})
            if not isinstance(meta, dict):
                meta = {}
                
            if meta.get("archived"):
                continue
                
            # Apenas apagar gravações que vieram da integração Huawei
            if str(meta.get("origem") or "").lower() != "huawei_sync":
                continue

            # Depois do envio, a posse visual passa para a Triagem. O botao
            # "Limpar Pendentes" da Telefonia nao deve apagar esses itens.
            if meta.get("telefonia_triage_requested_at") or meta.get("telefonia_triage_requested_by"):
                continue
                
            # Não excluir itens que já estão na Triagem prontos para revisão manual
            if meta.get("classification_status") == "done":
                continue
                
            hashes_to_delete.append(input_hash)
            if meta.get("huawei_call_id"):
                huawei_ids_to_delete.append(str(meta.get("huawei_call_id")))
                
        if hashes_to_delete:
            cursor.execute(
                """
                DELETE FROM fila_revisao_classificacao 
                WHERE input_hash = ANY(%s)
                """,
                (hashes_to_delete,)
            )

        if huawei_ids_to_delete:
            cursor.execute(
                "DELETE FROM huawei_sync_logs WHERE call_id = ANY(%s)",
                (huawei_ids_to_delete,)
            )
            
        conn.commit()
        return {"status": "ok", "message": f"{len(hashes_to_delete)} ligações removidas com sucesso.", "deleted": len(hashes_to_delete)}
    except Exception as exc:
        logger.exception("Falha ao remover todas as gravacoes: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao limpar gravações pendentes.")
    finally:
        conn.close()

@router.delete("/recordings/{input_hash}")
def remover_gravacao(input_hash: str, _user: dict = Depends(require_admin)):
    """
    Remove uma gravacao da fila.
    - Se estiver auditada/cota mensal: apenas marca como arquivada para sumir da tela.
    - Se estiver pendente ou em outro status: apaga do banco para permitir novo download.
    """
    item = _get_recording_queue_item_or_404(input_hash, require_audio=False)
    status = str(item.get("status") or "").strip().lower()
    metadata = _queue_metadata(item)
    huawei_call_id = str(metadata.get("huawei_call_id") or "").strip()

    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        # Apenas "oculta" do frontend marcando metadata.archived=true.
        # Nao mexemos no status de fila (que e dominio reservado a estados validos).
        ok = classification_review.atualizar_status_fila_revisao_classificacao(database.get_connection, 
            input_hash,
            status=status,
            metadata_merge={
                "archived": True,
                "archived_at": _utc_now_iso(),
            },
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Gravacao nao encontrada.")
        return {"status": "ok", "message": "Ligacao auditada foi ocultada da fila.", "action": "archived"}

    # Exclui de fato para que a coleta possa baixa-la novamente (se for oficial).
    # is_oficial vem do LATERAL JOIN em obter_fila_revisao_classificacao_por_hash;
    # default True garante que ao redownload nao seja bloqueado quando o campo
    # nao puder ser calculado (ex: testes legados sem o JOIN).
    conn = database.get_connection()
    try:
        cursor = conn.cursor()

        is_oficial = bool(item.get("is_oficial", True))

        cursor.execute(
            "DELETE FROM fila_revisao_classificacao WHERE input_hash = %s",
            (input_hash,),
        )
        if huawei_call_id:
            if is_oficial:
                # Permite que o proximo sync redescubra esta chamada na Huawei.
                cursor.execute(
                    "DELETE FROM huawei_sync_logs WHERE call_id = %s",
                    (huawei_call_id,),
                )
            else:
                # Option A: Operador sem cadastro. Se reimportarmos, volta com erro. 
                # Portanto, ignoramos permanentemente no sync log.
                cursor.execute(
                    """
                    INSERT INTO huawei_sync_logs (call_id, status, failure_reason, sincronizado_em)
                    VALUES (%s, 'skipped_operator', 'operador_huawei_nao_cadastrado', CURRENT_TIMESTAMP)
                    ON CONFLICT (call_id) DO UPDATE
                    SET status = 'skipped_operator',
                        failure_reason = 'operador_huawei_nao_cadastrado',
                        sincronizado_em = CURRENT_TIMESTAMP;
                    """,
                    (huawei_call_id,)
                )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": "Ligacao excluida.", "action": "deleted"}

@router.get("/recordings/{input_hash}/audio")
def obter_audio_gravacao(
    input_hash: str,
    _user: dict = Depends(require_admin),
):
    """Serve o audio classificado de uma gravacao da fila para player autenticado."""
    item = _get_recording_queue_item_or_404(input_hash)
    media_path = _recording_media_path(item)
    if not media_path or not _recording_is_audio(item):
        raise HTTPException(status_code=404, detail="Audio da gravacao nao encontrado.")

    stream = open_classified_audio_stream(media_path, input_hash=input_hash)
    if stream is None:
        raise HTTPException(status_code=404, detail="Arquivo de audio da gravacao nao encontrado.")

    iterator, content_length = stream
    filename = str(item.get("nome_arquivo") or media_path or "gravacao.wav")
    safe_name = _safe_filename(filename, fallback="gravacao.wav")
    headers = {"Content-Disposition": f'inline; filename="{safe_name}"'}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return StreamingResponse(
        iterator,
        media_type=get_mime_type(filename) or "audio/wav",
        headers=headers,
    )


@router.post("/recordings/{input_hash}/triage")
def enviar_gravacao_para_triagem(
    input_hash: str,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Coloca uma gravacao Huawei na triagem manual."""
    item = _get_huawei_queue_item_or_404(input_hash)
    status = str(item.get("status") or "").strip()

    if status in {
        REVIEW_QUEUE_STATUS_REVIEWED,
        REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
        REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    }:
        return {
            "success": True,
            "status": status,
            "message": "Gravacao ja esta na triagem manual.",
        }
    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(
            status_code=409,
            detail="Gravacao nao pode voltar para triagem a partir do status atual.",
        )
    _raise_if_huawei_direction_blocked(item)

    updated = classification_review.atualizar_status_fila_revisao_classificacao(database.get_connection, 
        input_hash,
        status=REVIEW_QUEUE_STATUS_PENDING,
        motivos_revisao_append=[TELEFONIA_TRIAGE_REASON],
        metadata_merge={
            "telefonia_triage_requested_at": datetime.now(timezone.utc).isoformat(),
            "telefonia_triage_requested_by": user.get("username") or user.get("sub") or "admin",
            "is_manual": True,
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Gravacao Huawei nao encontrada.")

    return {
        "success": True,
        "status": REVIEW_QUEUE_STATUS_PENDING,
        "message": "Gravacao enviada para triagem manual.",
    }


# Concorrencia global das classificacoes manuais (protege o Azure mesmo com varios
# admins triando ao mesmo tempo). Cap via TELEFONIA_CLASSIFY_MAX_CONCURRENCY (default 3).
# Lazy e por event-loop: um Semaphore de modulo se prende ao loop no 1o uso, e os
# testes rodam asyncio.run varias vezes com loops diferentes.
_classify_semaphore_state: Optional[tuple[Any, asyncio.Semaphore]] = None


def _classify_max_concurrency() -> int:
    raw = os.getenv("TELEFONIA_CLASSIFY_MAX_CONCURRENCY", "3")
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 3


def _get_classify_semaphore() -> asyncio.Semaphore:
    global _classify_semaphore_state
    loop = asyncio.get_running_loop()
    if _classify_semaphore_state is None or _classify_semaphore_state[0] is not loop:
        _classify_semaphore_state = (loop, asyncio.Semaphore(_classify_max_concurrency()))
    return _classify_semaphore_state[1]


@router.post("/recordings/{input_hash}/classify")
async def classificar_gravacao_manual(
    input_hash: str,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Roda a classificacao IA (setor/alerta) em um audio ja baixado da Huawei."""
    item = _get_huawei_queue_item_or_404(input_hash)
    status = str(item.get("status") or "").strip()

    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(status_code=409, detail="Gravacao ja foi auditada.")
    _raise_if_huawei_direction_blocked(item)

    metadata = _queue_metadata(item)
    media_path = metadata.get("classified_audio_path") or metadata.get("classified_file_path")
    if not media_path:
        raise HTTPException(status_code=404, detail="Caminho de audio ausente.")

    from core.automation import load_classified_audio
    audio_bytes = load_classified_audio(media_path, input_hash=input_hash)
    if not audio_bytes:
        raise HTTPException(status_code=404, detail="Arquivo de audio indisponivel.")

    filename = str(item.get("nome_arquivo") or "gravacao.wav")

    # Montar operador
    operator_id = str(metadata.get("operator_id") or metadata.get("id_huawei") or "").strip()
    operator_name = str(metadata.get("operator_name") or item.get("operador_previsto") or "").strip()
    operador = _resolve_registered_huawei_operator(metadata, item)
    if operador is None:
        huawei_id_hint = (
            operator_id
            or str(metadata.get("huawei_agent_id") or "").strip()
            or str(metadata.get("huawei_work_no") or "").strip()
        )
        detail = (
            "Operador Huawei nao cadastrado ou nao auditavel. "
            "Cadastre o operador com ID Huawei no modulo Operadores antes de classificar."
        )
        if huawei_id_hint:
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(
            status_code=400,
            detail=(
                "Gravacao Huawei sem ID Huawei na metadata. "
                "Reprocesse a sincronizacao D-1 antes de classificar."
            ),
        )

    from core.huawei_sync import _classificar_audio_huawei, _aplicar_auto_classificacao, _marcar_classificacao_status, _operator_truth_snapshot
    operator_truth = _operator_truth_snapshot(operador)

    try:
        async with _get_classify_semaphore():
            result = await _classificar_audio_huawei(
                audio_bytes,
                filename,
                operador,
                native_call_reason=str(metadata.get("huawei_call_reason") or "").strip() or None,
                native_call_reason_code=str(metadata.get("huawei_call_reason_code") or "").strip() or None,
            )
    except Exception as exc:
        _marcar_classificacao_status(input_hash, status="error", erro=str(exc))
        raise HTTPException(status_code=500, detail=f"Erro na classificacao: {exc}")

    sector_id = metadata.get("operator_sector_id") or operator_truth.get("setor_id") or getattr(result, "sector_id", None) or "desconhecido"
    alert_id = getattr(result, "alert_id", None) or "desconhecido"
    confidence = getattr(result, "confidence", 0.0) or 0.0

    _aplicar_auto_classificacao(
        input_hash,
        sector_id=sector_id,
        alert_id=alert_id,
        operator_name=operator_truth.get("nome") or getattr(result, "operator_name", None) or operator_name or None,
        confianca=confidence,
        needs_review=True,  # Força needs_review=True para manter o status='pending' na tela de Triagem
        review_reasons=list(getattr(result, "review_reasons", []) or []),
        review_priority=str(getattr(result, "review_priority", "low") or "low"),
        erro=getattr(result, "error", None),
        id_huawei=getattr(result, "id_huawei", None) or operator_truth.get("id_huawei"),
        matricula=getattr(result, "matricula", None) or operator_truth.get("matricula"),
    )

    return {
        "success": True,
        "message": "Classificacao concluida.",
        "sector_id": sector_id,
        "alert_id": alert_id,
    }


AUDIT_TASK_INFLIGHT_TIMEOUT = timedelta(minutes=10)


def _parse_iso_to_aware(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _get_telefonia_monthly_audit_quota() -> int:
    try:
        return _get_monthly_audit_quota()
    except Exception as exc:
        if os.getenv("PYTEST_CURRENT_TEST"):
            logger.info("Telefonia: usando cota mensal padrao em teste isolado: %s", exc)
            return 2
        logger.exception("Falha ao carregar cota mensal configurada para Telefonia")
        raise HTTPException(status_code=503, detail="Falha ao validar configuracao de cota mensal.")


def _extract_audit_context(item: dict) -> Dict[str, Any]:
    pipeline_context = repair_queue_audit_context(
        build_queue_audit_context(item, origin=AUDIT_ORIGIN_TELEFONIA_MANUAL)
    )
    return pipeline_context.to_router_context()


def _validate_audit_context_or_raise(ctx: Dict[str, Any], item: dict) -> Dict[str, Any]:
    """Valida o contexto da auditoria. Retorna ctx ajustado (operator_name/id resolvidos)."""
    if not ctx["alert_id"] or is_unknown_value(ctx["alert_id"]):
        raise HTTPException(status_code=400, detail="Alerta previsto nao encontrado no item.")
    if not ctx["sector_id"] or is_unknown_value(ctx["sector_id"]):
        raise HTTPException(status_code=400, detail="Setor previsto nao encontrado no item.")
    if not ctx["operator_name"] or is_unknown_value(ctx["operator_name"]):
        raise HTTPException(status_code=400, detail="Operador previsto nao encontrado no item.")

    try:
        from repositories.admin_criteria import get_criteria

        criterios = get_criteria(database.get_connection, alert_id=ctx["alert_id"])
        if criterios is not None and len(criterios) == 0:
            raise HTTPException(
                status_code=400,
                detail=f"Alerta '{ctx['alert_id']}' nao possui criterios cadastrados em audit_criteria.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Validacao de criterios pulada por erro de leitura para alerta %s: %s", ctx["alert_id"], exc)

    if ctx["sector_id"] and get_sector_prompt_rules(ctx["sector_id"]) is None:
        raise HTTPException(
            status_code=400,
            detail=f"Setor '{ctx['sector_id']}' nao reconhecido pelas regras de auditoria.",
        )

    resolved_operator = operators.resolve_auditable_colaborador(
        database.get_connection, ctx["operator_name"], ctx["operator_id"], ctx["sector_id"]
    )
    if not resolved_operator:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Operador '{ctx['operator_name']}' nao auditavel para o setor '{ctx['sector_id']}'. "
                "Selecione um colaborador ativo no modulo Operadores."
            ),
        )
    ctx["operator_name"] = resolved_operator.get("name") or ctx["operator_name"]
    ctx["operator_id"] = (
        resolved_operator.get("matricula")
        or resolved_operator.get("preferredId")
        or ctx["operator_id"]
    )
    apply_resolved_operator(
        coerce_pipeline_context(ctx.get("pipeline_context")),
        resolved_operator,
        fallback_operator_name=ctx["operator_name"],
        fallback_operator_id=ctx["operator_id"],
    )

    quota_date = QuotaGatekeeper.resolve_quota_datetime(_queue_metadata(item))
    quota_limit = _get_telefonia_monthly_audit_quota()
    try:
        current_count = audits.get_operator_audit_count_for_month(
            database.get_connection,
            ctx["operator_name"],
            quota_date.year,
            quota_date.month,
            operator_id=ctx["operator_id"],
        )
    except Exception as exc:
        if os.getenv("PYTEST_CURRENT_TEST"):
            logger.info("Telefonia: ignorando falha de cota mensal em teste isolado: %s", exc)
            current_count = 0
        else:
            logger.exception("Falha ao consultar cota mensal do operador %s", ctx["operator_name"])
            raise HTTPException(status_code=503, detail="Falha ao validar cota mensal do operador.")
    if current_count >= quota_limit:
        input_hash = str((item or {}).get("input_hash") or "").strip()
        if input_hash:
            try:
                classification_review.atualizar_status_fila_revisao_classificacao(
                    database.get_connection,
                    input_hash,
                    status=REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
                    erro=f"Cota mensal de {quota_limit} auditorias atingida",
                    motivos_revisao_append=["cota_mensal_atingida"],
                    metadata_merge={
                        "monthly_cap_period": quota_date.strftime("%Y-%m"),
                        "monthly_cap_operator": ctx["operator_name"],
                        "monthly_cap_operator_id": ctx["operator_id"] or "",
                        "monthly_cap_count": current_count,
                        "monthly_cap_limit": quota_limit,
                    },
                )
            except Exception:
                logger.exception("Falha ao marcar fila Telefonia como monthly_capped para %s", input_hash)
        raise HTTPException(
            status_code=429,
            detail=(
                f"Cota mensal de {quota_limit} auditorias atingida para o operador "
                f"{ctx['operator_name']} em {quota_date.month:02d}/{quota_date.year}."
            ),
        )

    media_path = _recording_media_path(item)
    if not media_path:
        raise HTTPException(status_code=404, detail="Arquivo classificado da gravacao nao encontrado.")
    ctx["media_path"] = media_path
    pipeline_context = coerce_pipeline_context(ctx.get("pipeline_context"))
    if pipeline_context is not None:
        pipeline_context.media_path = media_path
    return ctx


async def _process_audit_background_task(
    *,
    input_hash: str,
    sector_id: str,
    alert_id: str,
    operator_name: str,
    operator_id: str,
    source_type: str,
    filename: str,
    media_path: str,
    criado_por: str,
    audit_requested_by: Optional[str] = None,
    pipeline_context: Optional[dict] = None,
) -> None:
    """Tarefa em background: roda IA + persiste audit + sync arquivos_salvos + atualiza fila.

    Erros sao capturados e registrados na metadata da fila como `audit_task_status='failed'`
    para o frontend poder informar o usuario via polling.
    """
    try:
        _raise_if_audit_task_cancel_requested(input_hash)
        try:
            media_bytes = load_classified_audio(media_path, input_hash=input_hash)
        except Exception as exc:
            raise RuntimeError(f"Erro ao carregar midia: {exc}") from exc
        if not media_bytes:
            raise RuntimeError("Arquivo classificado da gravacao esta vazio ou nao foi encontrado.")

        mime_type = "application/pdf" if source_type == SOURCE_TYPE_PDF else get_mime_type(filename)
        alert = _build_alert_from_classification(sector_id, alert_id)
        audit_pipeline_context = coerce_pipeline_context(pipeline_context)
        _raise_if_audit_task_cancel_requested(input_hash)

        if source_type == SOURCE_TYPE_PDF:
            from core.audit import process_pdf_audit

            result, result_hash, from_cache = await process_pdf_audit(
                media_bytes,
                mime_type,
                alert,
                operator_name,
                operator_id,
                sector_id,
                pipeline_context=audit_pipeline_context,
            )
        else:
            result, result_hash, from_cache = await process_audit_with_ai(
                media_bytes,
                mime_type,
                alert,
                operator_name,
                operator_id,
                sector_id,
                pipeline_context=audit_pipeline_context,
            )

        _raise_if_audit_task_cancel_requested(input_hash)
        audit_input_hash = result_hash or input_hash
        audit_id = database.persist_audit_artifacts(
            result,
            from_cache=from_cache,
            input_hash=audit_input_hash,
            alert_id=alert_id,
            alert_label=alert.label,
            operator_id=operator_id,
            sector_id=sector_id,
            audio_bytes=media_bytes if source_type in {"", SOURCE_TYPE_AUDIO} else None,
            audio_mime_type=mime_type if source_type in {"", SOURCE_TYPE_AUDIO} else None,
            original_filename=filename,
            status=AUDIT_STATUS_AWAITING_PAIR,
            criado_por=criado_por,
            sync_saved_file=False,
        )
        if not audit_id:
            raise RuntimeError("persist_audit_artifacts retornou audit_id vazio.")

        saved_file_available = await _sync_saved_file_for_manual_audit(audit_id, criado_por=criado_por)
        if not saved_file_available:
            logger.warning(
                "Auditoria %s persistida, mas a sincronizacao imediata em arquivos salvos nao confirmou criacao.",
                audit_id,
            )

        classification_review.atualizar_status_fila_revisao_classificacao(
            database.get_connection,
            input_hash,
            status=REVIEW_QUEUE_STATUS_AUDITED,
            motivos_revisao_append=["auditada_instantaneamente"],
            metadata_merge={
                "telefonia_audit_requested_at": _utc_now_iso(),
                "telefonia_audit_requested_by": audit_requested_by or criado_por,
                "audit_id": audit_id,
                "audit_input_hash": audit_input_hash,
                "classification_status": "done",
                "audit_task_status": "completed",
                "audit_task_completed_at": _utc_now_iso(),
                "audit_task_saved_file_available": bool(saved_file_available),
                "audit_task_error": None,
                "audit_pipeline": audit_pipeline_context.to_audit_metadata() if audit_pipeline_context else None,
            },
        )
    except asyncio.CancelledError:
        logger.info("Audit background task cancelada para input_hash=%s", input_hash)
        raise
    except Exception as exc:
        logger.exception("Audit background task falhou para input_hash=%s: %s", input_hash, exc)
        try:
            classification_review.atualizar_status_fila_revisao_classificacao(
                database.get_connection,
                input_hash,
                status=REVIEW_QUEUE_STATUS_PENDING,
                metadata_merge={
                    "audit_task_status": "failed",
                    "audit_task_failed_at": _utc_now_iso(),
                    "audit_task_error": str(exc)[:500],
                },
            )
        except Exception:
            logger.exception("Falha ao registrar erro do audit background para input_hash=%s", input_hash)


class AuditRecordingRequest(BaseModel):
    force: bool = False


@router.post("/recordings/{input_hash}/audit", status_code=202)
async def auditar_instantaneamente_gravacao(
    input_hash: str,
    payload: AuditRecordingRequest | None = None,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Agenda auditoria em background e retorna 202 imediatamente.

    O frontend deve consultar GET /recordings/{hash}/audit-status para acompanhar.
    Padrao classico de long-running task: validacoes rapidas + agendamento + polling.

    Body opcional `{"force": true}` (v1.3.88): permite ao auditor forcar o envio
    sobrescrevendo gates de needs_manual_triage e direction guardrail. NAO
    sobrescreve `blocked_operator` (operador sem cadastro falha mesmo) nem
    auditorias ja concluidas/em cota mensal. A automacao (ciclo) nunca passa
    por aqui — ela so processa itens em ready_for_audit.
    """
    force = bool(payload.force) if payload is not None else False
    item = _get_recording_queue_item_or_404(input_hash)
    status_atual = str(item.get("status") or "").strip()

    if status_atual in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(status_code=409, detail="Gravacao ja foi auditada.")
    if status_atual == REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR:
        # Force nao supera operador inexistente: o pipeline vai falhar ao
        # resolver o colaborador. Resposta clara em vez de deixar quebrar adiante.
        raise HTTPException(
            status_code=409,
            detail="Operador nao cadastrado. Cadastre no modulo Operadores antes de auditar.",
        )
    if status_atual == REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE and not force:
        # v1.3.87: motivos apenas de transcricao liberam audit automaticamente.
        # Outros motivos exigem force=true (v1.3.88) — auditor decide com base
        # no que ele ve na fila e assume a responsabilidade.
        motivos = item.get("motivos_revisao") or []
        if not isinstance(motivos, list):
            motivos = []
        only_transcription = bool(motivos) and all(
            str(m).strip().lower().startswith("transcricao_")
            for m in motivos
            if str(m).strip()
        )
        if not only_transcription:
            raise HTTPException(
                status_code=409,
                detail="Gravacao precisa de correcao manual antes da auditoria.",
            )
    if not force:
        _raise_if_huawei_direction_blocked(item)

    metadata = _queue_metadata(item)
    audit_task_status = str(metadata.get("audit_task_status") or "").strip().lower()
    if audit_task_status == "processing":
        started_at = _parse_iso_to_aware(metadata.get("audit_task_started_at"))
        if started_at and (datetime.now(timezone.utc) - started_at) < AUDIT_TASK_INFLIGHT_TIMEOUT:
            raise HTTPException(
                status_code=409,
                detail="Auditoria ja em processamento. Aguarde a conclusao ou refresh do status.",
            )

    ctx = _extract_audit_context(item)
    ctx = _validate_audit_context_or_raise(ctx, item)
    pipeline_context = coerce_pipeline_context(ctx.get("pipeline_context"))

    audit_requested_by = user.get("username") or user.get("sub") or "telefonia_manual"
    criado_por = _resolve_audit_created_by_for_queue_item(item, user)
    started_at = _utc_now_iso()
    metadata_merge: Dict[str, Any] = {
        "audit_task_status": "processing",
        "audit_task_started_at": started_at,
        "audit_task_requested_by": audit_requested_by,
        "audit_task_error": None,
    }
    if force:
        metadata_merge["audit_forced"] = True
        metadata_merge["audit_forced_by"] = audit_requested_by
        metadata_merge["audit_forced_at"] = started_at
    claim = classification_review.tentar_iniciar_processamento_auditoria(
        database.get_connection,
        input_hash,
        status=status_atual or REVIEW_QUEUE_STATUS_PENDING,
        metadata_merge=metadata_merge,
        inflight_timeout_seconds=int(AUDIT_TASK_INFLIGHT_TIMEOUT.total_seconds()),
        ignore_status_block=force,
    )
    if not claim.get("started"):
        reason = str(claim.get("reason") or "")
        if reason == "processing":
            raise HTTPException(
                status_code=409,
                detail="Auditoria ja em processamento. Aguarde a conclusao ou refresh do status.",
            )
        if reason == "blocked_status":
            raise HTTPException(status_code=409, detail="Gravacao nao pode ser auditada a partir do status atual.")
        raise HTTPException(status_code=404, detail="Gravacao nao encontrada para iniciar auditoria.")

    _start_audit_task(
        input_hash,
        sector_id=ctx["sector_id"],
        alert_id=ctx["alert_id"],
        operator_name=ctx["operator_name"],
        operator_id=ctx["operator_id"],
        source_type=ctx["source_type"],
        filename=ctx["filename"],
        media_path=ctx["media_path"],
        criado_por=criado_por,
        audit_requested_by=audit_requested_by,
        pipeline_context=pipeline_context.to_audit_metadata() if pipeline_context else None,
    )

    return {
        "success": True,
        "status": "processing",
        "input_hash": input_hash,
        "started_at": started_at,
        "message": "Auditoria iniciada em background. Acompanhe via /audit-status.",
    }

async def _run_audit_task_and_cleanup(input_hash: str, **kwargs):
    task = _start_audit_task(input_hash, **kwargs)
    try:
        await task
    except asyncio.CancelledError:
        pass

@router.get("/recordings/{input_hash}/audit-status")
async def consultar_status_auditoria(
    input_hash: str,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Retorna o estado atual do background task de auditoria para um item da fila.

    Estados: 'idle' (nenhum task), 'processing', 'completed', 'failed'.
    Frontend deve fazer polling enquanto status == 'processing'.
    """
    item = _get_recording_queue_item_or_404(input_hash, require_audio=False)
    metadata = _queue_metadata(item)
    fila_status = str(item.get("status") or "").strip()
    task_status = str(metadata.get("audit_task_status") or "").strip().lower()

    if fila_status == REVIEW_QUEUE_STATUS_AUDITED:
        return {
            "status": "completed",
            "audit_id": metadata.get("audit_id"),
            "saved_file_available": bool(metadata.get("audit_task_saved_file_available", True)),
            "completed_at": metadata.get("audit_task_completed_at"),
        }

    if task_status == "failed":
        return {
            "status": "failed",
            "error_message": metadata.get("audit_task_error") or "Erro desconhecido.",
            "failed_at": metadata.get("audit_task_failed_at"),
        }

    if task_status == "processing":
        started_at = _parse_iso_to_aware(metadata.get("audit_task_started_at"))
        is_stale = (
            started_at is not None
            and (datetime.now(timezone.utc) - started_at) >= AUDIT_TASK_INFLIGHT_TIMEOUT
        )
        return {
            "status": "stale" if is_stale else "processing",
            "started_at": metadata.get("audit_task_started_at"),
        }

    return {"status": "idle"}


@router.delete("/recordings/{input_hash}/audit")
async def cancelar_auditoria(
    input_hash: str,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Cancela a execução atual de uma auditoria em background, voltando ao status pendente."""
    item = _get_recording_queue_item_or_404(input_hash, require_audio=False)
    metadata = _queue_metadata(item)
    task_status = str(metadata.get("audit_task_status") or "").strip().lower()

    if task_status not in ("processing", "stale", "failed"):
        raise HTTPException(
            status_code=400,
            detail="Auditoria não está em andamento ou falha para ser cancelada."
        )

    classification_review.atualizar_status_fila_revisao_classificacao(
        database.get_connection,
        input_hash,
        status=REVIEW_QUEUE_STATUS_PENDING,
        metadata_merge={
            "audit_task_status": "canceled",
            "audit_task_started_at": None,
            "audit_task_error": "Cancelada manualmente pelo usuário.",
        },
    )

    task_cancel_requested = False
    task = _ACTIVE_AUDIT_TASKS.get(input_hash)
    if task is not None and not task.done():
        task.cancel()
        task_cancel_requested = True

    return {
        "success": True,
        "message": "Auditoria cancelada e restaurada para pendente.",
        "task_cancel_requested": task_cancel_requested,
    }


@router.get("/debug/obs")
async def debug_obs_root(user: dict = Depends(require_admin)):
    """Lista as primeiras 30 pastas/chaves na raiz do OBS para descobrirmos o formato."""
    from core.huawei_obs_client import HuaweiOBSClient
    import db.database as database
    
    ak = str(configuration.get_config_value(database.get_connection, "huawei_obs_ak", "") or "").strip()
    sk = str(configuration.get_config_value(database.get_connection, "huawei_obs_sk", "") or "").strip()
    bucket = str(configuration.get_config_value(database.get_connection, "huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(configuration.get_config_value(database.get_connection, "huawei_obs_endpoint", "") or "").strip()
    
    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}
        
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    try:
        keys = await client._list_keys(prefix="")
        return {
            "bucket": bucket,
            "root_keys": keys[:30] if keys else [],
            "message": "Sucesso" if keys else "Bucket parece estar vazio na raiz!"
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/obs/search")
async def debug_obs_search(user: dict = Depends(require_admin)):
    """Procura pastas uteis no OBS."""
    from core.huawei_obs_client import HuaweiOBSClient
    import db.database as database
    from datetime import datetime, timezone
    
    ak = str(configuration.get_config_value(database.get_connection, "huawei_obs_ak", "") or "").strip()
    sk = str(configuration.get_config_value(database.get_connection, "huawei_obs_sk", "") or "").strip()
    bucket = str(configuration.get_config_value(database.get_connection, "huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(configuration.get_config_value(database.get_connection, "huawei_obs_endpoint", "") or "").strip()
    
    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}
        
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    
    agora = datetime.now(timezone.utc)
    date_str = agora.strftime("%Y%m%d")
    
    prefixes_to_test = [
        f"Voice/{date_str}/",
        f"voice/{date_str}/",
        f"Recordings/{date_str}/",
        f"recordings/{date_str}/",
        f"Contact_Record/",
        "Voice/",
        "Recordings/"
    ]
    
    results = {}
    
    for prefix in prefixes_to_test:
        try:
            keys = await client._list_keys(prefix=prefix)
            results[prefix] = keys[:10] if keys else []
        except Exception as e:
            results[prefix] = f"Error: {e}"

    return {
        "bucket": bucket,
        "search_results": results
    }

@router.post("/sync/d-minus-1")
async def sync_d_minus_1(
    request: Request,
    body: Optional[dict] = Body(default=None),
):
    """Dispara o pipeline D-1 (lote diário do OBS) via Cloud Scheduler.

    - Sem `date` no body: roda o pipeline orquestrado (respeita horário,
      lookback e retry configurados no banco).
    - Com `date`: força execução direta de uma data específica (uso legado).
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
    """Gatilho dedicado do Cloud Scheduler para o Coletor D-1/OBS."""
    from routers.automation import _require_cron_token

    _require_cron_token(request)
    if not _is_telefonia_cron_sync_enabled():
        return {
            "status": "disabled",
            "message": "Cron de coleta de Telefonia desligado.",
        }
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
    proxima = _calcular_proxima_execucao_d1_sp(
        now_sp=now_sp,
        horario_raw=horario_raw,
        enabled=cfg["huawei_d1_enabled"].lower() == "true",
        ultima_execucao=ultima_execucao,
        last_attempt_sp=last_attempt_sp,
        max_retries=max(1, _safe_int(cfg["huawei_d1_max_retries"], int(PIPELINE_CONFIG_DEFAULTS["huawei_d1_max_retries"]))),
        retry_intervalo_minutos=max(1, _safe_int(cfg["huawei_d1_retry_intervalo_minutos"], 60)),
    )
    proxima_iso = proxima.isoformat() if proxima else None

    try:
        raw_cron = configuration.get_config_value(database.get_connection, "telefonia_cron_sync_ativa", "true")
        cron_ativa = str(raw_cron or "").strip().lower() == "true"
    except Exception:
        cron_ativa = True

    try:
        raw_intervalo = configuration.get_config_value(database.get_connection, "automacao_intervalo_segundos", "600")
        intervalo_segundos = max(60, int(str(raw_intervalo or "600")))
    except Exception:
        intervalo_segundos = 600
    try:
        raw_audit_target = configuration.get_config_value(
            database.get_connection,
            "automacao_audit_target_count",
            "",
        )
        if raw_audit_target in (None, ""):
            raw_audit_target = configuration.get_config_value(
                database.get_connection,
                "automacao_audit_batch_size",
                "10",
            )
        limite_auditorias = max(1, _safe_int(raw_audit_target, 10))
    except Exception:
        limite_auditorias = 10
    limite_ligacoes = max(1, _safe_int(cfg["huawei_d1_limite_ligacoes"], 20), limite_auditorias)

    return {
        "config": {
            "enabled": cfg["huawei_d1_enabled"].lower() == "true",
            "horario_execucao": cfg["huawei_d1_horario_execucao"],
            "max_retries": max(1, _safe_int(cfg["huawei_d1_max_retries"], int(PIPELINE_CONFIG_DEFAULTS["huawei_d1_max_retries"]))),
            "retry_intervalo_minutos": max(1, _safe_int(cfg["huawei_d1_retry_intervalo_minutos"], 60)),
            "lookback_dias": max(1, _safe_int(cfg["huawei_d1_lookback_dias"], 1)),
            "cota_max_por_operador_mes": max(1, _safe_int(cfg["huawei_cota_max_por_operador_mes"], 2)),
            "limite_ligacoes": limite_ligacoes,
            "limite_auditorias": limite_auditorias,
            "telefonia_cron_sync_ativa": cron_ativa,
            "automacao_intervalo_segundos": intervalo_segundos,
        },
        "config_defaults": PIPELINE_CONFIG_DEFAULTS,
        "now_sp": now_sp.isoformat(),
        "proxima_execucao_sp": proxima_iso,
        "ultima_execucao": ultima_execucao,
    }




@router.get("/sync/diagnostics")
async def sync_diagnostics(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Devolve uma visao operacional rapida para diagnosticar 'parou de baixar'.

    Inclui:
      - se o sync esta travado em memoria
      - estado atual do sync_lock no banco (e quem o segura)
      - flag telefonia_cron_sync_ativa (gate do cron de Telefonia)
      - presenca do CRON_SECRET_TOKEN
      - flag ENABLE_HUAWEI_SYNC (gate do executar_sync_huawei)
    """
    info: Dict[str, Any] = {
        "in_memory_sync_running": _is_sync_running(),
        "last_sync_status": _LAST_SYNC.get("status"),
        "last_sync_started_at": _LAST_SYNC.get("started_at"),
        "last_sync_finished_at": _LAST_SYNC.get("finished_at"),
        "cron_secret_token_set": bool((os.getenv("CRON_SECRET_TOKEN") or "").strip()),
        "enable_huawei_sync_env": (os.getenv("ENABLE_HUAWEI_SYNC", "") or "").strip().lower() == "true",
    }
    try:
        info[TELEFONIA_CRON_SYNC_CONFIG_KEY] = _is_telefonia_cron_sync_enabled()
    except Exception:  # noqa: BLE001
        info[TELEFONIA_CRON_SYNC_CONFIG_KEY] = None
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
    try:
        info["intervalo_segundos"] = _get_telefonia_sync_interval_seconds()
    except Exception:  # noqa: BLE001
        info["intervalo_segundos"] = None
    return info


@router.post("/sync/reset-lock")
async def sync_reset_lock(_user: dict = Depends(require_admin)) -> Dict[str, Any]:
    """Forca a liberacao do sync_lock no banco quando ele ficou travado por
    deploy/crash no meio de uma sincronizacao. Existe a expiracao automatica
    de 30 min mas em emergencia o admin pode destravar manualmente."""
    if _is_sync_running():
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


@router.post("/automacao/toggle")
async def automacao_toggle(
    request: Request,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Compat legado: liga/desliga apenas o cron do modulo Telefonia.

    Body: {"enabled": true|false}. Sem body, retorna o estado atual.
    """
    estado_atual = _is_telefonia_cron_sync_enabled()
    try:
        body = await request.json()
    except Exception:
        body = None
    if not isinstance(body, dict) or "enabled" not in body:
        return {"status": "ok", TELEFONIA_CRON_SYNC_CONFIG_KEY: estado_atual}
    novo = bool(body.get("enabled"))
    try:
        configuration.update_config(
            database.get_connection,
            TELEFONIA_CRON_SYNC_CONFIG_KEY,
            "true" if novo else "false",
            alterado_por=_user.get("username", "admin"),
            motivo="toggle cron sync telefonia",
            origem="ui",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao atualizar config: {exc}")
    logger.info("%s alterada para %s pelo admin.", TELEFONIA_CRON_SYNC_CONFIG_KEY, novo)
    return {"status": "ok", TELEFONIA_CRON_SYNC_CONFIG_KEY: novo}


@router.post("/sync/cron-toggle")
async def telefonia_cron_toggle(
    request: Request,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Liga/desliga o cron de coleta do modulo Telefonia."""
    return await automacao_toggle(request, _user)

