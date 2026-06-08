import os
import sys
import unittest
from unittest.mock import patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import ai_feedback  # noqa: E402


class _FakeCursor:
    def __init__(self, *, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results and isinstance(self.fetchall_results[0], list):
            return list(self.fetchall_results.pop(0))
        return list(self.fetchall_results)


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class TestAIFeedbackPgvectorFallback(unittest.TestCase):
    def test_add_feedback_skips_embedding_column_when_pgvector_is_unavailable(self):
        cursor = _FakeCursor(fetchone_results=[None, {"id": 12}])
        conn = _FakeConnection(cursor)

        with patch.object(ai_feedback, "_get_connection", return_value=conn):
            result = ai_feedback.add_feedback(
                "classificacao",
                "Situacao",
                "Correcao",
                "Justificativa",
                "tester",
                transcricao_embedding=[0.1, 0.2],
            )

        self.assertEqual(result, {"id": 12, "created": True})
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)
        insert_query, insert_params = cursor.executed[-1]
        self.assertIn("INSERT INTO ai_feedback", insert_query)
        self.assertNotIn("transcricao_embedding", insert_query)
        self.assertEqual(len(insert_params), 8)

    def test_prompt_feedback_falls_back_to_chronological_order_without_embedding_column(self):
        row = {
            "tipo": "classificacao",
            "setor": "logistica",
            "criterio_id": None,
            "situacao": "Classificacao anterior",
            "correcao": "Correcao humana",
            "justificativa": "Motivo",
            "exemplo_transcricao": None,
        }
        cursor = _FakeCursor(fetchone_results=[None], fetchall_results=[row])
        conn = _FakeConnection(cursor)

        with patch.object(ai_feedback, "_get_connection", return_value=conn):
            prompt = ai_feedback.get_feedback_for_prompt(
                setor="logistica",
                tipos={"classificacao"},
                query_embedding=[0.1, 0.2],
            )

        select_query, select_params = cursor.executed[-1]
        self.assertIn("ORDER BY criado_em DESC", select_query)
        self.assertNotIn("<->", select_query)
        self.assertEqual(select_params[-1], ai_feedback.MAX_FEEDBACK_PER_PROMPT)
        self.assertIn("CALIBRACOES DOS AUDITORES", prompt)
        self.assertIn("Correcao humana", prompt)

    def test_prompt_feedback_falls_back_when_semantic_search_has_no_matches(self):
        row = {
            "tipo": "avaliacao",
            "setor": "logistica",
            "criterio_id": "C01",
            "situacao": "Avaliacao anterior",
            "correcao": "Correcao cronologica",
            "justificativa": "Motivo",
            "exemplo_transcricao": None,
        }
        cursor = _FakeCursor(fetchone_results=[{"column": 1}], fetchall_results=[[], [row]])
        conn = _FakeConnection(cursor)

        with patch.object(ai_feedback, "_get_connection", return_value=conn):
            prompt = ai_feedback.get_feedback_for_prompt(
                setor="logistica",
                tipos={"avaliacao"},
                query_embedding=[0.1, 0.2],
            )

        semantic_query, _semantic_params = cursor.executed[-2]
        fallback_query, fallback_params = cursor.executed[-1]
        self.assertIn("<->", semantic_query)
        self.assertIn("ORDER BY criado_em DESC", fallback_query)
        self.assertEqual(fallback_params[-1], ai_feedback.MAX_FEEDBACK_PER_PROMPT)
        self.assertIn("CALIBRACOES DOS AUDITORES", prompt)
        self.assertIn("Correcao cronologica", prompt)


if __name__ == "__main__":
    unittest.main()
