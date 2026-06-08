from __future__ import annotations
"""
Background worker for the saved_files sync that follows each audit.

Closes the C3 finding from the code review of 2026-05-10: previously
`_sync_arquivo_salvo_for_audit` was called synchronously inside the audit
batch loop, blocking the entire cycle on `saved_files` contention. Each
iteration of `bulk_update_audits` paid 2-3 round-trips to Postgres in the
hot path of the automation cycle.

Design:
    - Producers enqueue (audit_id, criado_por) and return immediately.
    - A single daemon worker thread drains the queue FIFO and calls the
      original synchronous implementation
      `database._sync_arquivo_salvo_for_audit_inline`.
    - The work is idempotent (UPSERT-like via existing-then-update or save),
      so duplicate enqueues or retries do not corrupt state.
    - On process crash queued items are lost — but the audit row itself
      was already committed, so a periodic backfill can recover them.
    - Under pytest (PYTEST_CURRENT_TEST set) the default is inline mode so
      tests do not race against an asynchronous worker. Operators can also
      force inline mode with AUDIT_SAVED_FILES_ASYNC=false.

The public surface is intentionally minimal:
    enqueue(audit_id, criado_por) — fire-and-forget dispatch
    set_inline_mode(bool | None) — test helpers / runtime override
    flush(timeout)               — best-effort drain (used by tests)
"""


import logging
import os
import queue
import threading
import time

logger = logging.getLogger(__name__)


def _read_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        return default
    return max(1, value)


_QUEUE_MAXSIZE = _read_int_env("AUDIT_SAVED_FILES_QUEUE_MAX", 10_000)

_jobs: "queue.Queue[tuple[int, str] | None]" = queue.Queue(maxsize=_QUEUE_MAXSIZE)
_worker_thread: threading.Thread | None = None
_worker_lock = threading.Lock()
_started = False
_inline_mode_override: bool | None = None


def _is_inline_mode() -> bool:
    if _inline_mode_override is not None:
        return _inline_mode_override
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    flag = os.getenv("AUDIT_SAVED_FILES_ASYNC", "true").strip().lower()
    return flag in {"0", "false", "no", "off"}


def set_inline_mode(inline: bool | None) -> None:
    """Force inline (sync) mode. Pass None to revert to env-driven detection.

    Useful for narrow integration tests that need deterministic timing
    without relying on PYTEST_CURRENT_TEST being set.
    """
    global _inline_mode_override
    _inline_mode_override = inline


def _run_sync(audit_id: int, criado_por: str) -> bool | None:
    # Lazy import to break the database <-> queue circular reference.
    import db.database as database

    return database._sync_arquivo_salvo_for_audit_inline(audit_id, criado_por=criado_por)


def _worker_loop() -> None:
    logger.info("saved-files-sync worker started (queue_max=%s).", _QUEUE_MAXSIZE)
    while True:
        try:
            item = _jobs.get(timeout=30.0)
        except queue.Empty:
            continue
        if item is None:
            _jobs.task_done()
            logger.info("saved-files-sync worker received poison pill; exiting.")
            return
        audit_id, criado_por = item
        try:
            synced = _run_sync(audit_id, criado_por)
            if synced is False:
                logger.warning(
                    "saved-files-sync nao criou/atualizou arquivo salvo "
                    "(audit_id=%s, pending=%s).",
                    audit_id,
                    _jobs.qsize(),
                )
            else:
                logger.info(
                    "saved-files-sync concluiu audit_id=%s (pending=%s).",
                    audit_id,
                    _jobs.qsize(),
                )
        except Exception:
            logger.exception(
                "Falha ao sincronizar arquivo salvo (audit_id=%s).", audit_id
            )
        finally:
            _jobs.task_done()


def _ensure_worker() -> None:
    global _worker_thread, _started
    if _started and _worker_thread and _worker_thread.is_alive():
        return
    with _worker_lock:
        if _started and _worker_thread and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(
            target=_worker_loop,
            name="saved-files-sync",
            daemon=True,
        )
        _worker_thread.start()
        _started = True


def enqueue(audit_id: int, criado_por: str = "") -> None:
    """Dispatch a saved_files sync. Inline under tests, queued in production."""
    if _is_inline_mode():
        synced = _run_sync(audit_id, criado_por)
        if synced is False:
            logger.warning(
                "saved-files-sync inline nao criou/atualizou arquivo salvo "
                "(audit_id=%s).",
                audit_id,
            )
        return
    _ensure_worker()
    try:
        _jobs.put_nowait((audit_id, criado_por))
        logger.info(
            "saved-files-sync enfileirou audit_id=%s (pending=%s).",
            audit_id,
            _jobs.qsize(),
        )
    except queue.Full:
        # Falling back to inline avoids losing the sync. Capacity should
        # rarely exhaust in practice — typical drain rate is sub-50ms per
        # item — but in a degenerate burst we prefer slowness over loss.
        logger.warning(
            "Fila de sincronizacao cheia (max=%s); sincronizando inline audit_id=%s",
            _QUEUE_MAXSIZE,
            audit_id,
        )
        _run_sync(audit_id, criado_por)


def flush(timeout: float = 30.0) -> bool:
    """Block until the queue is drained or timeout elapses.

    Returns True if the queue was fully drained, False on timeout.
    Test-only helper — production code should not need this.
    """
    if not _started:
        return True
    logger.info(
        "saved-files-sync flush iniciado (timeout=%ss, unfinished=%s, pending=%s, worker_alive=%s).",
        timeout,
        _jobs.unfinished_tasks,
        _jobs.qsize(),
        bool(_worker_thread and _worker_thread.is_alive()),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _jobs.unfinished_tasks == 0:
            logger.info("saved-files-sync flush concluido.")
            return True
        time.sleep(0.01)
    drained = _jobs.unfinished_tasks == 0
    if drained:
        logger.info("saved-files-sync flush concluido no limite do timeout.")
    else:
        logger.warning(
            "saved-files-sync flush expirou (unfinished=%s, pending=%s, worker_alive=%s).",
            _jobs.unfinished_tasks,
            _jobs.qsize(),
            bool(_worker_thread and _worker_thread.is_alive()),
        )
    return drained


def queue_size() -> int:
    """Diagnostic helper — current pending job count."""
    return _jobs.qsize()
