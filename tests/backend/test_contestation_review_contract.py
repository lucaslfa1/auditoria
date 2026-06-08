from repositories import audits
import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.audits import finalize_contestation_review


class TestContestationReviewContract(unittest.TestCase):
    class _Cursor:
        def __init__(self):
            self.queries = []

        def execute(self, query, params):
            self.queries.append((query, params))

    class _Connection:
        def __init__(self):
            self.cursor_obj = TestContestationReviewContract._Cursor()
            self.committed = False
            self.closed = False

        def cursor(self):
            return self.cursor_obj

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    @staticmethod
    def _current_audit():
        return {
            "id": 42,
            "status": "contestation_pending_review",
            "operator_name": "Operador Teste",
            "operator_id": "OP-42",
        }

    def test_rejected_contestation_preserves_original_details_and_score(self):
        conn = self._Connection()

        with patch("repositories.audits.get_audit_by_id", return_value=self._current_audit()):
            result = finalize_contestation_review(
                lambda: conn,
                42,
                verdict="rejected",
                defense="Nota original mantida.",
                reviewed_by="qa",
                updated_details=[
                    {"label": "Criterio", "status": "pass", "weight": 10, "obtainedScore": 10}
                ],
            )

        self.assertEqual(result["status"], "approved")
        self.assertEqual(result["contestation_verdict"], "rejected")
        update_query, update_params = conn.cursor_obj.queries[0]
        self.assertNotIn("details_json", update_query)
        self.assertNotIn("max_score", update_query)
        self.assertEqual(update_params, ("approved", "rejected", "Nota original mantida.", "qa", 42))
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)

    def test_accepted_contestation_recalculates_score_from_updated_details(self):
        conn = self._Connection()

        with patch("repositories.audits.get_audit_by_id", return_value=self._current_audit()):
            result = finalize_contestation_review(
                lambda: conn,
                42,
                verdict="accepted",
                defense="Criterios ajustados.",
                reviewed_by="qa",
                updated_details=[
                    {"label": "C1", "status": "PASS", "weight": 10, "obtainedScore": 0},
                    {"label": "C2", "status": "partial", "weight": 4, "obtainedScore": 0},
                    {"label": "C3", "status": "fail", "weight": 6, "obtainedScore": 6},
                    {"label": "C4", "status": "na", "weight": 8, "obtainedScore": 8},
                ],
            )

        self.assertEqual(result["contestation_verdict"], "accepted")
        update_query, update_params = conn.cursor_obj.queries[0]
        self.assertIn("details_json", update_query)
        self.assertEqual(update_params[5], 18.0)
        self.assertEqual(update_params[6], 28.0)
        self.assertIn('"status": "pass"', update_params[4])
        self.assertIn('"obtainedScore": 10.0', update_params[4])
        self.assertIn('"obtainedScore": 8.0', update_params[4])
        self.assertIn('"obtainedScore": 0.0', update_params[4])

    def test_accepted_contestation_rejects_invalid_detail_status(self):
        conn = self._Connection()

        with patch("repositories.audits.get_audit_by_id", return_value=self._current_audit()):
            with self.assertRaisesRegex(ValueError, "Status de criterio invalido"):
                finalize_contestation_review(
                    lambda: conn,
                    42,
                    verdict="accepted",
                    defense="Criterios ajustados.",
                    reviewed_by="qa",
                    updated_details=[
                        {"label": "C1", "status": "unknown", "weight": 10, "obtainedScore": 0},
                    ],
                )

        self.assertEqual(conn.cursor_obj.queries, [])
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
