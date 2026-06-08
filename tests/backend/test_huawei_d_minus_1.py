import os
import sys
import unittest
from datetime import datetime, timedelta, time as dt_time, timezone
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import huawei_d_minus_1 as d1


class TestHuaweiDMinus1(unittest.IsolatedAsyncioTestCase):
    def test_max_retries_exhaustion_precedes_retry_interval(self):
        now_sp = datetime(2026, 5, 7, 10, 0, tzinfo=d1.SP_TZ)
        run = {
            "status": "error",
            "attempts": 4,
            "last_attempt_at": now_sp - timedelta(minutes=5),
        }

        should_run, reason = d1._deve_executar(
            run,
            now_sp=now_sp,
            horario_execucao=dt_time(6, 0),
            max_retries=4,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
        )

        self.assertFalse(should_run)
        self.assertEqual(reason, "tentativas_esgotadas")

    def test_force_bypasses_tentativas_esgotadas(self):
        now_sp = datetime(2026, 5, 7, 10, 0, tzinfo=d1.SP_TZ)
        run = {
            "status": "error",
            "attempts": 4,
            "last_attempt_at": now_sp - timedelta(minutes=5),
        }

        should_run, reason = d1._deve_executar(
            run,
            now_sp=now_sp,
            horario_execucao=dt_time(6, 0),
            max_retries=4,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=True,
        )

        self.assertTrue(should_run)
        self.assertEqual(reason, "ok")

    def test_force_bypasses_antes_do_horario_programado(self):
        # Hora atual 05:30, horario programado 06:00 — antes do horário.
        now_sp = datetime(2026, 5, 7, 5, 30, tzinfo=d1.SP_TZ)

        should_run, reason = d1._deve_executar(
            None,
            now_sp=now_sp,
            horario_execucao=dt_time(6, 0),
            max_retries=4,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=True,
        )

        self.assertTrue(should_run)
        self.assertEqual(reason, "ok")

    def test_force_reexecuta_ja_concluido(self):
        # Desde e3fb7ef (2026-05-27, a pedido do usuario), force=True re-executa
        # dias 'completed' para buscar arquivos que tenham subido tarde no OBS.
        now_sp = datetime(2026, 5, 7, 10, 0, tzinfo=d1.SP_TZ)
        run = {"status": "completed", "attempts": 1}

        should_run, reason = d1._deve_executar(
            run,
            now_sp=now_sp,
            horario_execucao=dt_time(6, 0),
            max_retries=4,
            retry_intervalo=timedelta(hours=1),
            is_today_d1=True,
            force=True,
        )

        self.assertTrue(should_run)
        self.assertEqual(reason, "ok")

    def test_last_attempt_sp_accepts_timestamptz_values(self):
        run = {"last_attempt_at": datetime(2026, 5, 7, 13, 0, tzinfo=timezone.utc)}

        result = d1._last_attempt_sp(run)

        self.assertIsNotNone(result)
        self.assertEqual(result.tzinfo, d1.SP_TZ)
        self.assertEqual(result.hour, 10)

    async def test_retry_exhausted_notification_logs_once_without_webhook(self):
        with patch.object(d1.HuaweiDMinus1Tracker, "mark_retry_exhausted_alerted", return_value=True):
            with patch.object(d1, "_get_failure_webhook_url", return_value=""):
                with patch.object(d1.logger, "critical") as critical:
                    sent = await d1.HuaweiDMinus1Tracker.notify_retry_exhausted(
                        "20260506",
                        attempts=4,
                        last_error="obs_manifest_empty",
                    )

        self.assertTrue(sent)
        critical.assert_called_once()
        self.assertIn("06/05/2026", critical.call_args.args[1])
        self.assertIn("4 tentativas", critical.call_args.args[1])

    async def test_retry_exhausted_notification_is_idempotent(self):
        with patch.object(d1.HuaweiDMinus1Tracker, "mark_retry_exhausted_alerted", return_value=False):
            with patch.object(d1.logger, "critical") as critical:
                sent = await d1.HuaweiDMinus1Tracker.notify_retry_exhausted(
                    "20260506",
                    attempts=4,
                )

        self.assertFalse(sent)
        critical.assert_not_called()

    async def test_pipeline_reports_partial_when_inner_date_is_partial(self):
        progress_callback = lambda stage, current, total: None
        with patch.object(
            d1,
            "get_pipeline_config",
            return_value={
                "huawei_d1_enabled": "true",
                "huawei_d1_horario_execucao": "06:00",
                "huawei_d1_max_retries": "4",
                "huawei_d1_retry_intervalo_minutos": "60",
                "huawei_d1_lookback_dias": "1",
                "huawei_cota_max_por_operador_mes": "2",
                "huawei_d1_limite_ligacoes": "20",
            },
        ), patch.object(
            d1.HuaweiDMinus1Tracker,
            "get_run",
            return_value=None,
        ), patch.object(
            d1,
            "_deve_executar",
            return_value=(True, "ok"),
        ), patch.object(
            d1,
            "executar_d_minus_1",
            return_value={"status": "partial", "date_str": "20260518"},
        ) as execute_day, patch.object(
            d1,
            "_cleanup_d_minus_1_history",
            return_value=0,
        ):
            result = await d1.executar_d_minus_1_pipeline(progress_callback=progress_callback)

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["executados"][0]["status"], "partial")
        self.assertIs(execute_day.await_args.kwargs["progress_callback"], progress_callback)

    async def test_pipeline_stops_when_cancel_requested(self):
        with patch.object(
            d1,
            "get_pipeline_config",
            return_value={
                "huawei_d1_enabled": "true",
                "huawei_d1_horario_execucao": "06:00",
                "huawei_d1_max_retries": "4",
                "huawei_d1_retry_intervalo_minutos": "60",
                "huawei_d1_lookback_dias": "2",
                "huawei_cota_max_por_operador_mes": "2",
                "huawei_d1_limite_ligacoes": "20",
            },
        ), patch.object(
            d1,
            "executar_d_minus_1",
        ) as execute_day:
            result = await d1.executar_d_minus_1_pipeline(should_cancel=lambda: True)

        self.assertEqual(result["status"], "cancelled")
        execute_day.assert_not_called()


if __name__ == "__main__":
    unittest.main()
