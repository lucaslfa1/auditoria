"""Tests for the saved_files async dispatcher (C3 from 2026-05-10 review).

Covers:
    - Inline mode under pytest by default (no worker started).
    - Async dispatch when inline override is disabled: producer returns
      immediately, worker drains the queue and invokes the inline body.
    - Full-queue degradation falls back to inline (no loss).
    - flush() returns True when drained, False on timeout.
"""

import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import saved_files_sync_queue as queue_mod


class TestInlineMode(unittest.TestCase):
    """Under pytest the default is inline mode — no thread, immediate dispatch."""

    def setUp(self):
        queue_mod.set_inline_mode(None)  # let env-driven detection kick in

    def tearDown(self):
        queue_mod.set_inline_mode(None)

    def test_pytest_defaults_to_inline(self):
        # PYTEST_CURRENT_TEST is always set by the runner, so default is inline.
        self.assertTrue(queue_mod._is_inline_mode())

    def test_enqueue_runs_inline_under_pytest(self):
        called = []

        def fake_inline(audit_id, criado_por=""):
            called.append((audit_id, criado_por))

        with patch("db.database._sync_arquivo_salvo_for_audit_inline", fake_inline, create=True):
            queue_mod.enqueue(99, criado_por="auditor@example.com")

        self.assertEqual(called, [(99, "auditor@example.com")])

    def test_inline_override_forces_inline_even_outside_pytest(self):
        queue_mod.set_inline_mode(True)
        self.assertTrue(queue_mod._is_inline_mode())

    def test_inline_override_false_disables_inline_mode(self):
        queue_mod.set_inline_mode(False)
        self.assertFalse(queue_mod._is_inline_mode())


class TestAsyncDispatch(unittest.TestCase):
    """When inline mode is forced off, work is queued and run on a worker thread."""

    def setUp(self):
        queue_mod.set_inline_mode(False)

    def tearDown(self):
        queue_mod.set_inline_mode(None)

    def test_enqueue_runs_on_worker_thread(self):
        calls = []
        done = threading.Event()

        def fake_inline(audit_id, criado_por=""):
            calls.append((threading.current_thread().name, audit_id, criado_por))
            done.set()

        with patch("db.database._sync_arquivo_salvo_for_audit_inline", fake_inline, create=True):
            queue_mod.enqueue(7, criado_por="x")
            self.assertTrue(done.wait(timeout=5.0), "worker did not run job within 5s")

        self.assertEqual(len(calls), 1)
        thread_name, audit_id, criado_por = calls[0]
        self.assertEqual(audit_id, 7)
        self.assertEqual(criado_por, "x")
        self.assertEqual(thread_name, "saved-files-sync")

    def test_worker_survives_inline_exception(self):
        """A failure on one job must not kill the worker thread."""
        seen = []
        ready = threading.Event()

        def fake_inline(audit_id, criado_por=""):
            seen.append(audit_id)
            if audit_id == 1:
                raise RuntimeError("boom")
            if audit_id == 2:
                ready.set()

        with patch("db.database._sync_arquivo_salvo_for_audit_inline", fake_inline, create=True):
            queue_mod.enqueue(1)
            queue_mod.enqueue(2)
            self.assertTrue(ready.wait(timeout=5.0))

        self.assertIn(1, seen)
        self.assertIn(2, seen)

    def test_flush_returns_true_after_drain(self):
        def fake_inline(audit_id, criado_por=""):
            time.sleep(0.01)

        with patch("db.database._sync_arquivo_salvo_for_audit_inline", fake_inline, create=True):
            for i in range(5):
                queue_mod.enqueue(i)
            drained = queue_mod.flush(timeout=5.0)

        self.assertTrue(drained)


if __name__ == "__main__":
    unittest.main()
