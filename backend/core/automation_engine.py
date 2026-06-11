"""
Motor de Automação Híbrida.
Orquestra o fluxo contínuo: Telefonia (Huawei OBS D-1) -> Triagem -> Auditoria (IA) -> Arquivo (awaiting_pair).

A coleta de ligações usa exclusivamente o pipeline OBS D-1 (lote diário do dia
anterior). O caminho querycalls (executar_sync_huawei) continua disponível
apenas no módulo Telefonia para coleta manual ad-hoc, fora deste motor.
"""
import asyncio
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
import traceback

import db.database as database
from core import cost_guard
from core.huawei_d_minus_1 import executar_d_minus_1_pipeline
from core.automation import audit_all_pending, get_automation_status
from repositories.common import get_row_value

logger = logging.getLogger(__name__)

_AUTOMATION_CYCLE_LOCK_KEY = 2026042001

# Controle em memória do loop
_engine_task: asyncio.Task | None = None
_stop_event: asyncio.Event | None = None
_current_run_id: int | None = None
_current_status = {
    "is_running": False,
    "is_cycle_running": False,
    "current_stage": "idle",
    "current_message": "Aguardando proximo gatilho.",
    "current_run_source": None,
    "started_at": None,
    "finished_at": None,
    "last_run": None,
    "last_run_source": None,
    "last_error": None,
    "last_sync": None,
    "last_audit": None,
    "last_result": None,
    "baixadas_total": 0,
    "auditadas_total": 0,
}

_health_snapshot_cache: dict[str, object] = {
    "loaded_at": 0.0,
    "snapshot": None,
}


_MISSING = object()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _update_status(**updates) -> None:
    _current_status.update(updates)


def _json_dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _iso_or_none(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _parse_iso_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _empty_health_snapshot() -> dict:
    return {
        "available": False,
        "queue_by_status": {},
        "sync_status_24h": {},
        "sync_failure_reasons_24h": {},
        "cycle_status_24h": {},
        "cycle_totals_24h": {
            "runs": 0,
            "baixadas": 0,
            "auditadas": 0,
        },
    }


def _get_health_snapshot_cache_ttl_seconds() -> int:
    raw = os.getenv("AUTOMATION_HEALTH_SNAPSHOT_TTL_SECONDS", "30")
    try:
        return max(0, int(str(raw or "30").strip()))
    except (TypeError, ValueError):
        logger.warning("AUTOMATION_HEALTH_SNAPSHOT_TTL_SECONDS invalido: %r. Usando 30.", raw)
        return 30


def _load_health_snapshot() -> dict:
    snapshot = _empty_health_snapshot()
    conn = None
    try:
        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT status, COUNT(*)
            FROM fila_revisao_classificacao
            WHERE COALESCE(metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
            GROUP BY status
            """
        )
        snapshot["queue_by_status"] = {
            str(status or "unknown"): _safe_int(total)
            for status, total in cursor.fetchall()
        }

        cursor.execute(
            """
            SELECT status, COALESCE(failure_reason, ''), COUNT(*)
            FROM huawei_sync_logs
            WHERE sincronizado_em >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            GROUP BY status, COALESCE(failure_reason, '')
            """
        )
        sync_status: dict[str, int] = {}
        failure_reasons: dict[str, int] = {}
        for status, reason, total in cursor.fetchall():
            status_key = str(status or "unknown")
            count = _safe_int(total)
            sync_status[status_key] = sync_status.get(status_key, 0) + count
            if reason:
                reason_key = str(reason)
                failure_reasons[reason_key] = failure_reasons.get(reason_key, 0) + count
        snapshot["sync_status_24h"] = sync_status
        snapshot["sync_failure_reasons_24h"] = failure_reasons

        cursor.execute(
            """
            SELECT status, COUNT(*), COALESCE(SUM(baixadas), 0), COALESCE(SUM(auditadas), 0)
            FROM automation_cycle_runs
            WHERE started_at >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            GROUP BY status
            """
        )
        cycle_status: dict[str, int] = {}
        cycle_totals = {"runs": 0, "baixadas": 0, "auditadas": 0}
        for status, total, baixadas, auditadas in cursor.fetchall():
            count = _safe_int(total)
            cycle_status[str(status or "unknown")] = count
            cycle_totals["runs"] += count
            cycle_totals["baixadas"] += _safe_int(baixadas)
            cycle_totals["auditadas"] += _safe_int(auditadas)
        snapshot["cycle_status_24h"] = cycle_status
        snapshot["cycle_totals_24h"] = cycle_totals
        snapshot["available"] = True
    except Exception as exc:
        logger.debug("Falha ao carregar snapshot de saude da automacao: %s", exc)
    finally:
        if conn is not None:
            conn.close()
    return snapshot


def _load_health_snapshot_cached() -> dict:
    """Throttle DB-heavy health probes used by UI polling.

    The Telefonia/settings screens ask for engine status periodically. Without
    caching, every poll re-queries queue, sync, and cycle aggregates even when
    automation is idle, increasing Neon compute wakeups and network transfer.
    """
    ttl_seconds = _get_health_snapshot_cache_ttl_seconds()
    if ttl_seconds <= 0:
        return _load_health_snapshot()

    now = time.monotonic()
    cached_snapshot = _health_snapshot_cache.get("snapshot")
    loaded_at = float(_health_snapshot_cache.get("loaded_at") or 0.0)
    if isinstance(cached_snapshot, dict) and now - loaded_at < ttl_seconds:
        return dict(cached_snapshot)

    snapshot = _load_health_snapshot()
    _health_snapshot_cache["loaded_at"] = now
    _health_snapshot_cache["snapshot"] = dict(snapshot)
    return snapshot


def _count_keys(mapping: dict, *keys: str) -> int:
    return sum(_safe_int(mapping.get(key)) for key in keys)


def _health_indicator(identifier: str, label: str, value: str, tone: str, detail: str = "") -> dict:
    return {
        "id": identifier,
        "label": label,
        "value": value,
        "tone": tone,
        "detail": detail,
    }


def _health_alert(identifier: str, severity: str, title: str, detail: str = "") -> dict:
    return {
        "id": identifier,
        "severity": severity,
        "title": title,
        "detail": detail,
    }


def _stage_label(stage: str | None) -> str:
    labels = {
        "idle": "Aguardando",
        "starting": "Iniciando",
        "syncing_d1": "Coletando Huawei",
        "auditing": "Auditando",
        "completed": "Concluido",
        "partial": "Concluido com atencao",
        "error": "Erro",
        "disabled": "Desligada",
        "paused": "Pausada",
        "cancelled": "Cancelada",
        "stale": "Sem progresso",
    }
    normalized = str(stage or "idle").strip().lower()
    return labels.get(normalized, normalized.replace("_", " ").title())


def _build_automation_health_report(status: dict, snapshot: dict | None = None) -> dict:
    snapshot = snapshot or _empty_health_snapshot()
    queue_by_status = snapshot.get("queue_by_status") or {}
    sync_status = snapshot.get("sync_status_24h") or {}
    sync_reasons = snapshot.get("sync_failure_reasons_24h") or {}
    cycle_status = snapshot.get("cycle_status_24h") or {}
    cycle_totals = snapshot.get("cycle_totals_24h") or {}

    is_enabled = bool(status.get("is_enabled"))
    is_running = bool(status.get("is_running") or status.get("is_cycle_running"))
    is_paused = bool(status.get("is_paused"))
    is_stale = bool(status.get("latest_run_is_stale"))
    stage = str(status.get("current_stage") or "idle")

    ready_count = _count_keys(queue_by_status, "auto_resolved", "reviewed")
    manual_count = _count_keys(queue_by_status, "pending", "needs_manual_triage", "blocked_operator")
    capped_count = _count_keys(queue_by_status, "monthly_capped")
    audited_count = _count_keys(queue_by_status, "audited")
    failed_syncs = _count_keys(sync_status, "failed", "error")
    direction_blocks = _count_keys(
        sync_reasons,
        "receptiva_setor_risco",
        "receptiva_pretriagem_audio",
        "receptiva_setor_desconhecido",
        "direcao_desconhecida",
        "direcao_incompativel",
    )

    alerts: list[dict] = []
    if is_stale:
        alerts.append(
            _health_alert(
                "stale-cycle",
                "critical",
                "Ciclo sem sinal de progresso",
                "O ultimo ciclo continua como em andamento, mas o heartbeat parou.",
            )
        )
    if status.get("last_error"):
        alerts.append(
            _health_alert(
                "last-error",
                "warning",
                "Ultimo ciclo registrou erro",
                str(status.get("last_error")),
            )
        )
    if failed_syncs > 0:
        alerts.append(
            _health_alert(
                "sync-failures",
                "warning",
                "Falhas na coleta nas ultimas 24h",
                f"{failed_syncs} chamada(s) falharam durante a coleta Huawei.",
            )
        )
    if direction_blocks >= 50:
        alerts.append(
            _health_alert(
                "direction-blocks",
                "warning",
                "Muitas chamadas bloqueadas por direcao",
                f"{direction_blocks} bloqueio(s) por direcao nas ultimas 24h.",
            )
        )
    if manual_count >= 20:
        alerts.append(
            _health_alert(
                "manual-queue",
                "warning",
                "Triagem manual acumulada",
                f"{manual_count} item(ns) aguardam intervencao operacional.",
            )
        )
    if ready_count > 0 and is_enabled and not is_running:
        alerts.append(
            _health_alert(
                "ready-queue",
                "info",
                "Ha itens prontos para a automacao",
                f"{ready_count} item(ns) aguardam o proximo ciclo.",
            )
        )

    if not is_enabled:
        overall_status = "disabled"
        headline = "Automacao desligada."
    elif any(alert["severity"] == "critical" for alert in alerts):
        overall_status = "critical"
        headline = "Atencao critica no ciclo automatico."
    elif any(alert["severity"] == "warning" for alert in alerts):
        overall_status = "warning"
        headline = "Automacao operando com pontos de atencao."
    elif is_paused:
        overall_status = "warning"
        headline = "Ciclo pausado pelo usuario."
    elif is_running:
        overall_status = "running"
        headline = "Ciclo em progresso."
    else:
        overall_status = "ok"
        headline = "Automacao saudavel e aguardando agenda."

    if is_stale:
        engine_value = "Sem progresso"
        engine_tone = "danger"
    elif is_paused:
        engine_value = "Pausada"
        engine_tone = "warning"
    elif is_running:
        engine_value = "Rodando"
        engine_tone = "info"
    elif is_enabled:
        engine_value = "Ligada"
        engine_tone = "success"
    else:
        engine_value = "Desligada"
        engine_tone = "neutral"

    audit_progress = status.get("audit_progress") if isinstance(status.get("audit_progress"), dict) else {}
    total = max(
        _safe_int(audit_progress.get("total")),
        _safe_int(audit_progress.get("requested_audits")),
        _safe_int(audit_progress.get("target_count")),
    )
    completed = _safe_int(audit_progress.get("completed"))
    failed = _safe_int(audit_progress.get("failed"))
    blocked = _safe_int(audit_progress.get("blocked"))
    done = completed + failed
    progress_value = f"{done}/{total}" if total > 0 else ("Em progresso" if is_running else "Sem lote")
    progress_detail = f"{blocked} bloqueado(s)" if blocked else _stage_label(stage)

    indicators = [
        _health_indicator("engine", "Motor", engine_value, engine_tone, _stage_label(stage)),
        _health_indicator("progress", "Progresso", progress_value, "info" if is_running else "neutral", progress_detail),
        _health_indicator(
            "today",
            "Hoje",
            f"{_safe_int(status.get('auditadas_total'))} auditadas",
            "success",
            f"{_safe_int(status.get('baixadas_total'))} baixadas",
        ),
        _health_indicator(
            "queue",
            "Fila",
            f"{ready_count} prontas",
            "warning" if manual_count >= 20 else "neutral",
            f"{manual_count} em triagem; {capped_count} em cota",
        ),
    ]

    return {
        "status": overall_status,
        "headline": headline,
        "generated_at": _now_iso(),
        "indicators": indicators,
        "alerts": alerts,
        "metrics": {
            "queue_by_status": queue_by_status,
            "sync_status_24h": sync_status,
            "sync_failure_reasons_24h": sync_reasons,
            "cycle_status_24h": cycle_status,
            "cycle_totals_24h": cycle_totals,
            "ready_queue": ready_count,
            "manual_queue": manual_count,
            "audited_queue": audited_count,
            "direction_blocks_24h": direction_blocks,
            "sync_failures_24h": failed_syncs,
            "data_available": bool(snapshot.get("available")),
        },
    }


def _get_heartbeat_stale_seconds() -> int:
    raw = os.getenv("AUTOMATION_HEARTBEAT_STALE_SECONDS", "300")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 300
    return max(30, min(parsed, 3600))


def _latest_run_is_stale(latest_run: dict | None) -> bool:
    if not isinstance(latest_run, dict) or latest_run.get("status") != "running":
        return False
    heartbeat = _parse_iso_datetime(latest_run.get("last_heartbeat_at"))
    if heartbeat is None:
        heartbeat = _parse_iso_datetime(latest_run.get("started_at"))
    if heartbeat is None:
        return False
    now = datetime.now(timezone.utc) if heartbeat.tzinfo is not None else datetime.now()
    age_seconds = (now - heartbeat).total_seconds()
    return age_seconds > _get_heartbeat_stale_seconds()


def _reconcile_stale_running_cycles() -> None:
    """Verifica se há ciclos 'running' estagnados e os marca como 'stale' antes de tentar adquirir o lock."""
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, last_heartbeat_at, started_at
            FROM automation_cycle_runs 
            WHERE status = 'running'
            """
        )
        rows = cursor.fetchall()
        stale_ids = []
        for row in rows:
            latest_run = {"status": "running", "last_heartbeat_at": row[1], "started_at": row[2]}
            if _latest_run_is_stale(latest_run):
                stale_ids.append(row[0])
                
        if stale_ids:
            logger.warning("Encontrados %d ciclos estagnados. Reconciliando para 'stale'.", len(stale_ids))
            stale_seconds = _get_heartbeat_stale_seconds()
            cursor.execute(
                """
                UPDATE automation_cycle_runs 
                SET status = 'stale', 
                    stage = 'stale',
                    finished_at = CURRENT_TIMESTAMP, 
                    error_message = 'Heartbeat expirado, reconciliado antes do proximo ciclo'
                WHERE id = ANY(%s)
                """,
                (stale_ids,)
            )
            cursor.execute(
                """
                UPDATE configuracoes
                SET valor = CASE
                        WHEN chave = 'automation_engine_lock' THEN 'released'
                        ELSE 'false'
                    END,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE chave IN ('automation_engine_lock', 'huawei_d1_run_lock', 'sync_lock')
                  AND (
                        (chave = 'automation_engine_lock' AND valor NOT IN ('released', 'false'))
                     OR (chave = 'huawei_d1_run_lock' AND valor = 'running')
                     OR (chave = 'sync_lock' AND valor = 'true')
                  )
                  AND CAST(atualizado_em AS timestamp) < CURRENT_TIMESTAMP - (%s * interval '1 second')
                """,
                (stale_seconds,),
            )
            conn.commit()
    except Exception as exc:
        logger.error("Erro ao tentar reconciliar ciclos estagnados: %s", str(exc))
    finally:
        conn.close()



def _config_flag(key: str) -> bool:
    return str(database.get_config_value(key, "false") or "").strip().lower() == "true"


def _read_control_flags() -> tuple[bool, bool]:
    return _config_flag("automacao_is_paused"), _config_flag("automacao_is_cancelled")


def _apply_control_flags_to_progress(
    progress,
    *,
    is_paused: bool,
    is_cancelled: bool,
    force_running: bool = False,
) -> dict | None:
    if not isinstance(progress, dict):
        if force_running:
            progress = {"is_running": True}
        else:
            return progress

    merged = dict(progress)
    if force_running:
        merged.setdefault("is_running", True)
    if is_cancelled:
        merged["is_cancelled"] = True
        merged["is_paused"] = False
    elif is_paused and merged.get("is_running"):
        merged["is_paused"] = True
    return merged


def _is_audit_stage(latest_run: dict | None) -> bool:
    if not isinstance(latest_run, dict):
        return False
    return latest_run.get("stage") == "auditing"


def _db_audit_progress_is_active(latest_run: dict | None) -> bool:
    if not isinstance(latest_run, dict) or latest_run.get("status") != "running":
        return False
    if _latest_run_is_stale(latest_run):
        return False
    audit_result = latest_run.get("audit_result")
    if isinstance(audit_result, dict) and audit_result.get("is_running"):
        return True
    return _is_audit_stage(latest_run)


def _apply_control_flags_to_status_progress(
    progress,
    *,
    latest_run: dict | None,
    is_paused: bool,
    is_cancelled: bool,
):
    return _apply_control_flags_to_progress(
        progress,
        is_paused=is_paused,
        is_cancelled=is_cancelled,
        force_running=_db_audit_progress_is_active(latest_run),
    )


def _normalize_local_progress(progress, *, is_paused: bool, is_cancelled: bool):
    if not isinstance(progress, dict):
        return progress

    return _apply_control_flags_to_progress(
        progress,
        is_paused=is_paused,
        is_cancelled=is_cancelled,
        force_running=False,
    )


class _AutomationCycleLock:
    """PgBouncer-safe row lock with owner token.

    Conexao do pool e efemera: adquirida e devolvida dentro de cada metodo,
    nao retida entre chamadas. Antes, `self._conn` ficava preso entre
    `acquire()` e `release()` (minutos durante o ciclo), consumindo 1 slot
    do BoundedSemaphore do pool (`DB_POOL_MAX_CONN=20`) e contribuindo para
    a latencia observada em endpoints da Telefonia enquanto a automacao
    rodava (sintoma documentado em v1.3.91).
    """

    _KEY = "automation_engine_lock"
    _TTL_SECONDS = 30 * 60

    def __init__(self) -> None:
        self.acquired = False
        self._token = f"owner:{secrets.token_hex(16)}"

    def acquire(self) -> bool:
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO configuracoes (chave, valor, atualizado_em)
                VALUES (%s, 'released', CURRENT_TIMESTAMP)
                ON CONFLICT (chave) DO NOTHING
                """,
                (self._KEY,),
            )

            cursor.execute(
                """
                UPDATE configuracoes
                SET valor = %s, atualizado_em = CURRENT_TIMESTAMP
                WHERE chave = %s
                  AND (
                    valor IN ('released', 'false')
                    OR CAST(atualizado_em AS timestamp) < CURRENT_TIMESTAMP - (%s * interval '1 second')
                  )
                RETURNING chave
                """,
                (self._token, self._KEY, self._TTL_SECONDS),
            )
            row = cursor.fetchone()
            conn.commit()
            self.acquired = bool(row)
            return self.acquired
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            self.acquired = False
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def refresh(self) -> bool:
        if not self.acquired:
            return False
        try:
            conn = database.get_connection()
        except Exception as exc:
            # Sem conexao nao da para PROVAR a posse do lock: trata como
            # perdido (False) em vez de estourar erro cru no meio do ciclo —
            # o caller aborta de forma limpa via AutomationLockLostError.
            logger.warning("Refresh do lock do ciclo falhou ao conectar: %s", exc)
            self.acquired = False
            return False
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE configuracoes
                SET atualizado_em = CURRENT_TIMESTAMP
                WHERE chave = %s
                  AND valor = %s
                RETURNING chave
                """,
                (self._KEY, self._token),
            )
            row = cursor.fetchone()
            conn.commit()
            self.acquired = bool(row)
            return self.acquired
        except Exception as exc:
            logger.warning("Refresh do lock do ciclo falhou: %s", exc)
            self.acquired = False
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _try_release_once(self) -> bool:
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE configuracoes
                SET valor = 'released', atualizado_em = CURRENT_TIMESTAMP
                WHERE chave = %s
                  AND valor = %s
                """,
                (self._KEY, self._token),
            )
            conn.commit()
            return True
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def release(self) -> None:
        if not self.acquired:
            return
        # Uma re-tentativa com conexao NOVA antes de desistir: falha aqui
        # deixa o lock preso ate o TTL (30 min) e atrasa o proximo ciclo.
        # Cada tentativa usa conexao propria — conexao stale da primeira
        # tentativa nao contamina a segunda.
        try:
            self._try_release_once()
        except Exception as exc:
            logger.warning(
                "Falha ao liberar lock do ciclo de automacao (1a tentativa): %s; "
                "tentando novamente com conexao nova.",
                exc,
            )
            try:
                self._try_release_once()
            except Exception as retry_exc:
                logger.warning(
                    "Falha ao liberar lock do ciclo de automacao (2a tentativa): %s. "
                    "Lock expira pelo TTL de %ss.",
                    retry_exc,
                    self._TTL_SECONDS,
                )
        finally:
            self.acquired = False

    def __enter__(self) -> "_AutomationCycleLock":
        # Returns self so callers can inspect `.acquired` without raising.
        # release() is idempotent (no-op when self.acquired is False), so
        # __exit__ is safe to call regardless of acquisition outcome.
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.release()
        return False  # never suppress exceptions


class AutomationLockLostError(RuntimeError):
    """Raised when the row lock owner token is no longer held by this cycle."""


async def _await_with_lock_refresh(
    awaitable,
    cycle_lock: _AutomationCycleLock,
    *,
    interval_seconds: float = 60.0,
    run_id: int | None = None,
):
    task = asyncio.create_task(awaitable)
    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=interval_seconds)
            if done:
                return await task
            if not await asyncio.to_thread(cycle_lock.refresh):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                raise AutomationLockLostError("Lock da automacao perdido durante ciclo em andamento.")
            if run_id is not None:
                _persist_cycle_update(run_id)
    except asyncio.CancelledError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise
    except Exception:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        raise


def _create_cycle_run(source: str, started_at: str) -> int | None:
    conn = None
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO automation_cycle_runs (source, status, stage, message, started_at)
            VALUES (%s, 'running', 'starting', %s, %s)
            RETURNING id
            """,
            (source, "Ciclo de automacao iniciado.", started_at),
        )
        row = cursor.fetchone()
        conn.commit()
        return int(get_row_value(row, "id") or row[0])
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning("Nao foi possivel registrar ciclo de automacao no banco: %s", exc)
        return None
    finally:
        if conn is not None:
            conn.close()


def _persist_cycle_update(
    run_id: int | None,
    *,
    status: str | None = None,
    stage: str | None = None,
    message: str | None = None,
    finished_at: str | None = None,
    baixadas: int | None = None,
    auditadas: int | None = None,
    error_message: str | None = None,
    sync_result=_MISSING,
    audit_result=_MISSING,
    result=_MISSING,
) -> None:
    if run_id is None:
        return

    assignments = ["last_heartbeat_at = CURRENT_TIMESTAMP"]
    params: list = []

    def add(column: str, value) -> None:
        assignments.append(f"{column} = %s")
        params.append(value)

    if status is not None:
        add("status", status)
    if stage is not None:
        add("stage", stage)
    if message is not None:
        add("message", message)
    if finished_at is not None:
        add("finished_at", finished_at)
    if baixadas is not None:
        add("baixadas", baixadas)
    if auditadas is not None:
        add("auditadas", auditadas)
    if error_message is not None:
        add("error_message", error_message)
    if sync_result is not _MISSING:
        assignments.append("sync_result = %s::jsonb")
        params.append(_json_dumps(sync_result))
    if audit_result is not _MISSING:
        assignments.append("audit_result = %s::jsonb")
        params.append(_json_dumps(audit_result))
    if result is not _MISSING:
        assignments.append("result = %s::jsonb")
        params.append(_json_dumps(result))

    params.append(run_id)
    conn = None
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE automation_cycle_runs SET {', '.join(assignments)} WHERE id = %s",
            tuple(params),
        )
        conn.commit()
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning("Nao foi possivel atualizar ciclo de automacao %s: %s", run_id, exc)
    finally:
        if conn is not None:
            conn.close()


def _latest_cycle_run() -> dict | None:
    conn = None
    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                id, source, status, stage, message, started_at, finished_at,
                last_heartbeat_at, baixadas, auditadas, error_message,
                sync_result, audit_result, result
            FROM automation_cycle_runs
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.commit()
        if not row:
            return None
        return {
            "id": get_row_value(row, "id"),
            "source": get_row_value(row, "source"),
            "status": get_row_value(row, "status"),
            "stage": get_row_value(row, "stage"),
            "message": get_row_value(row, "message"),
            "started_at": _iso_or_none(get_row_value(row, "started_at")),
            "finished_at": _iso_or_none(get_row_value(row, "finished_at")),
            "last_heartbeat_at": _iso_or_none(get_row_value(row, "last_heartbeat_at")),
            "baixadas": get_row_value(row, "baixadas") or 0,
            "auditadas": get_row_value(row, "auditadas") or 0,
            "error_message": get_row_value(row, "error_message"),
            "sync_result": get_row_value(row, "sync_result"),
            "audit_result": get_row_value(row, "audit_result"),
            "result": get_row_value(row, "result"),
        }
    except Exception as exc:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.warning("Nao foi possivel carregar ultimo ciclo de automacao: %s", exc)
        return None
    finally:
        if conn is not None:
            conn.close()


async def _audit_all_pending_with_progress(
    run_id: int | None,
    *,
    cycle_lock: _AutomationCycleLock | None = None,
) -> dict:
    audit_task = asyncio.create_task(audit_all_pending(reset_control_flags=False))
    last_lock_refresh = time.monotonic()
    try:
        while not audit_task.done():
            await asyncio.sleep(1)
            progress = get_automation_status()
            is_paused, is_cancelled = _read_control_flags()
            progress = _normalize_local_progress(
                progress,
                is_paused=is_paused,
                is_cancelled=is_cancelled,
            )
            _update_status(last_audit=progress)
            _persist_cycle_update(run_id, audit_result=progress)

            if cycle_lock is not None and time.monotonic() - last_lock_refresh >= 60:
                if not await asyncio.to_thread(cycle_lock.refresh):
                    audit_task.cancel()
                    try:
                        await audit_task
                    except asyncio.CancelledError:
                        pass
                    raise AutomationLockLostError("Lock da automacao perdido durante a auditoria.")
                last_lock_refresh = time.monotonic()
        return await audit_task
    except asyncio.CancelledError:
        logger.warning("Ciclo de automacao cancelado; cancelando auditoria pendente em background.")
        audit_task.cancel()
        try:
            await audit_task
        except asyncio.CancelledError:
            pass
        raise
    except Exception:
        if not audit_task.done():
            audit_task.cancel()
            try:
                await audit_task
            except asyncio.CancelledError:
                pass
        raise


async def _classify_pending_huawei_items(
    run_id: int | None,
    *,
    cycle_lock: _AutomationCycleLock | None = None,
) -> dict:
    from core.huawei_sync import _build_operator_indexes, _classificar_pendentes_async
    from repositories.operators import listar_auditaveis_com_id_huawei

    _update_status(
        current_stage="classifying",
        current_message="Classificando ligacoes pendentes na fila (IA).",
    )
    _persist_cycle_update(
        run_id,
        stage="classifying",
        message="Classificando ligacoes pendentes na fila (IA).",
    )

    operadores = await asyncio.to_thread(listar_auditaveis_com_id_huawei, database.get_connection)
    op_by_id, op_by_name = _build_operator_indexes(operadores)

    def _classification_progress(_stage: str, current: int, total: int) -> None:
        if total > 0:
            message = f"Classificando ligacoes pendentes: {current}/{total}."
        else:
            message = "Classificando ligacoes pendentes."
        _update_status(current_stage="classifying", current_message=message)
        _persist_cycle_update(run_id, stage="classifying", message=message)

    classification_task = _classificar_pendentes_async(
        concurrency=3,
        operator_by_id=op_by_id,
        operator_by_name=op_by_name,
        should_cancel=_automation_cancel_requested,
        progress_callback=_classification_progress,
    )

    if cycle_lock is not None:
        return await _await_with_lock_refresh(
            classification_task,
            cycle_lock,
            run_id=run_id,
        )
    return await classification_task


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

def is_in_process_engine_enabled() -> bool:
    """Return whether the resident FastAPI background loop should be started."""
    return _env_flag("ENABLE_IN_PROCESS_AUTOMATION_ENGINE", False)

def is_automation_enabled() -> bool:
    """Verifica no banco se a automação híbrida está ligada."""
    val = database.get_config_value("automacao_hibrida_ativa", "false")
    return val.strip().lower() == "true"


def _automation_cancel_requested() -> bool:
    return _config_flag("automacao_is_cancelled")


def _reset_cycle_control_flags() -> None:
    database.update_config(
        "automacao_is_paused",
        "false",
        alterado_por="system:automation_engine",
        motivo="run_automation_cycle() reset",
        origem="system",
    )
    database.update_config(
        "automacao_is_cancelled",
        "false",
        alterado_por="system:automation_engine",
        motivo="run_automation_cycle() reset",
        origem="system",
    )


def _sync_result_contains_status(sync_result: dict, statuses: set[str]) -> bool:
    if not isinstance(sync_result, dict):
        return False
    top_status = str(sync_result.get("status") or "").strip().lower()
    if top_status in statuses:
        return True
    for item in sync_result.get("executados", []) or []:
        if not isinstance(item, dict):
            continue
        item_status = str(item.get("status") or "").strip().lower()
        inner = item.get("result") if isinstance(item.get("result"), dict) else {}
        inner_status = str(inner.get("status") or "").strip().lower()
        if item_status in statuses or inner_status in statuses:
            return True
    return False


_SYNC_FILTER_LABELS = (
    ("ignoradas_direcao_desconhecida", "direcao desconhecida"),
    ("ignoradas_operador_huawei_nao_cadastrado", "operador Huawei nao cadastrado"),
    ("ignoradas_duracao_minima", "duracao minima"),
    ("ignoradas_cota_mensal_pre_download", "cota mensal"),
    ("ignoradas_setor_nao_telefonia", "setor nao telefonia"),
    ("ignoradas_receptiva_setor_risco", "receptiva em setor de risco"),
    ("triagem_descartados", "triagem setorial"),
)


def _iter_sync_inner_results(sync_result: dict) -> list[dict]:
    if not isinstance(sync_result, dict):
        return []
    inners: list[dict] = []
    for item in sync_result.get("executados", []) or []:
        if not isinstance(item, dict):
            continue
        inner = item.get("result")
        if isinstance(inner, dict):
            inners.append(inner)
    if not inners and any(key in sync_result for key, _label in _SYNC_FILTER_LABELS):
        inners.append(sync_result)
    return inners


def _summarize_zero_download_filters(sync_result: dict) -> str:
    totals: dict[str, int] = {}
    for inner in _iter_sync_inner_results(sync_result):
        for key, label in _SYNC_FILTER_LABELS:
            totals[label] = totals.get(label, 0) + _safe_int(inner.get(key))

    top = [(label, count) for label, count in totals.items() if count > 0]
    top.sort(key=lambda item: item[1], reverse=True)
    if not top:
        return ""
    return "; ".join(f"{label}: {count}" for label, count in top[:3])


def set_automation_enabled(enabled: bool) -> None:
    """Ativa ou desativa a automação híbrida."""
    database.update_config(
        "automacao_hibrida_ativa",
        "true" if enabled else "false",
        alterado_por="system:automation_engine",
        motivo="set_automation_enabled(%s)" % bool(enabled),
        origem="system",
    )


def set_automation_enabled_atomic(enabled: bool) -> None:
    """Atomically toggle all gates required by the automatic cycle.

    The toggle in the UI represents a single user intent: "automation on/off".
    Historically the frontend issued separate writes, which left the system in
    inconsistent states such as auditor on, D-1 on, but the Telefonia collector
    disabled. This helper writes the engine, D-1, and collector gates in a
    single Postgres transaction so the toggle either fully succeeds or fully
    fails.
    """
    flag = "true" if enabled else "false"
    motivo = "set_automation_enabled_atomic(%s)" % bool(enabled)
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        for chave in ("automacao_hibrida_ativa", "huawei_d1_enabled", "telefonia_cron_sync_ativa"):
            # Snapshot pra audit_log antes do UPSERT
            cursor.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
            row = cursor.fetchone()
            valor_antes = row[0] if row else None
            cursor.execute(
                """
                INSERT INTO configuracoes (chave, valor, atualizado_em)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (chave)
                DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = CURRENT_TIMESTAMP
                """,
                (chave, flag),
            )
            if valor_antes != flag:
                cursor.execute(
                    """
                    INSERT INTO configuracoes_audit_log
                        (chave, valor_antes, valor_depois, alterado_por, motivo, origem)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (chave, valor_antes, flag, "system:automation_engine", motivo, "system"),
                )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _get_automation_interval_seconds() -> int:
    raw = database.get_config_value("automacao_intervalo_segundos", "600")
    try:
        return max(1, int(str(raw or "600").strip()))
    except (TypeError, ValueError):
        logger.warning("Configuracao automacao_intervalo_segundos invalida: %r. Usando 600.", raw)
        return 600

async def run_automation_cycle(*, source: str = "manual") -> dict:
    """Execute one bounded audit cycle over items already collected into the queue."""
    global _current_run_id, _current_status
    if not is_automation_enabled() and source != "manual_ui":
        logger.info("Automacao hibrida desligada; ciclo unico ignorado.")
        _update_status(
            is_running=False,
            is_cycle_running=False,
            current_stage="disabled",
            current_message="Automacao hibrida desligada.",
            current_run_source=source,
            finished_at=_now_iso(),
        )
        return {
            "status": "disabled",
            "message": "Automacao hibrida desligada.",
            "baixadas": 0,
            "auditadas": 0,
        }

    # Guardrail de orcamento: ciclo nem comeca quando o teto diario de
    # consumo pago foi atingido (ou o kill-switch de custo esta ativo).
    # Nenhum item e descartado — a fila aguarda o reset diario do contador.
    budget_reason = cost_guard.budget_exceeded()
    if budget_reason:
        logger.warning("Ciclo de automacao bloqueado pelo guardrail de orcamento (%s).", budget_reason)
        _update_status(
            is_running=False,
            is_cycle_running=False,
            current_stage="budget_blocked",
            current_message=f"Ciclo bloqueado pelo guardrail de orcamento: {budget_reason}.",
            current_run_source=source,
            finished_at=_now_iso(),
        )
        return {
            "status": "budget_blocked",
            "message": f"Ciclo bloqueado pelo guardrail de orcamento: {budget_reason}.",
            "baixadas": 0,
            "auditadas": 0,
        }

    _reconcile_stale_running_cycles()

    cycle_lock = _AutomationCycleLock()
    if not cycle_lock.acquire():
        logger.info("Automacao ja esta em andamento em outra instancia; ciclo %s ignorado.", source)
        return {
            "status": "skipped",
            "message": "Automacao ja esta em andamento.",
            "baixadas": 0,
            "auditadas": 0,
        }

    # All post-acquire work runs inside this try/finally so the lock is
    # released even if asyncio.CancelledError or any exception fires before
    # we reach the first await. Closing the gap was specifically called out
    # in the C4 finding of the code review (commit f70d041 fixed the audit
    # task path; this closes the same window for the cycle setup itself).
    try:
        started_at = _now_iso()
        _current_run_id = _create_cycle_run(source, started_at)
        _reset_cycle_control_flags()
        _update_status(
            is_running=True,
            is_cycle_running=True,
            current_stage="starting",
            current_message="Ciclo de automacao iniciado.",
            current_run_source=source,
            started_at=started_at,
            finished_at=None,
            last_error=None,
        )
        logger.info("Automacao ativa. Iniciando ciclo OBS D-1 + auditoria.")

        try:
            from db.database import limpar_fila_revisao_classificacao_antiga
            cleanup_result = await asyncio.to_thread(limpar_fila_revisao_classificacao_antiga, 24)
            if cleanup_result and cleanup_result.get("deleted", 0) > 0:
                logger.info("Limpeza: Removidos %d itens obsoletos/não resolvidos da fila.", cleanup_result["deleted"])
        except Exception as cleanup_exc:
            logger.warning("Falha ao executar limpeza da fila de triagem: %s", cleanup_exc)

        sync_result: dict = {"status": "error", "baixadas": 0}
        try:
            _update_status(
                current_stage="syncing_d1",
                current_message="Baixando e classificando lote OBS D-1.",
            )
            _persist_cycle_update(
                _current_run_id,
                stage="syncing_d1",
                message="Baixando e classificando lote OBS D-1.",
            )

            # Força a classificacao via IA (fase 2) para que o fluxo seja 100% autonomo.
            # Sem isso, as ligacoes parariam na fila de Triagem ("pending") aguardando
            # intervencao manual e seriam ignoradas pelo audit_all_pending().
            original_enable_classify = os.environ.get("HUAWEI_SYNC_ENABLE_CLASSIFY")
            os.environ["HUAWEI_SYNC_ENABLE_CLASSIFY"] = "true"
            last_progress_persist = 0.0
            last_progress_stage = ""

            def _sync_progress(stage: str, current: int, total: int) -> None:
                nonlocal last_progress_persist, last_progress_stage
                stage_text = str(stage or "syncing").replace("_", " ")
                if total > 0:
                    message = f"Baixando lote OBS D-1: {stage_text} ({current}/{total})."
                else:
                    message = f"Baixando lote OBS D-1: {stage_text}."
                _update_status(current_stage="syncing_d1", current_message=message)

                now_monotonic = time.monotonic()
                should_persist = (
                    stage != last_progress_stage
                    or current == total
                    or now_monotonic - last_progress_persist >= 15
                )
                if should_persist:
                    _persist_cycle_update(
                        _current_run_id,
                        stage="syncing_d1",
                        message=message,
                    )
                    last_progress_persist = now_monotonic
                    last_progress_stage = stage

            try:
                sync_result = await _await_with_lock_refresh(
                    executar_d_minus_1_pipeline(
                        should_cancel=_automation_cancel_requested,
                        progress_callback=_sync_progress,
                        force=(source == "manual_ui"),
                    ),
                    cycle_lock,
                    run_id=_current_run_id,
                )
            finally:
                if original_enable_classify is not None:
                    os.environ["HUAWEI_SYNC_ENABLE_CLASSIFY"] = original_enable_classify
                else:
                    os.environ.pop("HUAWEI_SYNC_ENABLE_CLASSIFY", None)

            _update_status(last_sync=sync_result)
            _persist_cycle_update(_current_run_id, sync_result=sync_result)
        except asyncio.CancelledError:
            raise
        except AutomationLockLostError:
            raise
        except Exception as sync_exc:
            logger.error("Falha no pipeline D-1 durante ciclo de automacao: %s", sync_exc)
            sync_result = {"status": "error", "message": str(sync_exc), "baixadas": 0}
            _update_status(
                last_error=f"Sync Error: {str(sync_exc)}",
                last_sync=sync_result,
            )
            _persist_cycle_update(
                _current_run_id,
                status="running",
                error_message=f"Sync Error: {str(sync_exc)}",
                sync_result=sync_result,
            )

        sync_status = str(sync_result.get("status") or "").strip().lower()
        if _automation_cancel_requested() or _sync_result_contains_status(sync_result, {"cancelled"}):
            logger.warning("Ciclo de automacao cancelado durante o pipeline D-1.")
            result = {
                "status": "cancelled",
                "source": source,
                "sync": sync_result,
                "audit": {"status": "skipped", "message": "Ciclo cancelado durante a coleta D-1."},
                "baixadas": 0,
                "auditadas": 0,
            }
            _update_status(
                current_stage="cancelled",
                current_message="Ciclo cancelado durante a coleta D-1.",
                last_run=_now_iso(),
                last_run_source=source,
                last_result=result,
                finished_at=_now_iso(),
            )
            _persist_cycle_update(
                _current_run_id,
                status="cancelled",
                stage="cancelled",
                message="Ciclo cancelado durante a coleta D-1.",
                finished_at=_current_status.get("finished_at"),
                sync_result=sync_result,
                result=result,
            )
            return result
        if sync_status == "disabled":
            logger.info("Pipeline D-1 desligado nas configuracoes; prosseguindo para triagem/auditoria.")
            # Do NOT return here. Proceed to audit.
            sync_result["baixadas"] = 0
            # Keep sync_status as "disabled" so it doesn't trigger the "error" block below

        # Soma "baixadas" de todas as datas processadas no lookback.
        baixadas = 0
        for item in sync_result.get("executados", []) or []:
            inner = item.get("result") or {}
            baixadas += int(inner.get("baixadas", 0) or 0)
        _current_status["baixadas_total"] += baixadas

        # Se D-1 falhou (status=error), pular fase de auditoria para evitar
        # auditar itens fantasmas ou em estado inconsistente. Marcar ciclo
        # como 'partial'.
        if _sync_result_contains_status(sync_result, {"partial"}):
            _update_status(last_error="Pipeline D-1 terminou parcialmente.")
            _persist_cycle_update(
                _current_run_id,
                error_message="Pipeline D-1 terminou parcialmente.",
            )

        if sync_status in {"error", "missing_credentials"}:
            logger.warning(
                "Pipeline D-1 retornou erro/falha operacional; pulando fase de auditoria. message=%s",
                sync_result.get("message"),
            )
            result = {
                "status": "partial",
                "source": source,
                "sync": sync_result,
                "audit": {"status": "skipped", "message": "Auditoria pulada: erro no pipeline D-1."},
                "baixadas": baixadas,
                "auditadas": 0,
            }
            _update_status(
                current_stage="partial",
                current_message="Ciclo finalizado parcialmente: erro no pipeline D-1.",
                last_run=_now_iso(),
                last_run_source=source,
                last_result=result,
                finished_at=_now_iso(),
            )
            _persist_cycle_update(
                _current_run_id,
                status="partial",
                stage="partial",
                message="Ciclo parcial: erro no pipeline D-1.",
                finished_at=_current_status.get("finished_at"),
                baixadas=baixadas,
                auditadas=0,
                sync_result=sync_result,
                result=result,
            )
            return result

        try:
            classification_result = await _classify_pending_huawei_items(
                _current_run_id,
                cycle_lock=cycle_lock,
            )
            sync_result["classificacao_pendentes"] = classification_result
            _update_status(last_sync=sync_result)
            _persist_cycle_update(_current_run_id, sync_result=sync_result)
            logger.info("Classificacao autonoma dos itens pendentes concluida: %s", classification_result)
        except asyncio.CancelledError:
            raise
        except AutomationLockLostError:
            raise
        except Exception as classification_exc:
            logger.warning("Falha ao rodar classificacao de pendentes: %s", classification_exc)

        audit_result = {"completed": 0}
        if not await asyncio.to_thread(cycle_lock.refresh):
            raise AutomationLockLostError("Lock da automacao perdido antes da auditoria.")
        try:
            _update_status(
                current_stage="auditing",
                current_message="Auditando itens classificados e prontos para IA.",
            )
            _persist_cycle_update(
                _current_run_id,
                stage="auditing",
                message="Auditando itens classificados e prontos para IA.",
            )
            audit_result = await _audit_all_pending_with_progress(
                _current_run_id,
                cycle_lock=cycle_lock,
            )
            _update_status(last_audit=audit_result)
            _persist_cycle_update(_current_run_id, audit_result=audit_result)
        except asyncio.CancelledError:
            raise
        except AutomationLockLostError:
            raise
        except Exception as audit_exc:
            logger.error("Falha na auditoria automatica durante ciclo de automacao: %s", audit_exc)
            audit_result = {"status": "error", "message": str(audit_exc), "completed": 0}
            _update_status(
                last_error=f"Audit Error: {str(audit_exc)}",
                last_audit=audit_result,
            )
            _persist_cycle_update(
                _current_run_id,
                error_message=f"Audit Error: {str(audit_exc)}",
                audit_result=audit_result,
            )

        auditadas = int(audit_result.get("completed", 0) or 0)
        descartados = int(
            audit_result.get("discarded", audit_result.get("descartados", 0)) or 0
        )
        audit_failed = int(audit_result.get("failed", 0) or 0)
        if audit_failed > 0 and not _current_status.get("last_error"):
            _update_status(last_error=f"{audit_failed} item(ns) falharam na auditoria automatica.")
        _current_status["auditadas_total"] += auditadas

        cycle_status = "partial" if _current_status.get("last_error") else "ok"
        zero_download_filters = _summarize_zero_download_filters(sync_result) if baixadas == 0 else ""
        if cycle_status == "ok" and zero_download_filters and auditadas == 0 and descartados == 0:
            completed_message = (
                "Ciclo concluido sem downloads novos; principais filtros: "
                f"{zero_download_filters}."
            )
        elif cycle_status == "ok":
            completed_message = (
                f"Ciclo concluido. Baixadas: {baixadas}; auditadas: {auditadas}; "
                f"descartados: {descartados}."
            )
        else:
            completed_message = "Ciclo terminou com falha parcial. Verifique o detalhe do erro."
        result = {
            "status": cycle_status,
            "source": source,
            "sync": sync_result,
            "audit": audit_result,
            "baixadas": baixadas,
            "auditadas": auditadas,
            "descartados": descartados,
        }

        _update_status(
            current_stage="completed" if cycle_status == "ok" else "error",
            current_message=completed_message,
            last_run=_now_iso(),
            last_run_source=source,
            last_result=result,
            finished_at=_now_iso(),
        )
        _persist_cycle_update(
            _current_run_id,
            status=cycle_status,
            stage="completed" if cycle_status == "ok" else "error",
            message=completed_message,
            finished_at=_current_status.get("finished_at"),
            baixadas=baixadas,
            auditadas=auditadas,
            error_message=_current_status.get("last_error"),
            sync_result=sync_result,
            audit_result=audit_result,
            result=result,
        )

        logger.info("Ciclo concluido. Baixadas: %s, Auditadas: %s", baixadas, auditadas)
        return result
    except asyncio.CancelledError:
        logger.warning("Ciclo de automacao cancelado; persistindo status 'cancelled'.")
        _update_status(
            current_stage="cancelled",
            current_message="Ciclo cancelado manualmente ou por parada do motor.",
            finished_at=_now_iso(),
        )
        _persist_cycle_update(
            _current_run_id,
            status="cancelled",
            stage="cancelled",
            message="Ciclo cancelado manualmente ou por parada do motor.",
            finished_at=_current_status.get("finished_at"),
        )
        raise
    except Exception as exc:
        logger.exception("Erro fatal no run_automation_cycle")
        _update_status(
            current_stage="error",
            current_message="Erro fatal no ciclo de automacao.",
            last_error=f"Fatal Error: {str(exc)}",
            finished_at=_now_iso(),
        )
        _persist_cycle_update(
            _current_run_id,
            status="error",
            stage="error",
            message="Erro fatal no ciclo de automacao.",
            finished_at=_current_status.get("finished_at"),
            error_message=f"Fatal Error: {str(exc)}",
        )
        return {
            "status": "error",
            "message": str(exc),
            "baixadas": 0,
            "auditadas": 0,
        }
    finally:
        _update_status(
            is_running=False,
            is_cycle_running=False,
            finished_at=_current_status.get("finished_at") or _now_iso(),
        )
        _current_run_id = None
        cycle_lock.release()

async def _automation_loop():
    global _current_status
    logger.info("Motor de Automacao Hibrida iniciado.")
    
    while not _stop_event.is_set():
        try:
            if not is_automation_enabled():
                logger.debug("Automacao desligada. Aguardando proximo ciclo.")
            else:
                await run_automation_cycle(source="resident_loop")
                
        except asyncio.CancelledError:
            logger.info("Loop de automacao cancelado.")
            break
        except Exception as exc:
            logger.error(f"Erro no ciclo de automacao: {exc}")
            logger.error(traceback.format_exc())
            _current_status["last_error"] = str(exc)
        
        # Pausa entre os ciclos
        intervalo_segundos = _get_automation_interval_seconds()
        
        try:
            # Espera o stop_event ou o timeout
            await asyncio.wait_for(_stop_event.wait(), timeout=intervalo_segundos)
        except asyncio.TimeoutError:
            # Timeout normal do sleep, o ciclo deve recomecar
            pass

    _current_status["is_running"] = False
    logger.info("Motor de Automacao Hibrida parado.")

def start_engine():
    global _engine_task, _stop_event
    if _engine_task and not _engine_task.done():
        logger.warning("Motor de Automacao ja esta rodando.")
        return
        
    _stop_event = asyncio.Event()
    _engine_task = asyncio.create_task(_automation_loop())

def stop_engine():
    global _stop_event
    if _stop_event:
        _stop_event.set()

def get_engine_status() -> dict:
    status = _current_status.copy()
    resident_loop_running = bool(_engine_task and not _engine_task.done())
    latest_run = _latest_cycle_run()
    latest_run_stale = _latest_run_is_stale(latest_run)
    db_cycle_running = bool(latest_run and latest_run.get("status") == "running" and not latest_run_stale)
    is_paused, is_cancelled = _read_control_flags()

    if latest_run and (db_cycle_running or not status.get("is_cycle_running")):
        latest_audit = _apply_control_flags_to_status_progress(
            latest_run.get("audit_result"),
            latest_run=latest_run,
            is_paused=is_paused,
            is_cancelled=is_cancelled,
        )
        status.update(
            {
                "current_stage": latest_run.get("stage") or status.get("current_stage"),
                "current_message": latest_run.get("message") or status.get("current_message"),
                "current_run_source": latest_run.get("source"),
                "started_at": latest_run.get("started_at"),
                "finished_at": latest_run.get("finished_at"),
                "last_run": latest_run.get("finished_at") or status.get("last_run"),
                "last_run_source": latest_run.get("source") or status.get("last_run_source"),
                "last_error": latest_run.get("error_message"),
                "last_sync": latest_run.get("sync_result"),
                "last_audit": latest_audit,
                "last_result": latest_run.get("result"),
            }
        )

    try:
        conn = database.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT COALESCE(SUM(baixadas), 0), COALESCE(SUM(auditadas), 0) 
                FROM automation_cycle_runs 
                WHERE DATE(started_at) = CURRENT_DATE
            """)
            row = cur.fetchone()
            if row:
                status["baixadas_total"] = int(row[0])
                status["auditadas_total"] = int(row[1])
        finally:
            conn.close()
    except Exception:
        pass

    status["latest_run"] = latest_run
    status["latest_run_is_stale"] = latest_run_stale
    status["is_resident_loop_running"] = resident_loop_running
    status["in_process_engine_enabled"] = is_in_process_engine_enabled()
    status["mode"] = "resident_loop" if status["in_process_engine_enabled"] else "external_cron"
    cycle_running = bool(status.get("is_cycle_running") or db_cycle_running)
    status["is_cycle_running"] = cycle_running
    status["is_running"] = cycle_running
    status["is_enabled"] = is_automation_enabled()
    status["is_paused"] = bool(is_paused and cycle_running)
    status["is_cancelled"] = bool(is_cancelled and cycle_running)
    if status["is_paused"] and status.get("current_stage") == "auditing":
        status["current_stage"] = "paused"
        status["current_message"] = "Automacao pausada pelo usuario."
    if latest_run_stale:
        status["current_stage"] = "stale"
        status["current_message"] = (
            "Ciclo marcado como running, mas o heartbeat parou. "
            "A automacao pode ter travado ou a instancia pode ter sido encerrada."
        )
        status["last_error"] = status["last_error"] or "Automation heartbeat stale."
    status["audit_progress"] = _normalize_local_progress(
        get_automation_status(),
        is_paused=status["is_paused"],
        is_cancelled=status["is_cancelled"],
    )
    status["health_report"] = _build_automation_health_report(status, _load_health_snapshot_cached())
    return status
