import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers import automation as automation_router
import core.automation_engine as automation_engine


class _FakeCursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class _Request:
    def __init__(self, token="secret"):
        self.headers = {"Authorization": f"Bearer {token}"}


class _FakeCycleLock:
    def __init__(self):
        self.released = False

    def acquire(self):
        return True

    def refresh(self):
        return True

    def release(self):
        self.released = True


class TestAutomationCron(unittest.TestCase):
    def tearDown(self):
        automation_router._manual_cycle_task = None

    def test_cron_token_is_required(self):
        with patch.dict(os.environ, {"CRON_SECRET_TOKEN": "secret"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                automation_router._require_cron_token(_Request(token="wrong"))

        self.assertEqual(raised.exception.status_code, 403)

    def test_table_lock_acquires_and_releases_owner_token(self):
        cursor = _FakeCursor({"chave": "automation_engine_lock"})
        conn = _FakeConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            lock = automation_engine._AutomationCycleLock()
            self.assertTrue(lock.acquire())
            lock.release()

        self.assertTrue(conn.closed)
        self.assertEqual(conn.commits, 2)
        self.assertIn("INSERT INTO configuracoes", cursor.executed[0][0])
        self.assertIn("UPDATE configuracoes", cursor.executed[1][0])
        self.assertIn("UPDATE configuracoes", cursor.executed[2][0])
        self.assertIn("valor = %s", cursor.executed[1][0])
        self.assertIn("AND valor = %s", cursor.executed[2][0])
        self.assertEqual(cursor.executed[1][1][0], cursor.executed[2][1][1])

    def test_table_lock_context_manager_releases_on_exception(self):
        """C4 regression: context manager must release the lock even when the
        body raises (covers asyncio.CancelledError and synchronous exceptions
        between acquisition and the first await point)."""
        cursor = _FakeCursor({"chave": "automation_engine_lock"})
        conn = _FakeConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            try:
                with automation_engine._AutomationCycleLock() as lock:
                    self.assertTrue(lock.acquired)
                    raise RuntimeError("simulated mid-cycle failure")
            except RuntimeError:
                pass

        self.assertTrue(conn.closed, "connection must be closed via __exit__")
        self.assertEqual(conn.commits, 2, "lock + unlock each commit once")
        self.assertIn("UPDATE configuracoes", cursor.executed[2][0])

    def test_table_lock_closes_connection_when_busy(self):
        cursor = _FakeCursor(None)  # None returned when RETURNING chave returns nothing
        conn = _FakeConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            lock = automation_engine._AutomationCycleLock()
            self.assertFalse(lock.acquire())

        self.assertTrue(conn.closed)
        self.assertEqual(conn.commits, 1)
        self.assertEqual(len(cursor.executed), 2)

    def test_reconcile_stale_cycle_releases_auxiliary_locks(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        cursor = _FakeCursor(rows=[(123, old, old)])
        conn = _FakeConnection(cursor)

        with patch.dict(os.environ, {"AUTOMATION_HEARTBEAT_STALE_SECONDS": "300"}, clear=False):
            with patch.object(automation_engine.database, "get_connection", return_value=conn):
                automation_engine._reconcile_stale_running_cycles()

        self.assertEqual(conn.commits, 1)
        self.assertTrue(conn.closed)
        self.assertIn("UPDATE automation_cycle_runs", cursor.executed[1][0])
        self.assertIn("UPDATE configuracoes", cursor.executed[2][0])
        self.assertIn("huawei_d1_run_lock", cursor.executed[2][0])
        self.assertEqual(cursor.executed[2][1], (300,))

    def test_cron_run_skips_when_automation_is_disabled(self):
        with patch.dict(os.environ, {"CRON_SECRET_TOKEN": "secret"}, clear=False), patch(
            "core.automation_engine.is_automation_enabled",
            return_value=False,
        ):
            result = asyncio.run(automation_router.cron_run_automation_cycle(_Request()))

        self.assertEqual(result["status"], "disabled")

    def test_cron_run_uses_lock_and_runs_single_cycle(self):
        run_cycle = AsyncMock(return_value={"status": "ok", "auditadas": 1})

        with patch.dict(os.environ, {"CRON_SECRET_TOKEN": "secret"}, clear=False), patch(
            "core.automation_engine.is_automation_enabled",
            return_value=True,
        ), patch("core.automation_engine.run_automation_cycle", run_cycle):
            result = asyncio.run(automation_router.cron_run_automation_cycle(_Request()))

        self.assertEqual(result["status"], "ok")
        run_cycle.assert_awaited_once_with(source="cloud_scheduler")

    def test_cron_run_skips_when_lock_is_busy(self):
        with patch.dict(os.environ, {"CRON_SECRET_TOKEN": "secret"}, clear=False), patch(
            "core.automation_engine.is_automation_enabled",
            return_value=True,
        ), patch(
            "core.automation_engine.run_automation_cycle",
            AsyncMock(return_value={"status": "skipped", "message": "Automacao ja esta em andamento."}),
        ):
            result = asyncio.run(automation_router.cron_run_automation_cycle(_Request()))

        self.assertEqual(result["status"], "skipped")

    def test_run_now_waits_for_single_cycle(self):
        run_cycle = AsyncMock(return_value={"status": "ok", "auditadas": 2})

        async def invoke():
            result = await automation_router.run_automation_cycle_now(_user={})
            await asyncio.sleep(0)
            return result

        with patch(
            "core.automation_engine.is_automation_enabled",
            return_value=True,
        ), patch(
            "core.automation_engine.get_engine_status",
            return_value={"is_running": False},
        ), patch("core.automation_engine.run_automation_cycle", run_cycle):
            result = asyncio.run(invoke())

        self.assertEqual(result["status"], "ok")
        run_cycle.assert_awaited_once_with(source="manual_ui")

    def test_run_now_skips_when_engine_is_already_running(self):
        run_cycle = AsyncMock(return_value={"status": "ok", "auditadas": 2})

        with patch(
            "core.automation_engine.is_automation_enabled",
            return_value=True,
        ), patch(
            "core.automation_engine.get_engine_status",
            return_value={"is_running": True},
        ), patch("core.automation_engine.run_automation_cycle", run_cycle):
            result = asyncio.run(automation_router.run_automation_cycle_now(_user={}))

        self.assertEqual(result["status"], "skipped")
        run_cycle.assert_not_called()

    def test_cycle_classifies_pending_huawei_items_before_audit(self):
        classify_pending = AsyncMock(return_value={"classificadas": 5, "erros": 0, "pendentes_restantes": 0})
        audit_pending = AsyncMock(return_value={"completed": 0, "discarded": 0, "failed": 0})
        sync_d1 = AsyncMock(return_value={"status": "ok", "executados": []})

        with patch("core.automation_engine.is_automation_enabled", return_value=True), patch(
            "core.automation_engine._reconcile_stale_running_cycles",
        ), patch(
            "core.automation_engine._AutomationCycleLock",
            _FakeCycleLock,
        ), patch(
            "core.automation_engine._create_cycle_run",
            return_value=123,
        ), patch(
            "core.automation_engine._reset_cycle_control_flags",
        ), patch(
            "core.automation_engine._automation_cancel_requested",
            return_value=False,
        ), patch(
            "core.automation_engine._persist_cycle_update",
        ), patch(
            "core.automation_engine.database.limpar_fila_revisao_classificacao_antiga",
            return_value={"deleted": 0},
            create=True,
        ), patch(
            "core.automation_engine.executar_d_minus_1_pipeline",
            sync_d1,
        ), patch(
            "core.automation_engine._classify_pending_huawei_items",
            classify_pending,
        ), patch(
            "core.automation_engine._audit_all_pending_with_progress",
            audit_pending,
        ):
            result = asyncio.run(automation_engine.run_automation_cycle(source="cloud_scheduler"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["sync"]["classificacao_pendentes"]["classificadas"], 5)
        classify_pending.assert_awaited_once()
        audit_pending.assert_awaited_once()


class TestAtomicAutomationToggle(unittest.TestCase):
    """Regression coverage for the atomic toggle (C2 from the code review).

    Prior to the fix the frontend issued separate writes and a partial failure
    left the engine and D-1 flags out of sync. The new
    `set_automation_enabled_atomic` writes all gates in one transaction.
    (O terceiro gate, telefonia_cron_sync_ativa, foi removido em 2026-06-12.)
    """

    def test_atomic_toggle_writes_both_keys_in_single_transaction(self):
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            automation_engine.set_automation_enabled_atomic(True)

        config_inserts = [
            params for query, params in cursor.executed
            if "INSERT INTO configuracoes " in query
        ]

        self.assertEqual(len(config_inserts), 2, "expected exactly two upserts into configuracoes")
        keys_written = [params[0] for params in config_inserts]
        self.assertEqual(
            keys_written,
            ["automacao_hibrida_ativa", "huawei_d1_enabled"],
        )
        values_written = {params[0]: params[1] for params in config_inserts}
        self.assertEqual(values_written["automacao_hibrida_ativa"], "true")
        self.assertEqual(values_written["huawei_d1_enabled"], "true")
        self.assertEqual(conn.commits, 1, "single transaction => single commit")
        self.assertTrue(conn.closed)

    def test_atomic_toggle_disabled_flag_is_string_false(self):
        cursor = _FakeCursor()
        conn = _FakeConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            automation_engine.set_automation_enabled_atomic(False)

        config_inserts = [
            params for query, params in cursor.executed
            if "INSERT INTO configuracoes " in query
        ]
        values = {params[0]: params[1] for params in config_inserts}
        self.assertEqual(values["automacao_hibrida_ativa"], "false")
        self.assertEqual(values["huawei_d1_enabled"], "false")

    def test_atomic_toggle_rolls_back_on_failure(self):
        class _BoomCursor(_FakeCursor):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def execute(self, query, params=None):
                self.calls += 1
                self.executed.append((query, params))
                if self.calls == 2:
                    raise RuntimeError("simulated DB failure on second upsert")

        class _RollbackConnection(_FakeConnection):
            def __init__(self, cursor):
                super().__init__(cursor)
                self.rollbacks = 0

            def rollback(self):
                self.rollbacks += 1

        cursor = _BoomCursor()
        conn = _RollbackConnection(cursor)

        with patch.object(automation_engine.database, "get_connection", return_value=conn):
            with self.assertRaises(RuntimeError):
                automation_engine.set_automation_enabled_atomic(True)

        self.assertEqual(conn.commits, 0, "must not commit on failure")
        self.assertEqual(conn.rollbacks, 1, "must rollback on failure")
        self.assertTrue(conn.closed, "connection must be closed on failure")


if __name__ == "__main__":
    unittest.main()
