import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation_engine as automation_engine


class _PoolCountingCursor:
    """Cursor minimo que devolve uma linha truthy em fetchone().

    Mantemos um buffer de queries para inspecao opcional, mas o foco do teste
    e o ciclo de vida da conexao, nao o conteudo do SQL.
    """

    def __init__(self):
        self.executed: list[tuple] = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        return (automation_engine._AutomationCycleLock._KEY,)


class _PoolCountingConnection:
    """Conexao fake que conta abre/fecha para verificar que nao fica presa."""

    def __init__(self, owner_counter: dict[str, int]):
        self._cursor = _PoolCountingCursor()
        self._counter = owner_counter
        self._counter["open"] += 1
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        if not self.closed:
            self.closed = True
            self._counter["closed"] += 1


class TestAutomationCycleLockPoolHygiene(unittest.TestCase):
    """Regressao: o lock nao pode segurar uma conexao do pool entre chamadas.

    O `_AutomationCycleLock` retinha `self._conn` entre `acquire()` e
    `release()` (minutos durante o ciclo de automacao), o que prendia 1 slot
    do BoundedSemaphore do pool (DB_POOL_MAX_CONN=20) e contribuia para a
    latencia observada em endpoints de Telefonia enquanto o ciclo rodava
    (v1.3.91 documentou o sintoma).
    """

    def _patch_pool(self):
        counter = {"open": 0, "closed": 0}

        def factory():
            return _PoolCountingConnection(counter)

        return counter, patch.object(
            automation_engine.database, "get_connection", side_effect=factory
        )

    def test_acquire_releases_pool_connection_before_returning(self):
        counter, patcher = self._patch_pool()
        with patcher:
            lock = automation_engine._AutomationCycleLock()
            acquired = lock.acquire()
        self.assertTrue(acquired)
        self.assertTrue(lock.acquired)
        self.assertEqual(
            counter["open"],
            counter["closed"],
            "acquire() deve devolver a conexao ao pool antes de retornar",
        )

    def test_refresh_releases_pool_connection_before_returning(self):
        counter, patcher = self._patch_pool()
        with patcher:
            lock = automation_engine._AutomationCycleLock()
            lock.acquire()
            open_after_acquire = counter["open"]
            refreshed = lock.refresh()
        self.assertTrue(refreshed)
        self.assertGreater(
            counter["open"],
            open_after_acquire,
            "refresh() deve abrir uma conexao curta nova",
        )
        self.assertEqual(
            counter["open"],
            counter["closed"],
            "refresh() deve devolver a conexao ao pool antes de retornar",
        )

    def test_release_does_not_leak_pool_connection(self):
        counter, patcher = self._patch_pool()
        with patcher:
            lock = automation_engine._AutomationCycleLock()
            lock.acquire()
            lock.release()
        self.assertFalse(lock.acquired)
        self.assertEqual(
            counter["open"],
            counter["closed"],
            "release() deve fechar qualquer conexao usada",
        )


class _BrokenCommitConnection:
    """Conexao fake cujo commit falha (simula conexao stale/rede caida)."""

    def __init__(self):
        self._cursor = _PoolCountingCursor()
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        raise RuntimeError("conexao stale: commit falhou")

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class TestAutomationCycleLockStaleConnection(unittest.TestCase):
    """v1.3.119: release() re-tenta com conexao NOVA; refresh() trata erro
    transitorio como lock perdido em vez de estourar erro cru no ciclo."""

    def test_release_retenta_com_conexao_nova_apos_falha(self):
        lock = automation_engine._AutomationCycleLock()
        good_counter = {"open": 0, "closed": 0}
        connections = [_BrokenCommitConnection(), _PoolCountingConnection(good_counter)]

        with patch.object(automation_engine.database, "get_connection", side_effect=lambda: connections.pop(0)):
            lock.acquired = True
            lock.release()  # nao deve lancar

        self.assertFalse(lock.acquired)
        self.assertEqual(good_counter["open"], 1, "2a tentativa deve usar conexao nova")
        self.assertEqual(good_counter["closed"], 1, "2a tentativa deve fechar a conexao")

    def test_release_desiste_apos_duas_falhas_sem_lancar(self):
        lock = automation_engine._AutomationCycleLock()
        with patch.object(automation_engine.database, "get_connection", side_effect=lambda: _BrokenCommitConnection()):
            lock.acquired = True
            lock.release()  # TTL assume; sem excecao propagada
        self.assertFalse(lock.acquired)

    def test_refresh_trata_erro_de_conexao_como_lock_perdido(self):
        lock = automation_engine._AutomationCycleLock()
        lock.acquired = True
        with patch.object(automation_engine.database, "get_connection", side_effect=RuntimeError("db down")):
            refreshed = lock.refresh()
        self.assertFalse(refreshed)
        self.assertFalse(lock.acquired)

    def test_refresh_trata_commit_falho_como_lock_perdido(self):
        lock = automation_engine._AutomationCycleLock()
        lock.acquired = True
        with patch.object(automation_engine.database, "get_connection", side_effect=lambda: _BrokenCommitConnection()):
            refreshed = lock.refresh()
        self.assertFalse(refreshed)
        self.assertFalse(lock.acquired)


if __name__ == "__main__":
    unittest.main()
