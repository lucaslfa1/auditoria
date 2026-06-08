import asyncio
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation as automation
import core.automation_engine as automation_engine


class _FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _control_config_value(key: str, default: str = "") -> str:
    if key == "automacao_is_paused":
        return "true"
    if key == "automacao_is_cancelled":
        return "false"
    return default


class TestAutomationControlState(unittest.TestCase):
    def test_pause_patches_latest_running_cycle_audit_result(self):
        conn = _FakeConnection()

        with patch.object(automation.database, "update_config", return_value=True) as update_config, patch.object(
            automation.database,
            "get_connection",
            return_value=conn,
        ):
            result = automation.pause_automation()

        update_config.assert_called_once_with("automacao_is_paused", "true", alterado_por="system:automation", motivo="pause_automation()", origem="system")
        self.assertIn("Sinal de pausa", result["message"])
        self.assertEqual(conn.commits, 1)
        self.assertTrue(conn.closed)
        query, params = conn.cursor_obj.executed[0]
        self.assertIn("automation_cycle_runs", query)
        self.assertIn("stage = 'auditing'", query)
        payload = json.loads(params[0])
        self.assertEqual(
            payload,
            {"is_running": True, "is_cancelled": False, "is_paused": True},
        )

    def test_engine_status_reflects_db_pause_even_when_local_progress_is_idle(self):
        latest_run = {
            "id": 10,
            "source": "cloud_scheduler",
            "status": "running",
            "stage": "auditing",
            "message": "Auditando itens classificados e prontos para IA.",
            "started_at": "2026-05-08T10:00:00",
            "finished_at": None,
            "last_heartbeat_at": datetime.now().isoformat(),
            "baixadas": 0,
            "auditadas": 0,
            "error_message": None,
            "sync_result": None,
            "audit_result": None,
            "result": None,
        }
        local_progress = {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "current_filename": "",
            "is_running": False,
            "is_cancelled": False,
            "is_paused": False,
            "started_at": None,
            "finished_at": None,
            "errors": [],
        }

        with patch.object(automation_engine, "_latest_cycle_run", return_value=latest_run), patch.object(
            automation_engine,
            "get_automation_status",
            return_value=local_progress,
        ), patch.object(
            automation_engine.database,
            "get_config_value",
            side_effect=_control_config_value,
        ), patch.object(
            automation_engine,
            "is_automation_enabled",
            return_value=True,
        ):
            status = automation_engine.get_engine_status()

        self.assertTrue(status["is_running"])
        self.assertTrue(status["is_paused"])
        self.assertEqual(status["current_stage"], "paused")
        self.assertEqual(status["current_message"], "Automacao pausada pelo usuario.")
        self.assertEqual(status["last_audit"]["is_running"], True)
        self.assertEqual(status["last_audit"]["is_paused"], True)
        self.assertEqual(status["audit_progress"]["is_paused"], False)

    def test_engine_status_marks_running_cycle_stale_when_heartbeat_stops(self):
        latest_run = {
            "id": 11,
            "source": "cloud_scheduler",
            "status": "running",
            "stage": "auditing",
            "message": "Auditando itens classificados e prontos para IA.",
            "started_at": (datetime.now() - timedelta(minutes=20)).isoformat(),
            "finished_at": None,
            "last_heartbeat_at": (datetime.now() - timedelta(minutes=20)).isoformat(),
            "baixadas": 0,
            "auditadas": 0,
            "error_message": None,
            "sync_result": None,
            "audit_result": {"is_running": True},
            "result": None,
        }

        with patch.object(automation_engine, "_latest_cycle_run", return_value=latest_run), patch.object(
            automation_engine,
            "get_automation_status",
            return_value={"is_running": False, "is_paused": False, "is_cancelled": False},
        ), patch.object(
            automation_engine.database,
            "get_config_value",
            return_value="false",
        ), patch.object(
            automation_engine,
            "is_automation_enabled",
            return_value=True,
        ):
            status = automation_engine.get_engine_status()

        self.assertFalse(status["is_running"])
        self.assertTrue(status["latest_run_is_stale"])
        self.assertEqual(status["current_stage"], "stale")

    def test_engine_status_does_not_report_cycle_running_while_resident_loop_sleeps(self):
        class ResidentTask:
            def done(self):
                return False

        idle_status = {
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

        with patch.object(automation_engine, "_current_status", idle_status), patch.object(
            automation_engine,
            "_engine_task",
            ResidentTask(),
        ), patch.object(
            automation_engine,
            "_latest_cycle_run",
            return_value=None,
        ), patch.object(
            automation_engine.database,
            "get_config_value",
            return_value="false",
        ), patch.object(
            automation_engine,
            "get_automation_status",
            return_value={"is_running": False, "is_paused": False, "is_cancelled": False},
        ), patch.object(
            automation_engine,
            "is_automation_enabled",
            return_value=True,
        ):
            status = automation_engine.get_engine_status()

        self.assertTrue(status["is_resident_loop_running"])
        self.assertFalse(status["is_cycle_running"])
        self.assertFalse(status["is_running"])

    def test_run_automation_cycle_skips_when_distributed_lock_is_busy(self):
        class BusyLock:
            def acquire(self):
                return False

            def release(self):
                raise AssertionError("release should not be called when lock was not acquired")

        with patch.object(automation_engine, "is_automation_enabled", return_value=True), patch.object(
            automation_engine,
            "_AutomationCycleLock",
            return_value=BusyLock(),
        ), patch.object(automation_engine, "_create_cycle_run") as create_cycle:
            result = asyncio.run(automation_engine.run_automation_cycle(source="resident_loop"))

        self.assertEqual(result["status"], "skipped")
        create_cycle.assert_not_called()

    def test_await_with_lock_refresh_updates_cycle_heartbeat(self):
        class Lock:
            def __init__(self):
                self.refreshes = 0

            def refresh(self):
                self.refreshes += 1
                return True

        async def delayed_result():
            await asyncio.sleep(0.03)
            return "ok"

        lock = Lock()
        with patch.object(automation_engine, "_persist_cycle_update") as persist_update:
            result = asyncio.run(
                automation_engine._await_with_lock_refresh(
                    delayed_result(),
                    lock,
                    interval_seconds=0.01,
                    run_id=33,
                )
            )

        self.assertEqual(result, "ok")
        self.assertGreaterEqual(lock.refreshes, 1)
        persist_update.assert_called_with(33)

    def test_run_automation_cycle_cancels_before_audit_when_cancel_flag_is_set(self):
        class Lock:
            acquired = False

            def acquire(self):
                self.acquired = True
                return True

            def refresh(self):
                return True

            def release(self):
                self.acquired = False

        def fake_config(key: str, default: str = "") -> str:
            if key == "automacao_is_cancelled":
                return "true"
            if key == "automacao_is_paused":
                return "false"
            return default

        with patch.object(automation_engine, "is_automation_enabled", return_value=True), patch.object(
            automation_engine,
            "_reconcile_stale_running_cycles",
        ), patch.object(
            automation_engine,
            "_AutomationCycleLock",
            return_value=Lock(),
        ), patch.object(
            automation_engine,
            "_create_cycle_run",
            return_value=77,
        ), patch.object(
            automation_engine,
            "_persist_cycle_update",
        ) as persist_update, patch.object(
            automation_engine.database,
            "update_config",
            return_value=True,
        ), patch.object(
            automation_engine.database,
            "get_config_value",
            side_effect=fake_config,
        ), patch.object(
            automation_engine,
            "_audit_all_pending_with_progress",
            new_callable=AsyncMock,
        ) as audit_all:
            result = asyncio.run(automation_engine.run_automation_cycle(source="cloud_scheduler"))

        self.assertEqual(result["status"], "cancelled")
        audit_all.assert_not_awaited()
        self.assertTrue(any(call.kwargs.get("status") == "cancelled" for call in persist_update.call_args_list))

    def test_invalid_automation_interval_falls_back_to_default(self):
        with patch.object(
            automation_engine.database,
            "get_config_value",
            return_value="not-a-number",
        ):
            self.assertEqual(automation_engine._get_automation_interval_seconds(), 600)

    def test_health_report_marks_stale_cycle_as_critical(self):
        status = {
            "is_enabled": True,
            "is_running": False,
            "is_cycle_running": False,
            "is_paused": False,
            "latest_run_is_stale": True,
            "current_stage": "stale",
            "last_error": None,
            "auditadas_total": 0,
            "baixadas_total": 0,
            "audit_progress": {},
        }
        snapshot = automation_engine._empty_health_snapshot()
        snapshot["available"] = True

        report = automation_engine._build_automation_health_report(status, snapshot)

        self.assertEqual(report["status"], "critical")
        self.assertEqual(report["indicators"][0]["value"], "Sem progresso")
        self.assertIn("stale-cycle", {alert["id"] for alert in report["alerts"]})

    def test_health_report_summarizes_queue_and_direction_alerts(self):
        status = {
            "is_enabled": True,
            "is_running": False,
            "is_cycle_running": False,
            "is_paused": False,
            "latest_run_is_stale": False,
            "current_stage": "idle",
            "last_error": None,
            "auditadas_total": 4,
            "baixadas_total": 7,
            "audit_progress": {},
        }
        snapshot = automation_engine._empty_health_snapshot()
        snapshot.update(
            {
                "available": True,
                "queue_by_status": {
                    "auto_resolved": 3,
                    "reviewed": 2,
                    "pending": 8,
                    "needs_manual_triage": 1,
                    "monthly_capped": 2,
                },
                "sync_status_24h": {"success": 10, "failed": 1},
                "sync_failure_reasons_24h": {"direcao_desconhecida": 55},
                "cycle_status_24h": {"ok": 1},
                "cycle_totals_24h": {"runs": 1, "baixadas": 7, "auditadas": 4},
            }
        )

        report = automation_engine._build_automation_health_report(status, snapshot)

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["metrics"]["ready_queue"], 5)
        self.assertEqual(report["metrics"]["manual_queue"], 9)
        self.assertEqual(report["metrics"]["direction_blocks_24h"], 55)
        self.assertIn("direction-blocks", {alert["id"] for alert in report["alerts"]})

    def test_audit_all_pending_uses_configured_monthly_quota(self):
        item = {
            "input_hash": "queue-hash",
            "nome_arquivo": "call.wav",
            "operador_previsto": "Operador Teste",
            "setor_previsto": "logistica",
            "alerta_previsto": "ENTREGA",
            "status": "auto_resolved",
            "metadata": {},
        }

        def fake_get_config(key: str, default: str = "") -> str:
            if key == "huawei_cota_max_por_operador_mes":
                return "3"
            return "false"

        with patch.object(
            automation.database,
            "listar_fila_revisao_classificacao",
            return_value=[item],
        ), patch.object(
            automation.database,
            "update_config",
            return_value=True,
        ), patch.object(
            automation.database,
            "get_config_value",
            side_effect=fake_get_config,
        ), patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador Teste", "matricula": "123"},
        ), patch(
            "repositories.audits.get_operator_audit_count_for_month",
            return_value=2,
        ), patch.object(
            automation,
            "_audit_single_item",
            new_callable=AsyncMock,
            return_value={"status": "audited"},
        ) as audit_single, patch.object(
            automation.database,
            "atualizar_status_fila_revisao_classificacao",
        ) as update_status, patch.object(
            automation.asyncio,
            "sleep",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(automation.audit_all_pending())

        self.assertEqual(result["completed"], 1)
        audit_single.assert_awaited_once_with(item)
        update_status.assert_not_called()

    def test_audit_all_pending_reaches_configured_target_with_operational_batches(self):
        items = [
            {
                "input_hash": f"queue-hash-{idx}",
                "nome_arquivo": f"call-{idx}.wav",
                "operador_previsto": "Operador Teste",
                "setor_previsto": "logistica",
                "alerta_previsto": "ENTREGA",
                "status": "auto_resolved",
                "metadata": {},
            }
            for idx in range(75)
        ]
        page_start = 0

        def list_ready_items(*, limit, status):
            nonlocal page_start
            chunk = items[page_start:page_start + limit]
            page_start += len(chunk)
            return chunk

        with patch.dict(
            os.environ,
            {
                "AUTOMATION_AUDIT_TARGET_COUNT": "75",
                "AUTOMATION_AUDIT_TIME_BUDGET_SECONDS": "1500",
                "AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS": "300",
            },
            clear=False,
        ), patch.object(
            automation.database,
            "listar_fila_revisao_classificacao",
            side_effect=list_ready_items,
        ) as list_queue, patch.object(
            automation.database,
            "update_config",
            return_value=True,
        ), patch.object(
            automation.database,
            "get_config_value",
            return_value="false",
        ), patch.object(
            automation,
            "_audit_single_item",
            new_callable=AsyncMock,
            return_value={"status": "audited"},
        ) as audit_single, patch.object(
            automation.asyncio,
            "sleep",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(automation.audit_all_pending())

        self.assertEqual(list_queue.call_count, 15)
        self.assertTrue(all(call.kwargs["limit"] == 5 for call in list_queue.call_args_list))
        self.assertEqual(audit_single.await_count, 75)
        self.assertEqual(result["target_count"], 75)
        self.assertEqual(result["requested_audits"], 75)
        self.assertEqual(result["batch_size"], 5)
        self.assertEqual(result["operational_batch_size"], 5)
        self.assertEqual(result["total"], 75)

    def test_audit_all_pending_stops_when_time_budget_is_exhausted(self):
        items = [
            {
                "input_hash": f"queue-hash-{idx}",
                "nome_arquivo": f"call-{idx}.wav",
                "operador_previsto": "Operador Teste",
                "setor_previsto": "logistica",
                "alerta_previsto": "ENTREGA",
                "status": "auto_resolved",
                "metadata": {},
            }
            for idx in range(2)
        ]
        monotonic_values = iter([100.0, 100.0, 101.0, 102.0, 581.0])

        def fake_monotonic():
            try:
                return next(monotonic_values)
            except StopIteration:
                return 581.0

        with patch.object(
            automation.database,
            "listar_fila_revisao_classificacao",
            return_value=items,
        ), patch.object(
            automation.database,
            "update_config",
            return_value=True,
        ), patch.object(
            automation.database,
            "get_config_value",
            return_value="false",
        ), patch.object(
            automation,
            "_audit_single_item_with_timeout",
            new_callable=AsyncMock,
            return_value={"status": "audited"},
        ) as audit_single, patch.object(
            automation.time,
            "monotonic",
            side_effect=fake_monotonic,
        ), patch.object(
            automation.asyncio,
            "sleep",
            new_callable=AsyncMock,
        ):
            result = asyncio.run(
                automation.audit_all_pending(max_items=2, time_budget_seconds=480)
            )

        audit_single.assert_awaited_once()
        self.assertTrue(result["time_budget_exhausted"])
        self.assertEqual(result["completed"], 1)


if __name__ == "__main__":
    unittest.main()
