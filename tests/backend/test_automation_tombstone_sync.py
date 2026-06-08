"""Tombstone na huawei_sync_logs (db/database.py).

Descarte permanente nunca rebaixa; recuperavel rebaixa ate o limite anti-loop. A linha
e PRESERVADA (UPSERT), nao deletada, para o contador sobreviver ao DELETE da fila.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db import database
from repositories import classification_review


class _FakeCursor:
    def __init__(self, returning=(1, "discarded_recoverable")):
        self.queries = []
        self._returning = returning

    def execute(self, sql, params=()):
        self.queries.append((" ".join(sql.split()), tuple(params) if params else ()))

    def fetchone(self):
        return {"discard_attempts": self._returning[0], "status": self._returning[1]}


class TestTombstoneHelper(unittest.TestCase):
    def test_permanent_grava_discarded_permanent_sem_delete(self):
        cur = _FakeCursor(returning=(1, "discarded_permanent"))
        attempts, status = database.huawei_sync_log_tombstone(
            cur, "C-1", permanent=True, motivo="transcricao_impossivel"
        )
        sql = cur.queries[0][0]
        self.assertIn("INSERT INTO huawei_sync_logs", sql)
        self.assertIn("discarded_permanent", sql)
        self.assertNotIn("DELETE", sql)
        self.assertEqual(status, "discarded_permanent")

    def test_recoverable_incrementa_attempts_e_usa_loop_limit_no_case(self):
        cur = _FakeCursor(returning=(2, "discarded_recoverable"))
        attempts, status = database.huawei_sync_log_tombstone(
            cur, "C-2", permanent=False, motivo="x", loop_limit=3
        )
        sql, params = cur.queries[0]
        self.assertIn("discarded_recoverable", sql)
        self.assertIn("discard_attempts = huawei_sync_logs.discard_attempts + 1", sql)
        self.assertIn(3, params)  # loop_limit usado no CASE de promocao a permanent
        self.assertEqual(attempts, 2)

    def test_call_id_vazio_e_noop(self):
        cur = _FakeCursor()
        self.assertEqual(database.huawei_sync_log_tombstone(cur, "", permanent=True), (0, ""))
        self.assertEqual(cur.queries, [])

    def test_row_nao_dict_nao_quebra(self):
        # robustez: cursor que retorna tupla simples no RETURNING
        class _TupleCursor(_FakeCursor):
            def fetchone(self):
                return (4, "discarded_permanent")

        attempts, status = database.huawei_sync_log_tombstone(_TupleCursor(), "C-9", permanent=True)
        self.assertEqual((attempts, status), (4, "discarded_permanent"))


class TestSyncLogExistsAllowlist(unittest.TestCase):
    """discarded_recoverable e reversivel (rebaixa); discarded_permanent nao (tombstone)."""

    def _captured_sql(self) -> str:
        captured = {}

        class _Cur:
            def execute(self, sql, params=()):
                captured["sql"] = " ".join(sql.split())

            def fetchone(self):
                return None

        class _Conn:
            def cursor(self):
                return _Cur()

            def close(self):
                pass

        with patch.object(database, "get_connection", return_value=_Conn()):
            database.huawei_sync_log_exists("C-1")
        return captured.get("sql", "")

    def test_allowlist_inclui_recoverable_e_exclui_permanent(self):
        sql = self._captured_sql()
        self.assertIn("NOT IN", sql)
        # recoverable na lista de reversiveis -> rebaixa
        self.assertIn("discarded_recoverable", sql)
        # permanent FORA da lista -> tratado como "ja sincronizado" (nao rebaixa)
        self.assertNotIn("discarded_permanent", sql)


class TestSyncLogRegistrarTombstone(unittest.TestCase):
    def test_registrar_nao_promove_discarded_permanent(self):
        captured = {}

        class _Cur:
            def execute(self, sql, params=()):
                captured["sql"] = " ".join(sql.split())
                captured["params"] = tuple(params)

        class _Conn:
            def cursor(self):
                return _Cur()

            def commit(self):
                captured["committed"] = True

            def close(self):
                captured["closed"] = True

        with patch.object(database, "get_connection", return_value=_Conn()):
            database.huawei_sync_log_registrar("C-1", status="success")

        sql = captured.get("sql", "")
        self.assertIn("ON CONFLICT (call_id) DO UPDATE", sql)
        self.assertIn("WHERE huawei_sync_logs.status IS DISTINCT FROM 'discarded_permanent'", sql)
        self.assertTrue(captured.get("committed"))


class TestReviewQueueTombstoneGuard(unittest.TestCase):
    def test_sync_nao_reenfileira_huawei_com_tombstone_permanente(self):
        captured = {"queries": [], "rolled_back": False}

        class _Cur:
            def execute(self, sql, params=()):
                captured["queries"].append((" ".join(sql.split()), tuple(params or ())))

            def fetchone(self):
                return (1,)

        class _Conn:
            def cursor(self):
                return _Cur()

            def rollback(self):
                captured["rolled_back"] = True

            def close(self):
                captured["closed"] = True

        result = classification_review.sincronizar_fila_revisao_classificacao(
            lambda: _Conn(),
            input_hash="hash-1",
            nome_arquivo="ligacao.wav",
            metadata={"origem": "huawei_sync", "huawei_call_id": "C-1"},
        )

        self.assertIsNone(result)
        self.assertTrue(captured["rolled_back"])
        sqls = [sql for sql, _params in captured["queries"]]
        self.assertIn("FROM huawei_sync_logs", sqls[0])
        self.assertFalse(any("INSERT INTO fila_revisao_classificacao" in sql for sql in sqls))
        self.assertFalse(any("UPDATE fila_revisao_classificacao" in sql for sql in sqls))


if __name__ == "__main__":
    unittest.main()
