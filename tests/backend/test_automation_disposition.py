"""Camada central de disposicao da esteira de automacao (core/automation_disposition.py).

execute_discard centraliza o descarte: qualquer descarte vira tombstone
permanente. transient_retry_state decide retry vs esgotamento.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.automation_disposition import Disposition, execute_discard, transient_retry_state


class TestTransientRetryState(unittest.TestCase):
    def test_primeira_falha_retenta(self):
        with patch.dict(os.environ, {"AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"}, clear=False):
            should_retry, nxt = transient_retry_state({"automation_transient_retries": 0})
        self.assertTrue(should_retry)
        self.assertEqual(nxt, 1)

    def test_esgota_no_limite(self):
        with patch.dict(os.environ, {"AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"}, clear=False):
            should_retry, nxt = transient_retry_state({"automation_transient_retries": 2})
        self.assertFalse(should_retry)
        self.assertEqual(nxt, 3)

    def test_metadata_invalida_trata_como_zero(self):
        with patch.dict(os.environ, {"AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"}, clear=False):
            should_retry, nxt = transient_retry_state(None)
        self.assertTrue(should_retry)
        self.assertEqual(nxt, 1)


class TestExecuteDiscard(unittest.TestCase):
    def _patch_db(self, result=None):
        from db import database
        return patch.object(
            database,
            "descartar_item_automacao",
            return_value=result or {"discarded": True, "tombstone": "discarded_permanent", "attempts": 1},
        )

    def test_impossible_usa_tombstone_true(self):
        with self._patch_db() as mock_disc:
            out = execute_discard(
                {"confianca": 0.5},
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="transcricao_impossivel",
                status_result="discarded_impossible_transcription",
                queue_input_hash="h1",
                filename="c.wav",
                metadata={"huawei_call_id": "C-1"},
            )
        self.assertEqual(out["status"], "discarded_impossible_transcription")
        self.assertTrue(mock_disc.call_args.kwargs["tombstone"])
        self.assertEqual(mock_disc.call_args.args[0], "h1")
        self.assertEqual(mock_disc.call_args.kwargs["motivo"], "transcricao_impossivel")

    def test_recoverable_legado_tambem_usa_tombstone_true(self):
        with self._patch_db() as mock_disc:
            out = execute_discard(
                {},
                Disposition.DISCARD_RECOVERABLE,
                motivo="triagem_sem_alerta_confiavel",
                status_result="discarded_unknown_alert",
                queue_input_hash="h2",
                filename="c.wav",
            )
        self.assertEqual(out["status"], "discarded_unknown_alert")
        self.assertTrue(mock_disc.call_args.kwargs["tombstone"])

    def test_loop_limit_vem_da_env(self):
        with self._patch_db() as mock_disc, patch.dict(
            os.environ, {"AUTOMATION_DISCARD_LOOP_LIMIT": "5"}, clear=False
        ):
            execute_discard({}, Disposition.DISCARD_RECOVERABLE, motivo="m", status_result="discarded_x", queue_input_hash="h3")
        self.assertEqual(mock_disc.call_args.kwargs["loop_limit"], 5)

    def test_status_result_deve_comecar_com_discarded(self):
        # convencao: a telemetria do lote soma por startswith("discarded")
        with self._patch_db():
            out = execute_discard({}, Disposition.DISCARD_RECOVERABLE, motivo="m", status_result="discarded_operator", queue_input_hash="h")
        self.assertTrue(out["status"].startswith("discarded"))

    def test_proceed_e_retry_sao_invalidos(self):
        for d in (Disposition.PROCEED, Disposition.RETRY):
            with self.assertRaises(ValueError):
                execute_discard({}, d, motivo="m", status_result="discarded_x", queue_input_hash="h")


if __name__ == "__main__":
    unittest.main()
