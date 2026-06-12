"""Automação: auditoria em lote dos itens produzidos pela triagem/classificação.

Papel no fluxo: sync Huawei D-1 → triagem → classificação GPT → **este módulo**
(audita itens `auto_resolved`/`ready_for_audit` da fila `fila_revisao_classificacao`)
→ resultado vai para "Arquivos Salvos" com status `awaiting_pair` → revisão
humana → aprovação → fechamento.

Esteira binária (v1.3.103): todo item READY termina em `audited` OU descartado
(tombstone permanente p/ lixo; recuperável só p/ falha técnica transitória).
Nada fica preso na fila. As flags `AUTOMATION_DISCARD_*` (default ON) controlam
cada gate de descarte e permitem rollback via env.

CUSTO DE API: `_audit_single_item` dispara chamadas PAGAS ao Azure —
transcrição (Azure Speech Fast Transcription, + Whisper/GPT-4o no fallback)
e avaliação (Azure OpenAI GPT-4o). O `cost_guard` impõe teto diário e
interrompe o lote graciosamente quando estourado.

Contrato da fila é público: consumidores devem depender apenas do payload
parseado retornado pelo repositório da fila de revisão.
"""

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Optional, Tuple

import db.database as database
from repositories import operators
from core import cost_guard
from core.classification import get_mime_type
from core.automation_guardrails import AutomationGatekeeper
from core.transcription import compute_input_hash
from core.transcription_quality import (
    get_transcription_audit_readiness,
    get_transcription_review_reasons,
)
from core.automation_disposition import (
    Disposition,
    execute_discard,
    transient_retry_state,
)
from core.runtime_flags import allow_official_criteria_test_fallback
from core.audit_pipeline import (
    AUDIT_ORIGIN_AUTOMATION,
    apply_resolved_operator,
    attach_pipeline_context_to_audio_quality,
    build_queue_audit_context,
    repair_queue_audit_context,
)
from db.domain_constants import (
    AUDIT_STATUS_AWAITING_PAIR,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    SOURCE_TYPE_AUDIO,
    SOURCE_TYPE_PDF,
)
from schemas import AuditAlert, AuditCriterion

logger = logging.getLogger(__name__)
DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT = 3
DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS = 180


class ClassifiedAudioUnavailableError(RuntimeError):
    """Fila referencia um áudio classificado que não pôde ser reaberto do storage.

    Tratada como falha TRANSITÓRIA: o item volta para retry e, esgotado o
    limite, é descartado como recuperável (pode voltar num próximo sync).
    """


class AuditPersistenceError(RuntimeError):
    """A auditoria foi gerada pela IA mas não foi persistida de forma consistente."""


class AlertWithoutOfficialCriteriaError(RuntimeError):
    """Alerta sem critérios no catálogo oficial (módulo IA > Critérios no banco).

    Sem critério oficial não se audita: o item é descartado (flag ON) ou volta
    para triagem manual (flag OFF).
    """


def _automatic_audio_transcription_review_reasons(audio_quality: Any) -> list[str]:
    """Lista de motivos pelos quais a transcrição deste áudio exigiria revisão humana."""
    return list(get_transcription_review_reasons(audio_quality))


def get_classified_audio_storage_root() -> Path:
    """Raiz local do storage de mídia classificada.

    Usa `CLASSIFIED_AUDIO_STORAGE_DIR` se setada; senão `backend/storage/classified_audio`.
    Obs.: em produção a mídia vive na tabela `media_files` (banco); o filesystem
    é fallback/legado.
    """
    configured = os.getenv("CLASSIFIED_AUDIO_STORAGE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "storage" / "classified_audio"


def _normalize_classified_storage_key(relative_path: object) -> Optional[str]:
    """Sanitiza a chave relativa do storage (anti path-traversal).

    Rejeita caminho absoluto, drive Windows (`C:`) e componentes `.`/`..`.
    Retorna a chave POSIX normalizada ou None quando inválida.
    """
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw or raw.startswith("/"):
        return None
    path = PurePosixPath(raw)
    if path.parts and ":" in path.parts[0]:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path.as_posix()


def _resolve_classified_local_path(relative_path: object) -> Optional[Path]:
    """Resolve a chave relativa para um Path absoluto DENTRO da raiz do storage.

    Retorna None (com warning) se a chave for inválida ou escapar da raiz.
    """
    storage_key = _normalize_classified_storage_key(relative_path)
    if not storage_key:
        logger.warning("Caminho de midia classificada invalido: %r", relative_path)
        return None

    root = get_classified_audio_storage_root().resolve()
    resolved = (root / storage_key).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        logger.warning("Caminho de midia classificada fora do storage: %r", relative_path)
        return None
    return resolved


def store_classified_audio(input_hash: str, filename: str, audio_bytes: bytes) -> str:
    """Guarda a mídia classificada para ser auditada depois pela automação.

    Efeito colateral: grava em `media_files` (banco) sob a chave namespaced
    `classified:{input_hash}`. Retorna a storage_key relativa
    (`classified_audio/AAAA/MM/{hash16}{ext}`) que vai para o metadata da fila.
    """
    ext = Path(filename).suffix.lower() or ".wav"
    safe_hash = input_hash[:16] if input_hash else "unknown"
    relative = f"{safe_hash}{ext}"

    now = datetime.now()
    date_path = f"{now:%Y}/{now:%m}"
    storage_key = f"classified_audio/{date_path}/{relative}"

    from core.media_storage import classified_media_hash, store_media
    content_type = get_mime_type(filename) or "audio/wav"

    store_media(
        file_hash=classified_media_hash(input_hash) or input_hash,
        content_bytes=audio_bytes,
        original_filename=filename,
        content_type=content_type,
        storage_key=storage_key
    )
    return storage_key


def load_classified_audio(relative_path: str, input_hash: Optional[str] = None) -> Optional[bytes]:
    """Carrega os bytes da mídia classificada do storage.

    Tenta primeiro a chave namespaced `classified:{input_hash}`; cai para o
    `input_hash` cru (legado) e por fim para o `relative_path`, para que linhas
    gravadas antes do namespacing continuem funcionando. Retorna None se não achar.
    """
    from core.media_storage import classified_media_hash, load_media_bytes
    ns_key = classified_media_hash(input_hash)
    if ns_key:
        bytes_data = load_media_bytes(file_hash=ns_key, fallback_path=None)
        if bytes_data is not None:
            return bytes_data
    return load_media_bytes(file_hash=input_hash or relative_path, fallback_path=relative_path)


_AUDIO_STREAM_CHUNK_SIZE = 64 * 1024  # 64 KB por chunk


def open_classified_audio_stream(
    relative_path: str,
    input_hash: Optional[str] = None
) -> Optional[Tuple[Iterator[bytes], Optional[int]]]:
    """Abre o audio classificado em modo streaming.

    Devolve (iterator_de_chunks, content_length) ou None quando o arquivo nao
    existe. Usado pelo router /telefonia/recordings/{hash}/audio para evitar
    carregar WAVs inteiros em memoria ao servir o player.
    """
    from core.media_storage import classified_media_hash, open_media_stream
    ns_key = classified_media_hash(input_hash)
    if ns_key:
        stream = open_media_stream(file_hash=ns_key, fallback_path=None)
        if stream is not None:
            return stream
    return open_media_stream(file_hash=input_hash or relative_path, fallback_path=relative_path)



def cleanup_classified_audio_storage(*, retention_days: int = 30, dry_run: bool = True) -> dict:
    """Remove do filesystem áudios classificados órfãos (sem referência na fila).

    Arquivos ainda referenciados por `fila_revisao_classificacao.metadata.classified_audio_path`
    são SEMPRE preservados. Os não referenciados só são apagados quando mais
    antigos que `retention_days`. Com `dry_run=True` (default) apenas lista os
    candidatos sem apagar. Retorna dict-relatório (referenced/kept/candidates/deleted).
    """
    root = get_classified_audio_storage_root()
    if retention_days < 0:
        raise ValueError("retention_days deve ser maior ou igual a zero")

    if not root.exists():
        return {
            "root": str(root),
            "referenced": 0,
            "kept": 0,
            "candidates": [],
            "deleted": [],
            "dry_run": dry_run,
        }

    referenced_paths = {
        str(Path(relative_path).as_posix())
        for relative_path in database.listar_paths_audio_classificado_fila_revisao()
        if str(relative_path or "").strip()
    }
    cutoff = datetime.now() - timedelta(days=retention_days)
    candidates: list[str] = []
    deleted: list[str] = []
    kept = 0

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = str(path.relative_to(root).as_posix())
        if relative in referenced_paths:
            kept += 1
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime)
        if modified_at > cutoff:
            kept += 1
            continue
        candidates.append(relative)
        if not dry_run:
            path.unlink(missing_ok=True)
            deleted.append(relative)

    return {
        "root": str(root),
        "referenced": len(referenced_paths),
        "kept": kept,
        "candidates": candidates,
        "deleted": deleted,
        "dry_run": dry_run,
        "retention_days": retention_days,
    }


@dataclass
class AutomationProgress:
    """Estado em memória de uma execução de `audit_all_pending` (singleton do processo).

    Exposto via `get_automation_status()` para o painel da UI (polling).
    Acessos sempre sob `_progress_lock`. `completed`/`discarded`/`failed`/`blocked`
    são contadores acumulados do lote; `current_step` + `last_heartbeat_at`
    servem de heartbeat para detectar automação travada ("zumbi").
    """

    total: int = 0
    target_count: int = 0
    requested_audits: int = 0
    batch_size: int = 0
    operational_batch_size: int = 0
    completed: int = 0
    discarded: int = 0
    failed: int = 0
    blocked: int = 0
    current_filename: str = ""
    current_filenames: list = field(default_factory=list)  # itens em voo (async)
    is_running: bool = False
    is_cancelled: bool = False
    is_paused: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_step: str = ""
    current_item_started_at: Optional[str] = None
    last_step_at: Optional[str] = None
    last_heartbeat_at: Optional[str] = None
    time_budget_seconds: int = 0
    item_timeout_seconds: int = 0
    errors: deque = field(default_factory=lambda: deque(maxlen=100))

    def to_dict(self) -> dict:
        """Serializa o progresso para o JSON consumido pelo front (inclui alias
        legado `descartados` e só os 10 últimos erros)."""
        return {
            "total": self.total,
            "target_count": self.target_count,
            "requested_audits": self.requested_audits,
            "batch_size": self.batch_size,
            "operational_batch_size": self.operational_batch_size,
            "completed": self.completed,
            "discarded": self.discarded,
            "descartados": self.discarded,
            "failed": self.failed,
            "blocked": self.blocked,
            "current_filename": self.current_filename,
            "current_filenames": list(self.current_filenames),
            "is_running": self.is_running,
            "is_cancelled": self.is_cancelled,
            "is_paused": self.is_paused,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "current_step": self.current_step,
            "current_item_started_at": self.current_item_started_at,
            "last_step_at": self.last_step_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "time_budget_seconds": self.time_budget_seconds,
            "item_timeout_seconds": self.item_timeout_seconds,
            "errors": list(self.errors)[-10:],
        }


_progress = AutomationProgress()
_progress_lock = threading.Lock()


def get_automation_status() -> dict:
    """Snapshot thread-safe do progresso da automação (consumido pela UI via polling)."""
    with _progress_lock:
        return _progress.to_dict()


def _set_progress_step(step: str, *, filename: Optional[str] = None) -> None:
    """Registra um heartbeat leve da etapa atual do item (p/ UI e diagnóstico de travamento)."""
    now = datetime.now(timezone.utc).isoformat()
    with _progress_lock:
        if filename is not None:
            _progress.current_filename = filename
        _progress.current_step = step
        _progress.last_step_at = now
        _progress.last_heartbeat_at = now
    logger.info(
        "Automacao: etapa do item atual filename=%r step=%s",
        filename or get_automation_status().get("current_filename") or "?",
        step,
    )


def _get_automation_item_timeout_seconds() -> int:
    """Timeout por item (segundos), clampado em [60, 900].

    Precedência: env `AUTOMATION_ITEM_TIMEOUT_SECONDS` > config no banco
    `automacao_item_timeout_seconds` > 480.
    """
    raw = os.getenv("AUTOMATION_ITEM_TIMEOUT_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value("automacao_item_timeout_seconds", "480")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 480
    return max(60, min(parsed, 900))


def _coerce_positive_int(value: object, default: int) -> int:
    """Converte para int >= 1; valor inválido vira `default`."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _read_config_value_with_fallback(keys: tuple[str, ...], default: str) -> str:
    """Lê a primeira config não vazia do banco entre `keys` (suporta chaves renomeadas/legadas)."""
    for key in keys:
        try:
            raw = database.get_config_value(key, "")
        except Exception as exc:
            logger.debug("Automacao: falha ao ler config %s: %s", key, exc)
            continue
        if raw not in (None, ""):
            return str(raw)
    return default


def _get_automation_audit_target_count() -> int:
    """Meta de auditorias por execução (quantos itens o lote tenta processar).

    Precedência: env `AUTOMATION_AUDIT_TARGET_COUNT` > env legada
    `AUTOMATION_AUDIT_BATCH_SIZE` > configs no banco > default 3.
    """
    raw = os.getenv("AUTOMATION_AUDIT_TARGET_COUNT")
    if raw in (None, ""):
        raw = os.getenv("AUTOMATION_AUDIT_BATCH_SIZE")
    if raw in (None, ""):
        raw = _read_config_value_with_fallback(
            ("automacao_audit_target_count", "automacao_audit_batch_size"),
            str(DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT),
        )
    return _coerce_positive_int(raw, DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT)


def _get_automation_audit_batch_size() -> int:
    """Nome retrocompatível para a meta de auditorias configurada.

    A UI hoje grava uma META de auditorias; o runtime deriva lotes operacionais
    menores a partir do orçamento de tempo (`_derive_automation_audit_batch_size`)
    em vez de tratar este valor como tamanho de página da fila.
    """
    return _get_automation_audit_target_count()


def _get_automation_expected_audit_item_seconds() -> int:
    """Duração ESPERADA de um item (s, clamp [30, 900]) — usada só p/ dimensionar o lote."""
    raw = os.getenv("AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value(
            "automacao_expected_audit_item_seconds",
            str(DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS),
        )
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS
    return max(30, min(parsed, 900))


def _derive_automation_audit_batch_size(
    *,
    target_count: int,
    time_budget_seconds: int,
    item_timeout_seconds: int,
) -> int:
    """Tamanho do lote operacional: min(meta, quantos itens cabem no orçamento de tempo).

    Garante que um cron com orçamento curto não pegue mais itens do que
    consegue terminar (evita item iniciado e abortado no meio).
    """
    expected_item_seconds = min(
        _get_automation_expected_audit_item_seconds(),
        max(1, item_timeout_seconds),
    )
    budget_bound = max(1, int(time_budget_seconds) // expected_item_seconds)
    return max(1, min(int(target_count), budget_bound))


def _get_automation_audit_time_budget_seconds() -> int:
    """Orçamento de tempo TOTAL do lote (s, clamp [60, 1800]; default 480).

    Env `AUTOMATION_AUDIT_TIME_BUDGET_SECONDS` > config `automacao_audit_time_budget_seconds`.
    """
    raw = os.getenv("AUTOMATION_AUDIT_TIME_BUDGET_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value("automacao_audit_time_budget_seconds", "480")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 480
    return max(60, min(parsed, 1800))


async def _audit_single_item_with_timeout(item: dict, *, timeout_seconds: Optional[float] = None) -> dict:
    """Envolve `_audit_single_item` em `asyncio.wait_for` e converte estouro em
    `TimeoutError` legível — evita item infinito segurando a automação ("zumbi")."""
    timeout_seconds = timeout_seconds or _get_automation_item_timeout_seconds()
    try:
        return await asyncio.wait_for(_audit_single_item(item), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        filename = item.get("nome_arquivo", "?")
        raise TimeoutError(
            f"Timeout ao auditar '{filename}' apos {timeout_seconds}s. "
            "O item foi abortado para evitar automacao zumbi."
        ) from exc


def _config_flag(key: str) -> bool:
    """Lê uma flag booleana da tabela de config do banco ('true' literal = ligada)."""
    return str(database.get_config_value(key, "false") or "").strip().lower() == "true"


def _discard_unknown_alerts_enabled() -> bool:
    """Flag: item com alerta 'desconhecido' é descartado (tombstone) em vez de ir p/ triagem manual."""
    raw = os.getenv("AUTOMATION_DISCARD_UNKNOWN_ALERTS")
    if raw is None:
        return True  # default ON; rollback via AUTOMATION_DISCARD_UNKNOWN_ALERTS=false
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _audit_on_transcription_risk_enabled() -> bool:
    """Flag: audita mesmo com transcrição de qualidade arriscada (gate humano valida depois)."""
    raw = os.getenv("AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK")
    if raw is None:
        return True  # default ON; rollback via AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK=false
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_default_on(name: str) -> bool:
    """Flag de env var com default ON (rollback setando =false). Padrao das flags da
    esteira de dois estados terminais (auditado | descartado)."""
    raw = os.getenv(name)
    if raw is None:
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _discard_blocked_operator_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_BLOCKED_OPERATOR")


def _audit_ignore_monthly_cap_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP")


def _discard_missing_sector_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_MISSING_SECTOR")


def _discard_no_criteria_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_NO_CRITERIA")


def _discard_non_telephony_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_NON_TELEPHONY")


def _discard_impossible_transcription_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_IMPOSSIBLE_TRANSCRIPTION")


def _transcription_failure_retry_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_TRANSCRIPTION_FAILURE_RETRY")


def _item_metadata(item: dict) -> dict:
    """Metadata normalizado do item da fila (aceita dict, JSON string ou ausente)."""
    raw = item.get("metadata") or item.get("metadata_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw if isinstance(raw, dict) else {}


def _handle_transient_failure(
    item: dict,
    exc: Exception,
    *,
    motivo_retry: str,
    motivo_discard: str,
    status_discard: str,
    step_retry: str,
) -> None:
    """Erro transitorio em audit_all_pending: re-tenta (volta a pending) ate
    AUTOMATION_TRANSIENT_RETRY_LIMIT e, esgotado, DESCARTA (recuperavel) — acaba com a
    "automacao zumbi" sem prender o item. Atualiza o _progress global."""
    input_hash = item.get("input_hash")
    metadata = _item_metadata(item)
    should_retry, next_count = transient_retry_state(metadata)
    if input_hash and should_retry:
        # Retry volta para AUTO_RESOLVED (re-auditavel no proximo ciclo) e NAO para
        # pending: audit_all_pending so re-pega status ready (auto_resolved/reviewed),
        # entao pending ficaria preso sem ser re-auditado nem descartado.
        _mark_item_status(
            input_hash,
            REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
            str(exc),
            motivos_revisao_append=[motivo_retry],
            metadata_merge={
                "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                "automation_transient_retries": next_count,
            },
        )
        with _progress_lock:
            _progress.failed += 1
            _progress.current_step = step_retry
            _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
            _progress.errors.append({"filename": item.get("nome_arquivo", "?"), "error": str(exc)})
        return
    if input_hash:
        try:
            execute_discard(
                item,
                Disposition.DISCARD_RECOVERABLE,
                motivo=motivo_discard,
                status_result=status_discard,
                queue_input_hash=input_hash,
                filename=item.get("nome_arquivo", "?"),
                metadata=metadata,
            )
            with _progress_lock:
                _progress.discarded += 1
                _progress.current_step = "item_discarded"
                _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "Automacao: '%s' descartado apos esgotar retries transitorios (%s).",
                item.get("nome_arquivo", "?"), motivo_discard,
            )
            return
        except Exception:
            logger.exception(
                "Automacao: falha ao descartar transitorio esgotado '%s'",
                item.get("nome_arquivo", "?"),
            )
    with _progress_lock:
        _progress.failed += 1
        _progress.current_step = "item_failed"
        _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
        _progress.errors.append({"filename": item.get("nome_arquivo", "?"), "error": str(exc)})


def _get_monthly_audit_quota() -> int:
    """Cota mensal de auditorias por operador (config `huawei_cota_max_por_operador_mes`, default 2).

    Obs.: com `AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP` ON (default), a cota só é
    aplicada no ENVIO ao supervisor, não na auditoria automática.
    """
    raw = database.get_config_value("huawei_cota_max_por_operador_mes", "2")
    try:
        return max(1, int(str(raw or "2").strip()))
    except (TypeError, ValueError):
        logger.warning("Configuracao huawei_cota_max_por_operador_mes invalida: %r. Usando 2.", raw)
        return 2


def _patch_running_cycle_audit_result(**updates) -> None:
    """Mescla `updates` no JSON `audit_result` do ciclo ATIVO em `automation_cycle_runs`.

    Efeito colateral: UPDATE no banco (melhor esforço — falha vira warning, não
    propaga). Usado para refletir pause/cancel no painel de ciclos.
    """
    payload = {key: value for key, value in updates.items() if value is not None}
    if not payload:
        return

    conn = None
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE automation_cycle_runs
               SET audit_result = COALESCE(audit_result, '{}'::jsonb) || %s::jsonb,
                   last_heartbeat_at = CURRENT_TIMESTAMP
             WHERE id = (
                SELECT id
                  FROM automation_cycle_runs
                 WHERE status = 'running'
                   AND stage = 'auditing'
                 ORDER BY started_at DESC, id DESC
                 LIMIT 1
             )
            """,
            (json.dumps(payload, ensure_ascii=False),),
        )
        conn.commit()
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning("Falha ao sincronizar controle da automacao no ciclo ativo: %s", exc)
    finally:
        if conn is not None:
            conn.close()


def cancel_automation() -> dict:
    """Solicita cancelamento da automação em execução (gracioso: termina o item atual).

    Efeitos colaterais: grava as flags `automacao_is_cancelled=true` /
    `automacao_is_paused=false` na config do banco — assim o sinal alcança o
    worker mesmo em OUTRA instância do cluster — e atualiza o ciclo ativo.
    """
    database.update_config(
        "automacao_is_cancelled", "true",
        alterado_por="system:automation", motivo="cancel_automation()", origem="system",
    )
    database.update_config(
        "automacao_is_paused", "false",
        alterado_por="system:automation", motivo="cancel_automation() unpause", origem="system",
    )
    _patch_running_cycle_audit_result(is_running=True, is_cancelled=True, is_paused=False)
    with _progress_lock:
        if _progress.is_running:
            _progress.is_cancelled = True
            _progress.is_paused = False  # unpause to allow cancel to process
            return {"message": "Cancelamento solicitado. A auditoria atual sera concluida antes de parar."}
        return {"message": "Sinal de cancelamento enviado para o cluster."}


def pause_automation() -> dict:
    """Pausa a automação (o loop espera em `wait_if_paused_or_cancelled` até retomar).

    Efeito colateral: grava `automacao_is_paused=true` na config do banco
    (sinal cross-instância) e atualiza o ciclo ativo.
    """
    database.update_config(
        "automacao_is_paused", "true",
        alterado_por="system:automation", motivo="pause_automation()", origem="system",
    )
    _patch_running_cycle_audit_result(is_running=True, is_cancelled=False, is_paused=True)
    with _progress_lock:
        if _progress.is_running and not _progress.is_cancelled:
            _progress.is_paused = True
            return {"message": "Automação pausada."}
        return {"message": "Sinal de pausa enviado para o cluster."}


def resume_automation() -> dict:
    """Retoma a automação pausada (limpa `automacao_is_paused` na config do banco)."""
    database.update_config(
        "automacao_is_paused", "false",
        alterado_por="system:automation", motivo="resume_automation()", origem="system",
    )
    _patch_running_cycle_audit_result(is_paused=False)
    with _progress_lock:
        if _progress.is_running and _progress.is_paused:
            _progress.is_paused = False
            return {"message": "Automação retomada."}
        return {"message": "Sinal de retomada enviado para o cluster."}


async def audit_all_pending(
    *,
    reset_control_flags: bool = True,
    max_items: Optional[int] = None,
    time_budget_seconds: Optional[int] = None,
) -> dict:
    """Audita itens da fila (status `ready_for_audit`) até a meta, em lotes limitados.

    Loop principal da esteira: pega itens da fila em páginas (`batch_size`
    derivado do orçamento de tempo), processa um a um respeitando pause/cancel
    (flags no banco), timeout por item, orçamento de tempo do lote e o teto
    diário do `cost_guard` (itens restantes FICAM na fila quando estoura).

    CUSTO: cada item auditado dispara transcrição (Azure Speech) + avaliação
    (GPT-4o) — chamadas pagas via `_audit_single_item`.

    Parâmetros: `reset_control_flags` limpa pause/cancel ao iniciar (default);
    `max_items`/`time_budget_seconds` sobrescrevem a config (uso pelo cron).
    Retorno: dict de progresso + flags de término (queue_exhausted,
    time_budget_exhausted, budget_blocked_motivo). Levanta RuntimeError se já
    houver automação rodando neste processo.

    Efeitos colaterais: atualiza status/metadata dos itens na fila, persiste
    auditorias em `audits` (awaiting_pair) e drena a fila de sincronização de
    Arquivos Salvos no finally.
    """
    global _progress

    target_count = max(1, int(max_items)) if max_items is not None else _get_automation_audit_batch_size()
    time_budget = (
        max(60, min(int(time_budget_seconds), 1800))
        if time_budget_seconds is not None
        else _get_automation_audit_time_budget_seconds()
    )
    item_timeout_seconds = min(_get_automation_item_timeout_seconds(), time_budget)
    batch_size = _derive_automation_audit_batch_size(
        target_count=target_count,
        time_budget_seconds=time_budget,
        item_timeout_seconds=item_timeout_seconds,
    )
    started_monotonic = time.monotonic()
    deadline = started_monotonic + time_budget
    time_budget_exhausted = False
    budget_blocked_reason: Optional[str] = None
    queue_exhausted = False
    no_items_found = False
    selected_count = 0
    processed_count = 0
    control_flags_reset = False

    with _progress_lock:
        if _progress.is_running:
            raise RuntimeError("Automacao ja esta em andamento.")
        _progress = AutomationProgress(
            is_running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            last_heartbeat_at=datetime.now(timezone.utc).isoformat(),
            time_budget_seconds=time_budget,
            item_timeout_seconds=item_timeout_seconds,
            target_count=target_count,
            requested_audits=target_count,
            batch_size=batch_size,
            operational_batch_size=batch_size,
        )

    def mark_time_budget_exhausted() -> None:
        nonlocal time_budget_exhausted
        time_budget_exhausted = True
        with _progress_lock:
            _progress.current_step = "time_budget_exhausted"
            _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
        logger.info("Automacao: orçamento de tempo do lote esgotado antes do proximo item.")

    async def wait_if_paused_or_cancelled() -> bool:
        """Bloqueia enquanto pausado (flag no banco); retorna False se cancelado."""
        while True:
            db_paused = _config_flag("automacao_is_paused")
            db_cancelled = _config_flag("automacao_is_cancelled")
            with _progress_lock:
                if db_cancelled:
                    _progress.is_cancelled = True
                if db_paused:
                    _progress.is_paused = True
                elif not db_paused and _progress.is_paused:
                    _progress.is_paused = False

                if _progress.is_cancelled:
                    logger.info("Automacao cancelada pelo usuario.")
                    return False
                is_paused = _progress.is_paused
            if not is_paused:
                return True
            await asyncio.sleep(1)

    async def process_ready_item(item: dict) -> None:
        """Processa UM item: gate de elegibilidade Huawei (setor/direção) →
        auditoria com timeout → contabiliza completed/discarded/blocked/failed.
        Falhas transitórias (áudio ausente, timeout) vão p/ retry-ou-descarte."""
        with _progress_lock:
            _progress.current_filename = item.get("nome_arquivo", "?")
            _progress.current_step = "starting_item"
            _progress.current_item_started_at = datetime.now(timezone.utc).isoformat()
            _progress.last_step_at = _progress.current_item_started_at
            _progress.last_heartbeat_at = _progress.current_item_started_at

        try:
            item_started = time.monotonic()
            direction_block = AutomationGatekeeper.check_eligibility(item)
            if direction_block:
                block_reason, block_sector = direction_block
                input_hash = item.get("input_hash")
                if input_hash and _discard_non_telephony_enabled():
                    # Compliance de telefonia (setor nao-telefonia / direcao incompativel)
                    # nunca vira auditavel -> DESCARTA (tombstone), nao prende em triagem.
                    try:
                        execute_discard(
                            item,
                            Disposition.DISCARD_IMPOSSIBLE,
                            motivo=block_reason,
                            status_result="discarded_non_telephony",
                            queue_input_hash=input_hash,
                            filename=item.get("nome_arquivo", "?"),
                            sector_id=block_sector,
                            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                        )
                        with _progress_lock:
                            _progress.discarded += 1
                            _progress.current_step = "item_discarded"
                            _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                        logger.info(
                            "Automacao: descartando '%s' por politica Huawei (setor=%s, motivo=%s).",
                            item.get("nome_arquivo", "?"), block_sector, block_reason,
                        )
                    except Exception as disc_exc:
                        logger.exception(
                            "Automacao: falha ao descartar '%s' (politica Huawei): %s",
                            item.get("nome_arquivo", "?"), disc_exc,
                        )
                        with _progress_lock:
                            _progress.failed += 1
                            _progress.current_step = "item_failed"
                            _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                    return
                if block_reason == "setor_nao_telefonia":
                    error_message = (
                        "Ligacao Huawei bloqueada: setor nao pertence ao modulo Telefonia."
                    )
                    motivos_append = ["setor_nao_telefonia_automacao"]
                else:
                    error_message = (
                        "Ligacao Huawei de setor de risco bloqueada: "
                        "somente chamadas ativas sao validas para automacao."
                    )
                    motivos_append = ["direcao_invalida_automacao"]
                if input_hash:
                    _mark_item_status(
                        input_hash,
                        REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
                        error_message,
                        motivos_revisao_append=motivos_append,
                        metadata_merge={
                            "automation_direction_blocked_at": datetime.now(timezone.utc).isoformat(),
                            "automation_direction_block_reason": block_reason,
                            "automation_direction_block_sector": block_sector,
                        },
                    )
                    with _progress_lock:
                        _progress.failed += 1
                        _progress.blocked += 1
                        _progress.current_step = "item_skipped_direction"
                        _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                    logger.info(
                        "Automacao: bloqueando '%s' por politica Huawei "
                        "(setor=%s, motivo=%s).",
                        item.get("nome_arquivo", "?"),
                        block_sector,
                        block_reason,
                    )
                else:
                    with _progress_lock:
                        _progress.failed += 1
                        _progress.current_step = "item_failed"
                        _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                        _progress.errors.append(
                            {
                                "filename": item.get("nome_arquivo", "?"),
                                "error": "Item Huawei bloqueado sem input_hash para atualizar a fila.",
                            }
                        )
                return

            res = await _audit_single_item_with_timeout(
                item,
                timeout_seconds=min(item_timeout_seconds, max(1.0, deadline - time.monotonic())),
            )
            result_status = res.get("status") if res else "unknown"
            if result_status == "audited":
                cost_guard.record_audit_completed()
                with _progress_lock:
                    _progress.completed += 1
                    _progress.current_step = "item_completed"
                    _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Automacao: item '%s' concluido em %.1fs",
                    item.get("nome_arquivo", "?"),
                    time.monotonic() - item_started,
                )
            elif str(result_status).startswith("discarded"):
                with _progress_lock:
                    _progress.discarded += 1
                    _progress.current_step = "item_discarded"
                    _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Automacao: item '%s' descartado (status=%s) em %.1fs",
                    item.get("nome_arquivo", "?"),
                    result_status,
                    time.monotonic() - item_started,
                )
            else:
                with _progress_lock:
                    _progress.failed += 1
                    _progress.blocked += 1
                    _progress.current_step = "item_blocked"
                    _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                logger.info(
                    "Automacao: item '%s' ignorado/bloqueado (status=%s) em %.1fs",
                    item.get("nome_arquivo", "?"),
                    result_status,
                    time.monotonic() - item_started,
                )
        except ClassifiedAudioUnavailableError as exc:
            logger.warning(
                "Automacao: arquivo classificado indisponivel para '%s': %s",
                item.get("nome_arquivo", "?"),
                exc,
            )
            _handle_transient_failure(
                item,
                exc,
                motivo_retry="audio_classificado_ausente",
                motivo_discard="audio_classificado_ausente_esgotado",
                status_discard="discarded_audio_unavailable",
                step_retry="item_failed",
            )
        except TimeoutError as exc:
            logger.error(
                "Automacao: timeout ao auditar '%s': %s",
                item.get("nome_arquivo", "?"),
                exc,
            )
            _handle_transient_failure(
                item,
                exc,
                motivo_retry="automation_timeout",
                motivo_discard="automation_timeout_esgotado",
                status_discard="discarded_timeout_exhausted",
                step_retry="item_timeout",
            )
        except Exception as exc:
            logger.exception(
                "Automacao: erro ao auditar '%s': %s",
                item.get("nome_arquivo", "?"),
                exc,
            )
            with _progress_lock:
                _progress.failed += 1
                _progress.current_step = "item_failed"
                _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                _progress.errors.append(
                    {
                        "filename": item.get("nome_arquivo", "?"),
                        "error": str(exc),
                    }
                )

    try:
        while processed_count < target_count:
            remaining_budget = deadline - time.monotonic()
            if remaining_budget <= 1:
                mark_time_budget_exhausted()
                break

            fetch_limit = min(batch_size, target_count - processed_count)
            items = list(
                database.listar_fila_revisao_classificacao(
                    limit=fetch_limit,
                    status=REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
                )
                or []
            )[:fetch_limit]

            if not items:
                queue_exhausted = True
                if selected_count == 0:
                    no_items_found = True
                break

            selected_count += len(items)
            with _progress_lock:
                _progress.total += len(items)

            logger.info(
                "Automacao: iniciando lote operacional com %d item(ns) "
                "(target=%d, batch_size=%d, budget=%ss, item_timeout=%ss)",
                len(items),
                target_count,
                batch_size,
                time_budget,
                item_timeout_seconds,
            )

            if reset_control_flags and not control_flags_reset:
                database.update_config(
                    "automacao_is_paused", "false",
                    alterado_por="system:automation", motivo="audit_all_pending() reset", origem="system",
                )
                database.update_config(
                    "automacao_is_cancelled", "false",
                    alterado_por="system:automation", motivo="audit_all_pending() reset", origem="system",
                )
                control_flags_reset = True

            for item in items:
                if processed_count >= target_count:
                    break
                remaining_budget = deadline - time.monotonic()
                if remaining_budget <= 1:
                    mark_time_budget_exhausted()
                    break
                # Guardrail de orcamento: teto diario de consumo pago atingido
                # -> encerra o lote graciosamente ANTES do proximo item. Os
                # itens restantes continuam ready_for_audit (nada e descartado)
                # e serao processados quando o contador diario resetar.
                budget_blocked_reason = cost_guard.budget_exceeded()
                if budget_blocked_reason:
                    with _progress_lock:
                        _progress.current_step = "budget_exceeded"
                        _progress.last_heartbeat_at = datetime.now(timezone.utc).isoformat()
                    logger.warning(
                        "Automacao: lote encerrado pelo guardrail de orcamento (%s). "
                        "Itens restantes permanecem na fila.",
                        budget_blocked_reason,
                    )
                    break
                if not await wait_if_paused_or_cancelled():
                    break

                await process_ready_item(item)
                processed_count += 1

                await asyncio.sleep(0.5)

            with _progress_lock:
                cancelled = _progress.is_cancelled
            if cancelled or time_budget_exhausted or budget_blocked_reason:
                break
            if len(items) < fetch_limit:
                queue_exhausted = True
                break

    finally:
        try:
            from core.saved_files_sync_queue import flush as flush_sync_queue
            from core.saved_files_sync_queue import queue_size as saved_files_queue_size

            drained = await asyncio.to_thread(flush_sync_queue, timeout=60.0)
            if not drained:
                logger.warning(
                    "Fila de sincronizacao de arquivos nao drenou antes do fim da automacao "
                    "(pending=%s).",
                    saved_files_queue_size(),
                )
        except Exception as exc:
            logger.warning("Falha ao aguardar o termino da fila de sincronizacao de arquivos: %s", exc)

        with _progress_lock:
            _progress.is_running = False
            _progress.current_filename = ""
            _progress.current_step = ""
            _progress.current_item_started_at = None
            _progress.finished_at = datetime.now(timezone.utc).isoformat()
            _progress.last_heartbeat_at = _progress.finished_at

    with _progress_lock:
        result = _progress.to_dict()
        result.update(
            {
                "batch_size": batch_size,
                "operational_batch_size": batch_size,
                "target_count": target_count,
                "requested_audits": target_count,
                "time_budget_seconds": time_budget,
                "item_timeout_seconds": item_timeout_seconds,
                "time_budget_exhausted": time_budget_exhausted,
                "queue_exhausted": queue_exhausted,
                "budget_blocked_motivo": budget_blocked_reason,
            }
        )
        if no_items_found:
            result["message"] = "Nenhum item pendente para auditoria."
        elif budget_blocked_reason:
            result["message"] = (
                f"Lote encerrado pelo guardrail de orcamento: {budget_blocked_reason}."
            )

    logger.info(
        "Automacao concluida: %d/%d auditados, %d descartados, %d bloqueados/erros",
        result["completed"],
        result["total"],
        result["discarded"],
        result["failed"],
    )
    return result


async def _audit_single_item(item: dict) -> dict:
    """Audita um item classificado da fila de revisão (coração da automação).

    Sequência de gates (cada um pode descartar/bloquear ANTES de gastar API):
    1. operador (OperatorGatekeeper: não auditável → descarte permanente);
    2. cota mensal (só com `AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP` OFF — legado);
    3. mídia classificada disponível (ausente → falha transitória/retry);
    4. alerta válido (`desconhecido` → descarte; o catálogo oficial precisa
       ter critérios, senão `AlertWithoutOfficialCriteriaError`);
    5. cache de auditoria por input_hash (hit → reusa SEM custo de API).

    CUSTO: no caminho cheio chama `process_audit_with_ai` (transcrição Azure
    Speech + avaliação GPT-4o, pagas) ou `process_pdf_audit` (GPT-4o) p/ docs.

    Retorno: {"status": "audited", "audit_id": ...} ou {"status": "discarded_*"/
    "blocked_*"}. Efeitos colaterais: persiste a auditoria em `audits` com
    status `awaiting_pair` (criado_por='automacao') e atualiza o item na fila.
    """
    queue_input_hash = item.get("input_hash", "")
    filename = item.get("nome_arquivo", "")

    if not queue_input_hash or not filename:
        raise ValueError(f"Item sem hash ou filename: {item}")

    _set_progress_step("normalizing_metadata", filename=filename)
    metadata = item.get("metadata") or item.get("metadata_json") or {}
    if isinstance(metadata, str):
        import json

        try:
            metadata = json.loads(metadata)
        except Exception as exc:
            logger.debug("metadata malformado para '%s': %s", filename, exc)
            metadata = {}
    elif not isinstance(metadata, dict):
        metadata = {}

    pipeline_context = repair_queue_audit_context(
        build_queue_audit_context({**item, "metadata": metadata}, origin=AUDIT_ORIGIN_AUTOMATION)
    )
    filename = pipeline_context.filename or filename
    sector_id = pipeline_context.sector_id
    alert_id = pipeline_context.alert_id
    operator_name = pipeline_context.operator_name
    operator_id = (
        pipeline_context.operator_id
        or item.get("operator_id")
        or metadata.get("operator_id")
        or item.get("id_huawei")
        or metadata.get("id_huawei")
    )
    _set_progress_step("resolving_operator", filename=filename)
    from core.automation_operator import OperatorGatekeeper, QuotaGatekeeper
    
    operator_result = OperatorGatekeeper.resolve_operator(
        database.get_connection,
        item,
        metadata,
        operator_name,
        operator_id,
        sector_id,
    )
    if not operator_result.is_valid:
        if _discard_blocked_operator_enabled():
            # Operador nao auditavel ja e filtrado no download e nunca vira auditoria valida
            # -> descarta PERMANENTE (tombstone); nao re-processa. So falhas tecnicas
            # transitorias (timeout/transcricao) podem voltar num proximo sync.
            return execute_discard(
                item,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="operador_nao_auditavel",
                status_result="discarded_operator",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=sector_id,
                operator_name=operator_name,
                operator_id=operator_id,
                metadata=metadata,
            )
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
            operator_result.block_message,
            motivos_revisao_append=operator_result.motivos_revisao_append,
            metadata_merge=operator_result.metadata_merge,
        )
        logger.info(
            "Automacao: '%s' bloqueado ou revisao. Motivo: %s",
            filename,
            operator_result.block_message,
        )
        return {"status": operator_result.block_reason}

    operator_name = operator_result.operator_name
    operator_id = operator_result.operator_id
    apply_resolved_operator(
        pipeline_context,
        operator_result.resolved_operator_dict,
        fallback_operator_name=operator_name,
        fallback_operator_id=operator_id,
    )

    if not _audit_ignore_monthly_cap_enabled():
        # Rollback (flag OFF): cota mensal barra a auditoria (comportamento legado).
        # Default ON: a IA audita tudo que presta e deixa em awaiting_pair; a cota 2/mes e
        # compliance apenas no ENVIO ao supervisor (force-send), nunca na auditoria automatica.
        _set_progress_step("checking_operator_quota", filename=filename)
        quota_date = QuotaGatekeeper.resolve_quota_datetime(metadata)
        monthly_audit_quota = _get_monthly_audit_quota()
        quota_block = QuotaGatekeeper.check_quota(
            database.get_connection,
            operator_name,
            operator_id,
            quota_date,
            monthly_audit_quota,
        )
        if quota_block:
            quota_block["metadata_merge"]["audit_pipeline"] = pipeline_context.to_audit_metadata()
            _mark_item_status(
                queue_input_hash,
                REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
                quota_block["block_message"],
                motivos_revisao_append=quota_block["motivos_revisao_append"],
                metadata_merge=quota_block["metadata_merge"],
            )
            logger.info(
                "Automacao: bloqueando '%s' por cota mensal.",
                filename,
            )
            return {"status": quota_block["block_reason"]}

    source_type = pipeline_context.source_type
    media_path = pipeline_context.media_path or metadata.get("classified_audio_path") or metadata.get("classified_file_path")
    _set_progress_step("loading_classified_media", filename=filename)
    media_bytes = load_classified_audio(media_path, input_hash=queue_input_hash) if media_path else None
    if not media_bytes:
        raise ClassifiedAudioUnavailableError(
            f"Arquivo classificado nao encontrado para '{filename}'. "
            "O arquivo precisa ser armazenado durante a classificacao."
        )

    _set_progress_step("validating_context", filename=filename)
    alert_norm = str(alert_id).strip().lower() if alert_id else ""
    if not alert_id or alert_norm == "desconhecido":
        if _discard_unknown_alerts_enabled():
            # Alerta inexistente/desconhecido e lixo de classificacao -> descarta PERMANENTE
            # (tombstone); rebaixar so re-classificaria como desconhecido e descartaria de novo.
            return execute_discard(
                item,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="triagem_sem_alerta_confiavel",
                status_result="discarded_unknown_alert",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=sector_id,
                operator_name=operator_name,
                operator_id=operator_id,
                metadata=metadata,
            )
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
            "Alerta desconhecido (triagem sem alerta confiavel)",
            motivos_revisao_append=["alerta_desconhecido_ou_invalido"],
            metadata_merge={
                "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                "audit_pipeline": pipeline_context.to_audit_metadata(),
            },
        )
        logger.info(
            "Automacao: '%s' voltou para triagem manual (alerta desconhecido; flag OFF).",
            filename,
        )
        return {"status": "blocked_invalid_context"}
    elif not sector_id:
        if _discard_missing_sector_enabled():
            # Setor ausente -> nao da pra rotear/auditar; descarta PERMANENTE (tombstone).
            return execute_discard(
                item,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="setor_ausente_com_alerta_valido",
                status_result="discarded_invalid_context",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=sector_id,
                operator_name=operator_name,
                operator_id=operator_id,
                metadata=metadata,
            )
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
            "Setor ausente com alerta valido",
            motivos_revisao_append=["setor_ausente_com_alerta_valido"],
            metadata_merge={
                "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                "audit_pipeline": pipeline_context.to_audit_metadata(),
            },
        )
        logger.info(
            "Automacao: '%s' voltou para triagem manual (setor ausente, alerta=%s).",
            filename, alert_id,
        )
        return {"status": "blocked_invalid_context"}

    _set_progress_step("building_alert_and_hash", filename=filename)
    try:
        alert = _build_alert_from_classification(sector_id, alert_id)
    except AlertWithoutOfficialCriteriaError:
        if _discard_no_criteria_enabled():
            return execute_discard(
                item,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="alerta_sem_criterios",
                status_result="discarded_no_criteria",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=sector_id,
                operator_name=operator_name,
                operator_id=operator_id,
                metadata=metadata,
            )
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
            "Alerta sem criterios cadastrados",
            motivos_revisao_append=["alerta_sem_criterios"],
            metadata_merge={
                "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                "audit_pipeline": pipeline_context.to_audit_metadata(),
            },
        )
        logger.info(
            "Automacao: '%s' voltou para triagem manual porque o alerta '%s' nao possui criterios.",
            filename, alert_id
        )
        return {"status": "blocked_no_criteria"}

    if not getattr(alert, "criteria", None):
        if _discard_no_criteria_enabled():
            return execute_discard(
                item,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="alerta_sem_criterios",
                status_result="discarded_no_criteria",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=sector_id,
                operator_name=operator_name,
                operator_id=operator_id,
                metadata=metadata,
            )
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
            "Alerta sem criterios cadastrados",
            motivos_revisao_append=["alerta_sem_criterios"],
            metadata_merge={
                "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                "audit_pipeline": pipeline_context.to_audit_metadata(),
            },
        )
        logger.info(
            "Automacao: '%s' voltou para triagem manual porque o alerta '%s' nao possui criterios.",
            filename, alert_id
        )
        return {"status": "blocked_no_criteria"}

    mime_type = "application/pdf" if source_type == SOURCE_TYPE_PDF else get_mime_type(filename)
    audit_input_hash = compute_input_hash(
        media_bytes,
        mime_type,
        alert,
        operator_name,
        operator_id,
        sector_id,
    )

    _set_progress_step("checking_audit_cache", filename=filename)
    from core.automation_cache import AuditCacheGatekeeper, TranscriptionFallbackGatekeeper
    
    cache_result = AuditCacheGatekeeper.check_existing_audit(
        database.get_connection,
        audit_input_hash,
        pipeline_context,
        media_bytes,
        mime_type,
        filename,
        queue_input_hash,
    )
    if cache_result is not None:
        return cache_result

    if source_type == SOURCE_TYPE_PDF:
        from core.audit import process_pdf_audit

        _set_progress_step("processing_pdf_audit", filename=filename)
        result, result_hash, from_cache = await process_pdf_audit(
            media_bytes,
            mime_type,
            alert,
            operator_name,
            operator_id,
            sector_id,
            pipeline_context=pipeline_context,
        )
    else:
        from services import process_audit_with_ai

        _set_progress_step("transcribing_and_evaluating_audio", filename=filename)
        try:
            result, result_hash, from_cache = await process_audit_with_ai(
                media_bytes,
                mime_type,
                alert,
                operator_name,
                operator_id,
                sector_id,
                pipeline_context=pipeline_context,
            )
        except RuntimeError as exc:
            return TranscriptionFallbackGatekeeper.handle_transcription_runtime_error(
                exc,
                queue_input_hash,
                filename,
                pipeline_context,
                metadata=metadata,
            )
    hash_mismatch = bool(result_hash and result_hash != audit_input_hash)
    if hash_mismatch:
        logger.warning(
            "Automacao: hash de auditoria DIVERGENTE para '%s' (esperado=%s, retornado=%s). Assumindo o retornado como oficial.",
            filename,
            audit_input_hash,
            result_hash,
        )
    effective_audit_hash = result_hash or audit_input_hash

    if source_type == SOURCE_TYPE_AUDIO:
        quality_block = TranscriptionFallbackGatekeeper.check_new_audit_quality(
            result,
            queue_input_hash,
            filename,
            effective_audit_hash,
            pipeline_context,
        )
        if quality_block:
            return quality_block

    _set_progress_step("persisting_audit_artifacts", filename=filename)
    audit_id = database.persist_audit_artifacts(
        result,
        from_cache=from_cache,
        input_hash=effective_audit_hash,
        alert_id=alert_id,
        alert_label=alert.label,
        operator_id=operator_id,
        sector_id=sector_id,
        audio_bytes=media_bytes if source_type == SOURCE_TYPE_AUDIO else None,
        audio_mime_type=mime_type if source_type == SOURCE_TYPE_AUDIO else None,
        original_filename=filename,
        status=AUDIT_STATUS_AWAITING_PAIR,
        criado_por="automacao",
    )
    if not audit_id:
        raise AuditPersistenceError(
            f"Persistencia da auditoria nao retornou um id valido para '{filename}'."
        )
    _set_progress_step("marking_queue_audited", filename=filename)
    _mark_item_status(
        queue_input_hash,
        REVIEW_QUEUE_STATUS_AUDITED,
        metadata_merge={
            "audit_id": audit_id,
            "audit_input_hash": effective_audit_hash,
            "audit_pipeline": pipeline_context.to_audit_metadata(),
        },
    )
    logger.info(
        "Automacao: auditado '%s' (audit_id=%s, score: %.1f/%s)",
        filename,
        audit_id,
        result.score,
        result.maxPossibleScore,
    )
    return {"status": "audited", "audit_id": audit_id}


def _build_alert_from_classification(sector_id: str, alert_id: str) -> AuditAlert:
    """Monta o `AuditAlert` (alerta + critérios oficiais) a partir da classificação.

    Resolve aliases via `canonicalize_alert_id` (ex.: BAS-POLICIAL ->
    BAS-PRIORITARIO-POLICIA) ANTES de consultar o banco, para evitar
    `criteria=[]` silencioso. Em runtime, os critérios oficiais vêm
    exclusivamente do módulo Inteligência Artificial > Critérios (tabelas
    `audit_alerts`/`audit_criteria` no Neon).

    Levanta `AlertWithoutOfficialCriteriaError` se o banco não tiver critérios
    para o alerta (exceto em ambiente de teste isolado, onde o fallback é
    permitido por flag). Não tem efeito colateral.
    """
    from core.classification import canonicalize_alert_id, get_alert_lookup_by_id
    from db.database import get_connection
    from repositories.admin_criteria import get_criteria

    canonical_alert_id = canonicalize_alert_id(alert_id)
    alert_lookup = get_alert_lookup_by_id()
    alert_info = alert_lookup.get(canonical_alert_id) or alert_lookup.get(alert_id)

    if alert_info:
        _resolved_sector, _sector_label, alert_label = alert_info
    else:
        alert_label = canonical_alert_id

    criteria: list[AuditCriterion] = []
    try:
        db_criteria = get_criteria(get_connection, canonical_alert_id)
    except Exception:
        if allow_official_criteria_test_fallback():
            logger.info(
                "Automacao: ignorando falha ao carregar criterios do alerta em ambiente de teste isolado.",
            )
            db_criteria = []
        else:
            raise

    if db_criteria:
        for criterion in db_criteria:
            chave_val = criterion.get("chave")
            crit_id = chave_val if chave_val else f"crit_{criterion.get('id', 'unknown')}"
            criteria.append(
                AuditCriterion(
                    id=str(crit_id),
                    chave=str(chave_val) if chave_val else None,
                    label=criterion.get("label", ""),
                    weight=float(criterion.get("weight", 0)),
                    deflator=float(criterion.get("deflator", 0)) if criterion.get("deflator") is not None else None,
                    evaluation_type=criterion.get("evaluation_type", "auto"),
                    description=criterion.get("description", ""),
                )
            )
    elif not allow_official_criteria_test_fallback():
        raise AlertWithoutOfficialCriteriaError(
            "Alerta sem criterios oficiais cadastrados no modulo Inteligencia Artificial > Criterios "
            f"(alert_id={canonical_alert_id}, sector_id={sector_id})."
        )

    return AuditAlert(
        id=canonical_alert_id,
        label=alert_label,
        context=alert_label,
        criteria=criteria,
    )


def _mark_item_status(
    input_hash: str,
    status: str,
    error_message: str = None,
    *,
    motivos_revisao_append: Optional[list[str]] = None,
    metadata_merge: Optional[dict] = None,
) -> None:
    """Atualiza status/erro/motivos/metadata do item na fila (wrapper retrocompatível).

    Efeito colateral: UPDATE em `fila_revisao_classificacao`; `metadata_merge`
    faz merge (não substitui) no JSON de metadata existente.
    """
    database.atualizar_status_fila_revisao_classificacao(
        input_hash,
        status=status,
        erro=error_message,
        motivos_revisao_append=motivos_revisao_append,
        metadata_merge=metadata_merge,
    )
