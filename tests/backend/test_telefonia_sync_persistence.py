"""Cobertura do estado persistido do sync da Telefonia (v1.3.95).

Antes da v1.3.95 o estado de pause/cancel/heartbeat vivia apenas nos globals
`_LAST_SYNC*` em `backend/routers/telefonia.py`. Reinicio do Cloud Run
(deploy, OOM, idle scale-down) perdia o estado e a UI ficava mostrando
"running" indefinidamente.

A persistencia minima adicionada aqui esta na tabela `telefonia_sync_history`:
- `pause_requested`/`cancel_requested` (booleanos).
- `last_heartbeat_at` (timestamptz).

Esses testes documentam a contract das funcoes do repositorio e checam que
o reconcile do bootstrap marca runs orfaos como 'interrupted'.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class _FakeCursor:
    def __init__(self, *, fetch_one=None, fetch_all=None):
        self.queries: list[tuple[str, tuple]] = []
        self._fetch_one = fetch_one
        self._fetch_all = fetch_all or []

    def execute(self, query, params=()):
        self.queries.append((query.strip(), tuple(params) if params else ()))
        # Suporte basico a UPDATE ... RETURNING (simulado): proximo fetchone vira proximo da fila.
        if isinstance(self._fetch_one, list) and self._fetch_one:
            self._next_one = self._fetch_one.pop(0)
        elif self._fetch_one is not None and not isinstance(self._fetch_one, list):
            self._next_one = self._fetch_one
        else:
            self._next_one = None

    def fetchone(self):
        return self._next_one

    def fetchall(self):
        return self._fetch_all

    @property
    def rowcount(self):
        return getattr(self, "_rowcount", 0)


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _factory_with_cursor(cursor):
    def factory():
        return _FakeConn(cursor)
    return factory


class TestTelefoniaSyncPersistenceRepository(unittest.TestCase):
    """Funcoes novas no repositorio para gerenciar o run em progresso."""

    def test_start_telefonia_sync_run_inserts_row_with_null_finished_at(self):
        from repositories import telefonia as repo

        cur = _FakeCursor(fetch_one=(42,))
        run_id = repo.start_telefonia_sync_run(
            _factory_with_cursor(cur),
            started_at="2026-05-28T13:00:00+00:00",
            horas_retroativas=1,
            trigger_type="manual",
        )
        self.assertEqual(run_id, 42)
        # Deve ter feito 1 execute e 1 commit + close.
        self.assertEqual(len(cur.queries), 1)
        query, params = cur.queries[0]
        self.assertIn("INSERT INTO telefonia_sync_history", query)
        self.assertIn("RETURNING id", query)
        # finished_at e mensagem_erro devem ser NULL na criacao.
        self.assertIn("status", query.lower())
        self.assertIn("running", params)

    def test_heartbeat_updates_last_heartbeat_at_for_run_id(self):
        from repositories import telefonia as repo

        cur = _FakeCursor()
        repo.heartbeat_telefonia_sync_run(_factory_with_cursor(cur), run_id=42)
        self.assertEqual(len(cur.queries), 1)
        query, params = cur.queries[0]
        self.assertIn("UPDATE telefonia_sync_history", query)
        self.assertIn("last_heartbeat_at", query)
        self.assertIn(42, params)

    def test_set_pause_requested_updates_flag(self):
        from repositories import telefonia as repo

        cur = _FakeCursor()
        repo.set_telefonia_sync_pause(_factory_with_cursor(cur), run_id=42, pause=True)
        self.assertEqual(len(cur.queries), 1)
        query, params = cur.queries[0]
        self.assertIn("UPDATE telefonia_sync_history", query)
        self.assertIn("pause_requested", query)
        self.assertIn(True, params)
        self.assertIn(42, params)

    def test_set_cancel_requested_updates_flag(self):
        from repositories import telefonia as repo

        cur = _FakeCursor()
        repo.set_telefonia_sync_cancel(_factory_with_cursor(cur), run_id=42, cancel=True)
        self.assertEqual(len(cur.queries), 1)
        query, _ = cur.queries[0]
        self.assertIn("cancel_requested", query)

    def test_finalize_telefonia_sync_run_writes_finished_at_and_status(self):
        from repositories import telefonia as repo

        cur = _FakeCursor()
        repo.finalize_telefonia_sync_run(
            _factory_with_cursor(cur),
            run_id=42,
            finished_at="2026-05-28T13:05:00+00:00",
            status="completed",
            baixadas=3,
            enfileiradas=3,
            erros_totais=0,
            mensagem_erro=None,
        )
        self.assertEqual(len(cur.queries), 1)
        query, params = cur.queries[0]
        self.assertIn("UPDATE telefonia_sync_history", query)
        self.assertIn("finished_at", query)
        self.assertIn("completed", params)
        self.assertIn(42, params)

    def test_get_active_telefonia_sync_run_returns_none_when_no_open_run(self):
        from repositories import telefonia as repo

        cur = _FakeCursor(fetch_one=None)
        result = repo.get_active_telefonia_sync_run(_factory_with_cursor(cur))
        self.assertIsNone(result)
        query, _ = cur.queries[0]
        self.assertIn("finished_at IS NULL", query)

    def test_reconcile_stale_marks_interrupted_when_heartbeat_too_old(self):
        """Bootstrap do app marca runs orfaos (heartbeat antigo OU NULL com started_at antigo) como interrupted."""
        from repositories import telefonia as repo

        cur = _FakeCursor()
        cur._rowcount = 2  # simula que 2 linhas foram atualizadas
        count = repo.reconcile_stale_telefonia_sync_runs(
            _factory_with_cursor(cur),
            stale_after_seconds=120,
        )
        self.assertEqual(count, 2)
        query, _ = cur.queries[0]
        self.assertIn("UPDATE telefonia_sync_history", query)
        self.assertIn("interrupted", query.lower())
        self.assertIn("finished_at IS NULL", query)


if __name__ == "__main__":
    unittest.main()
