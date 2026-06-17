from __future__ import annotations
"""Router do módulo Telefonia — integração com a Huawei AICC (sync, fila e ações).

Papel no fluxo: porta de entrada HTTP do pipeline de Telefonia. O sync (manual
ou D-1 via cron) baixa as ligações da Huawei → itens entram na fila
`fila_revisao_classificacao` com origem=huawei_sync → triagem/classificação →
auditoria (instantânea por aqui, ou em lote via core/automation.py) → resultado
em "Arquivos Salvos" com status `awaiting_pair` → revisão humana.

Grupos de endpoints (prefixo /api/telefonia):
  - Sync manual:        POST /sync/manual|cancel|pause|resume|clear,
                        GET /sync/status|history
  - Cron (Scheduler):   POST /cron/sync e POST /sync/d-minus-1 — autenticados
                        por Bearer CRON_SECRET_TOKEN (sem sessão de usuário);
                        todos os demais endpoints exigem admin (require_admin)
  - Pipeline D-1:       POST /sync/d-minus-1/manual,
                        GET /sync/d-minus-1/status|summary
  - Fila de gravações:  GET/DELETE /recordings, DELETE /recordings/{hash},
                        GET /recordings/{hash}/audio
  - Ações por gravação: POST /recordings/{hash}/triage|classify|audit,
                        GET /recordings/{hash}/audit-status,
                        DELETE /recordings/{hash}/audit
  - Operação:           GET /sync/diagnostics (inclui custo_diario do
                        cost_guard), POST /sync/reset-lock
  - Debug OBS:          GET /debug/obs, GET /debug/obs/search

CUSTO DE API: POST /recordings/{hash}/classify e POST /recordings/{hash}/audit
disparam chamadas PAGAS ao Azure (Speech para transcrição + OpenAI GPT-4o para
classificação/avaliação). Os syncs (manual/cron/D-1) geram custo indireto ao
enfileirar itens que o pipeline classifica em seguida. Teto diário e
kill-switch em core/cost_guard.py.

Credenciais Huawei: cofre com precedência env > tabela `configuracoes`
(ver _credentials_status).

O router antigo em `routers/automation.py` mantém shims para não quebrar o
frontend legado até a migração completa.
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

# ── Constantes do módulo ─────────────────────────────────────────────────────
# Status de run D-1 que ainda admitem retry automático no mesmo dia
# (consultados por _calcular_proxima_execucao_d1_sp).
D1_RETRY_PENDING_STATUSES = {
    "empty",
    "error",
    "partial",
    "obs_voice_empty_will_retry",
    "obs_manifest_empty_will_retry",
}
# Motivo gravado em motivos_revisao quando o admin envia a gravação à triagem.
TELEFONIA_TRIAGE_REASON = "enviado_para_triagem_telefonia"


# ── Estado em memória do módulo (perde-se em restart do pod) ─────────────────

# Tasks de auditoria em background por input_hash — permitem o cancelamento
# imediato via DELETE /recordings/{hash}/audit.
_ACTIVE_AUDIT_TASKS: Dict[str, asyncio.Task] = {}

def _safe_int(value: Any, default: int) -> int:
    """Converte valor arbitrário para int, com default em entrada inválida."""
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
    """Timestamp atual em UTC no formato ISO-8601 (padrão de persistência do módulo)."""
    return datetime.now(timezone.utc).isoformat()


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
    """Calcula o próximo disparo do pipeline D-1 em horário de São Paulo.

    Considera o horário diário configurado e, quando a última run terminou em
    status que admite retry (D1_RETRY_PENDING_STATUSES), o intervalo de retry.
    Retorna None se o horário configurado for inválido.
    """
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
    """True se há sync em andamento: task local viva OU lock `sync_lock` (TTL 30min) no banco (cobre múltiplas instâncias)."""
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
    """Extrai o dict `metadata` de um item da fila, tolerando None/tipo errado."""
    metadata = (item or {}).get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _resolve_audit_created_by_for_queue_item(item: dict, user: dict) -> str:
    """Define o `criado_por` da auditoria: 'automacao' p/ itens automáticos, senão o usuário logado."""
    metadata = _queue_metadata(item)
    if metadata.get("is_manual") is False:
        return "automacao"

    user_info = user or {}
    return user_info.get("username") or user_info.get("sub") or "telefonia_manual"


def _is_audit_task_cancel_requested(input_hash: str) -> bool:
    """Consulta no banco se o usuário pediu cancelamento da auditoria em background (metadata.audit_task_status='canceled')."""
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
    """Checkpoint de cancelamento: lança CancelledError se o cancelamento foi pedido."""
    if _is_audit_task_cancel_requested(input_hash):
        raise asyncio.CancelledError(f"Auditoria cancelada para input_hash={input_hash}")


def _cleanup_audit_task(input_hash: str, task: asyncio.Task) -> None:
    """Callback de término da task de auditoria: tira do registro e loga cancelamento/erro."""
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
    """Dispara a auditoria em background e registra a task para permitir cancelamento."""
    task = asyncio.create_task(
        _process_audit_background_task(input_hash=input_hash, **kwargs),
        name=f"telefonia_audit_{input_hash[:12]}",
    )
    _ACTIVE_AUDIT_TASKS[input_hash] = task
    task.add_done_callback(lambda finished_task: _cleanup_audit_task(input_hash, finished_task))
    return task


def _metadata_flag(metadata: dict, key: str) -> bool:
    """Lê flag booleana do metadata aceitando bool ou strings ('1', 'true', 'sim'...)."""
    value = (metadata or {}).get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim"}


def _recording_sent_to_triage(item: dict) -> bool:
    """True se a gravação já foi enviada à triagem (carimbo no metadata ou motivo registrado)."""
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
    """True se o item nasceu do sync Huawei (metadata.origem == 'huawei_sync')."""
    return str(_queue_metadata(item).get("origem") or "").lower() == "huawei_sync"


def _recording_media_path(item: dict) -> str:
    """Path da mídia classificada no storage (áudio ou documento)."""
    metadata = _queue_metadata(item)
    return str(metadata.get("classified_audio_path") or metadata.get("classified_file_path") or "").strip()


def _recording_source_type(item: dict) -> str:
    """Tipo da mídia de origem ('audio', 'pdf'...) registrado no metadata."""
    metadata = _queue_metadata(item)
    return str(metadata.get("source_type") or "").strip().lower()


def _recording_is_audio(item: dict) -> bool:
    """True se a gravação é áudio (PDFs de chat seguem fluxo documental — v1.3.105)."""
    source_type = _recording_source_type(item)
    filename = str((item or {}).get("nome_arquivo") or "").lower()
    if source_type == SOURCE_TYPE_PDF or filename.endswith(".pdf"):
        return False
    return True


def _resolve_registered_huawei_operator(metadata: dict, item: dict) -> Optional[dict]:
    """Resolve o colaborador cadastrado tentando todos os IDs Huawei presentes no item.

    Retorna o cadastro normalizado (nome, setor, escala...) do primeiro ID que
    casar em `colaboradores`, ou None se nenhum estiver cadastrado.
    """
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
    """True se é gravação de ÁUDIO vinda do sync Huawei (exclui PDFs)."""
    return _is_huawei_queue_item(item) and _recording_is_audio(item)


def _huawei_recording_direction_block(item: dict) -> Optional[tuple[str, str]]:
    """Aplica o guardrail de direção/setor: retorna (motivo, setor) se bloqueada.

    Regras: setor fora do módulo Telefonia bloqueia; setores de risco
    outbound-only bloqueiam ligações receptivas ou de direção desconhecida.
    None = liberada.
    """
    if not _is_huawei_queue_item(item):
        return None

    metadata = _queue_metadata(item)
    # Usa primeiro o setor real do operador no metadata. O setor previsto pela
    # classificacao pode estar errado e nao deve liberar receptiva de risco.
    sector = normalize_huawei_sector(
        metadata.get("operator_sector_id")
        or metadata.get("operator_sector_real")
        or (item or {}).get("setor_previsto")
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
    """Converte o bloqueio de direção/setor em HTTP 409 com mensagem explicativa."""
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
    """Filtro da lista de gravações da UI: só áudio Huawei ativo e acionável (não arquivado/auditado/bloqueado/em triagem)."""
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
    """Converte begin_time Huawei (epoch ms) em ISO UTC; None se ausente/inválido."""
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
    """Projeta um item da fila no formato que a UI de gravações consome.

    Calcula campos derivados: disponibilidade de áudio, bloqueio de direção,
    `can_send_to_audit`, timestamps normalizados e flags de revisão.
    """
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
    """Busca item Huawei da fila pelo hash ou lança 404 (400 se hash vazio)."""
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
    """Busca item da fila (qualquer origem) pelo hash ou lança 404."""
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
    """Espelha a auditoria recém-criada em Arquivos Salvos (não propaga falha — só loga)."""
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
    """Resolve o cofre de credenciais Huawei e diz o que falta para o sync.

    Cada credencial é buscada primeiro nas envs e depois na tabela
    `configuracoes` (env tem precedência). O conjunto exigido depende do
    `auth_mode`: modos OAuth diretos pedem app key/secret; o modo proxy pede
    AK/SK. Retorna {configured, missing, auth_mode, fields} para a UI do
    cofre — nunca expõe os valores, só `has_value`/`from_env`.
    """
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
        """Primeiro valor não-vazio entre os aliases de env da credencial."""
        for env_key in keys:
            value = str(os.getenv(env_key) or "").strip()
            if value:
                return value
        return ""

    def first_config_value(keys: tuple[str, ...]) -> str:
        """Primeiro valor não-vazio entre as chaves do cofre (tabela `configuracoes`)."""
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
    """Converte datetime ISO (do datetime-local do navegador) em epoch ms; assume UTC-3 quando sem timezone."""
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


async def _run_manual_sync(
    horas: float,
    cancel_event: threading.Event | None = None,
    begin_time_ms: Optional[int] = None,
    end_time_ms: Optional[int] = None,
    pause_event: threading.Event | None = None,
) -> None:
    """Corpo da task de sync manual: executa `executar_sync_huawei` e persiste o desfecho.

    Atualiza o snapshot `_LAST_SYNC` (status/progresso para a UI), respeita
    cancelamento/pausa via events e grava o histórico da run no banco.
    Custo indireto: itens enfileirados serão classificados pelo pipeline (GPT).
    """
    global _LAST_SYNC_CANCEL_EVENT, _LAST_SYNC_PAUSE_EVENT, _LAST_SYNC_RUN_ID
    run_id = _LAST_SYNC_RUN_ID

    def _finalize(*, status: str, baixadas: int, enfileiradas: int, erros: int, mensagem: Optional[str]) -> None:
        """Fecha a run no banco (UPDATE por run_id; fallback INSERT histórico)."""
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
            """Publica progresso para a UI e emite heartbeat da run no banco."""
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


# Concorrencia global das classificacoes manuais (protege o Azure mesmo com varios
# admins triando ao mesmo tempo). Cap via TELEFONIA_CLASSIFY_MAX_CONCURRENCY (default 3).
# Lazy e por event-loop: um Semaphore de modulo se prende ao loop no 1o uso, e os
# testes rodam asyncio.run varias vezes com loops diferentes.
_classify_semaphore_state: Optional[tuple[Any, asyncio.Semaphore]] = None


def _classify_max_concurrency() -> int:
    """Limite de classificações simultâneas (env TELEFONIA_CLASSIFY_MAX_CONCURRENCY, default 3)."""
    raw = os.getenv("TELEFONIA_CLASSIFY_MAX_CONCURRENCY", "3")
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 3


def _get_classify_semaphore() -> asyncio.Semaphore:
    """Semáforo de classificação preso ao event loop atual (recriado se o loop mudar)."""
    global _classify_semaphore_state
    loop = asyncio.get_running_loop()
    if _classify_semaphore_state is None or _classify_semaphore_state[0] is not loop:
        _classify_semaphore_state = (loop, asyncio.Semaphore(_classify_max_concurrency()))
    return _classify_semaphore_state[1]


AUDIT_TASK_INFLIGHT_TIMEOUT = timedelta(minutes=10)


def _parse_iso_to_aware(value: Any) -> Optional[datetime]:
    """Converte ISO em datetime timezone-aware (assume UTC quando sem timezone)."""
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
    """Cota mensal de auditorias por operador; falha de config vira 503 (default 2 só em teste isolado)."""
    try:
        return _get_monthly_audit_quota()
    except Exception as exc:
        if os.getenv("PYTEST_CURRENT_TEST"):
            logger.info("Telefonia: usando cota mensal padrao em teste isolado: %s", exc)
            return 2
        logger.exception("Falha ao carregar cota mensal configurada para Telefonia")
        raise HTTPException(status_code=503, detail="Falha ao validar configuracao de cota mensal.")


def _extract_audit_context(item: dict) -> Dict[str, Any]:
    """Monta o contexto de auditoria (alerta/setor/operador) a partir do item da fila, com auto-reparo."""
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


async def _run_audit_task_and_cleanup(input_hash: str, **kwargs):
    """Roda a auditoria em background aguardando o término (cancelamento é desfecho normal)."""
    task = _start_audit_task(input_hash, **kwargs)
    try:
        await task
    except asyncio.CancelledError:
        pass


# ── Submódulos de rotas ──────────────────────────────────────────────────────
# Importados APÓS todas as definições de helpers/estado/constantes acima:
# cada submódulo faz `from routers import telefonia as tf` e resolve esses
# nomes em RUNTIME (preserva monkeypatch e o estado compartilhado do módulo).
from routers.telefonia_routes import audit_actions as _audit_actions_routes  # noqa: E402
from routers.telefonia_routes import cron_d1 as _cron_d1_routes  # noqa: E402
from routers.telefonia_routes import recordings as _recordings_routes  # noqa: E402
from routers.telefonia_routes import sync as _sync_routes  # noqa: E402

router.include_router(_sync_routes.router)
router.include_router(_cron_d1_routes.router)
router.include_router(_recordings_routes.router)
router.include_router(_audit_actions_routes.router)

# Reexports de compatibilidade: testes e shims legados (ex.: routers/automation.py)
# importam endpoints e modelos diretamente de routers.telefonia.
from routers.telefonia_routes.sync import (  # noqa: E402,F401
    cancel_sync,
    clear_sync_report,
    pause_sync,
    resume_sync,
    sync_diagnostics,
    sync_history,
    sync_manual,
    sync_reset_lock,
    sync_status,
)
from routers.telefonia_routes.cron_d1 import (  # noqa: E402,F401
    cron_sync_d_minus_1,
    get_sync_d_minus_1_status,
    get_sync_d_minus_1_summary,
    sync_d_minus_1,
    sync_d_minus_1_manual,
)
from routers.telefonia_routes.recordings import (  # noqa: E402,F401
    debug_obs_root,
    debug_obs_search,
    listar_gravacoes,
    obter_audio_gravacao,
    remover_gravacao,
    remover_todas_gravacoes,
)
from routers.telefonia_routes.audit_actions import (  # noqa: E402,F401
    AuditRecordingRequest,
    auditar_instantaneamente_gravacao,
    cancelar_auditoria,
    classificar_gravacao_manual,
    consultar_status_auditoria,
    enviar_gravacao_para_triagem,
)
