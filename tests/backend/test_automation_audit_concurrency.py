"""Paralelização da fase de auditoria (`audit_all_pending`).

Prova que, com `AUTOMATION_AUDIT_CONCURRENCY>1`, vários itens são auditados em
paralelo (pico de itens em voo == concorrência), que `1` mantém o comportamento
serial legado e que o cap de meta é respeitado. Testes de mocks puros — não
tocam o banco, a IA nem a rede.
"""
import asyncio
import os
import unittest
from unittest.mock import patch

import core.automation as automation
from core.automation_config import _get_automation_audit_concurrency


def _make_items(n: int) -> list[dict]:
    return [
        {"input_hash": f"h{i}", "nome_arquivo": f"call_{i}.wav", "metadata": {}}
        for i in range(n)
    ]


class _ConcurrencyTracker:
    """Conta itens em voo e registra o pico observado."""

    def __init__(self, dwell: float = 0.03) -> None:
        self.dwell = dwell
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    async def __call__(self, item, *, timeout_seconds=None):
        self.calls += 1
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.dwell)
            return {"status": "audited"}
        finally:
            self.in_flight -= 1


def _run_audit(tracker, *, max_items: int, available: int):
    """Roda audit_all_pending com a fila mockada (`available` itens, depois vazia)."""
    automation._progress = automation.AutomationProgress()

    # Pool consumível: cada fetch entrega até `limit` itens e os REMOVE da fila
    # (no runtime os itens auditados saem de `ready_for_audit`), como o banco faz.
    pool = _make_items(available)

    def _fake_listar(limit, status):
        taken = pool[:limit]
        del pool[:limit]
        return taken

    with patch.object(automation.database, "listar_fila_revisao_classificacao", side_effect=_fake_listar), \
         patch.object(automation.AutomationGatekeeper, "check_eligibility", return_value=None), \
         patch.object(automation, "_audit_single_item_with_timeout", new=tracker), \
         patch.object(automation.cost_guard, "budget_exceeded", return_value=None), \
         patch.object(automation.cost_guard, "record_audit_completed", return_value=None), \
         patch.object(automation, "_config_flag", return_value=False), \
         patch("core.saved_files_sync_queue.flush", return_value=True), \
         patch("core.saved_files_sync_queue.queue_size", return_value=0):
        return asyncio.run(
            automation.audit_all_pending(
                reset_control_flags=False,
                max_items=max_items,
                time_budget_seconds=300,
            )
        )


class TestAuditConcurrencyParallel(unittest.TestCase):
    def setUp(self):
        # env > db: evita qualquer leitura de config no banco durante o teste.
        self._env = patch.dict(
            os.environ,
            {
                "AUTOMATION_ITEM_TIMEOUT_SECONDS": "120",
                "AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS": "30",
            },
            clear=False,
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_runs_in_parallel_up_to_concurrency(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "5"}, clear=False):
            tracker = _ConcurrencyTracker()
            _run_audit(tracker, max_items=12, available=12)
        self.assertEqual(tracker.calls, 12)
        self.assertEqual(tracker.peak, 5, "esperado pico de 5 itens em voo")
        self.assertEqual(automation._progress.completed, 12)

    def test_concurrency_one_is_serial(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "1"}, clear=False):
            tracker = _ConcurrencyTracker()
            _run_audit(tracker, max_items=8, available=8)
        self.assertEqual(tracker.peak, 1, "concorrência=1 deve permanecer serial")
        self.assertEqual(automation._progress.completed, 8)

    def test_respects_target_cap(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "5"}, clear=False):
            tracker = _ConcurrencyTracker()
            _run_audit(tracker, max_items=4, available=20)
        # Nunca audita mais que a meta, mesmo com 20 itens disponíveis e pool de 5.
        self.assertEqual(tracker.calls, 4)
        self.assertEqual(automation._progress.completed, 4)
        self.assertLessEqual(tracker.peak, 4)


class TestAuditConcurrencyConfig(unittest.TestCase):
    def test_env_wins(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "3"}, clear=False):
            with patch("core.automation_config.database.get_config_value", return_value="9") as mock_db:
                self.assertEqual(_get_automation_audit_concurrency(), 3)
                mock_db.assert_not_called()

    def test_env_empty_falls_back_to_db(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": ""}, clear=False):
            with patch("core.automation_config.database.get_config_value", return_value="4"):
                self.assertEqual(_get_automation_audit_concurrency(), 4)

    def test_default_is_five(self):
        env = dict(os.environ)
        env.pop("AUTOMATION_AUDIT_CONCURRENCY", None)
        with patch.dict(os.environ, env, clear=True):
            with patch("core.automation_config.database.get_config_value", side_effect=lambda k, d=None: d):
                self.assertEqual(_get_automation_audit_concurrency(), 5)

    def test_clamped_to_ceiling_ten(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "999"}, clear=False):
            self.assertEqual(_get_automation_audit_concurrency(), 10)

    def test_clamped_to_floor_one(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "0"}, clear=False):
            self.assertEqual(_get_automation_audit_concurrency(), 1)

    def test_invalid_falls_back_to_default(self):
        with patch.dict(os.environ, {"AUTOMATION_AUDIT_CONCURRENCY": "abc"}, clear=False):
            self.assertEqual(_get_automation_audit_concurrency(), 5)


if __name__ == "__main__":
    unittest.main()
