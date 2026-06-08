"""Tests for critical audit flow fixes (T2, T3, C1, C2, T5)."""

import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestAuditFlowFixes(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_audit_flow_fixes_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _make_result(self, ai_feedback=None):
        return AuditResult(
            score=8.0,
            maxPossibleScore=10.0,
            summary="Test audit",
            details=[
                AuditResultDetail(
                    criterionId="C01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=10.0,
                    comment="OK",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde")
            ],
            operatorName="Operador Teste",
            operatorId="OP-001",
            timestamp="2026-03-12T12:00:00",
            source_type="audio",
            ai_feedback=ai_feedback,
        )

    def _create_audit_with_status(self, status, ai_feedback=None):
        result = self._make_result(ai_feedback=ai_feedback)
        database.save_audit(
            result,
            input_hash=f"flow-fix-{uuid.uuid4().hex[:8]}",
            operator_id="OP-001",
            sector_id="fenix",
            status=status,
            ai_feedback=ai_feedback,
        )
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM audits WHERE operator_id = 'OP-001' ORDER BY id DESC LIMIT 1"
            )
            return int(cursor.fetchone()[0])
        finally:
            conn.close()

    # --- T2: ai_feedback roundtrip ---
    def test_ai_feedback_roundtrip_via_row_to_audit_result(self):
        """T2 fix: ai_feedback must survive save -> load via row_to_audit_result."""
        feedback_text = "O operador demonstrou boa postura no atendimento."
        audit_id = self._create_audit_with_status(
            "pending_approval", ai_feedback=feedback_text
        )

        # Load via get_audit_by_id (uses dict, always had ai_feedback)
        audit_dict = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit_dict["ai_feedback"], feedback_text)

        # Load via cache path that uses row_to_audit_result
        from repositories.common import row_to_audit_result

        conn = database.get_connection()
        try:
            
            
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM audits WHERE id = %s", (audit_id,))
            row = cursor.fetchone()
            result = row_to_audit_result(row)
            self.assertIsNotNone(result)
            self.assertEqual(result.ai_feedback, feedback_text)
        finally:
            conn.close()

    # --- T3: Missing sector mappings ---
    def test_criteria_load_transferencia(self):
        """T3 fix: transferencia and other aliases must be in sector_mapping."""
        from core.config import load_criteria_for_sector

        # We read the source to verify the mapping dict contains our aliases.
        # Calling load_criteria_for_sector would try to load JSON files that
        # may not exist in the test env, so we just verify the mapping logic.
        import inspect
        import core.config as config_mod

        source = inspect.getsource(config_mod.load_criteria_for_sector)

        expected_aliases = {
            "transferencia": "rastreamento",
            "logistica_unilever": "unilever",
            "operacao_taborda": "logistica",
            "celula_atendimento": "receptivo",
        }
        for alias, target in expected_aliases.items():
            self.assertIn(
                f'"{alias}"',
                source,
                f"Alias '{alias}' must be in sector_mapping",
            )
            self.assertIn(
                f'"{target}"',
                source,
                f"Target '{target}' must be in sector_mapping for alias '{alias}'",
            )

    # --- T5: lru_cache returns immutable tuple ---
    def test_criteria_cache_returns_fresh_list(self):
        """T5 fix: load_criteria_for_sector must return a new list each call."""
        from core.config import load_criteria_for_sector

        result1 = load_criteria_for_sector("grs")
        result2 = load_criteria_for_sector("grs")

        if result1 is not None and result2 is not None:
            # They should be equal but NOT the same object
            self.assertEqual(result1, result2)
            self.assertIsNot(result1, result2, "Cache should return fresh list copies")
            # Mutating one should not affect the other
            result1.append(None)
            self.assertNotEqual(len(result1), len(result2))

    # --- C1: Status transition validation ---
    def test_approve_requires_pending_approval(self):
        """C1 fix: Cannot approve an audit that is already approved."""
        audit_id = self._create_audit_with_status("pending_approval")
        # First approve should work
        database.update_audit_status(audit_id, "approved", None)

        # Second approve should fail (approved -> approved not in transitions)
        with self.assertRaises(ValueError) as ctx:
            database.update_audit_status(audit_id, "approved", None)
        self.assertIn("invalida", str(ctx.exception).lower())

    def test_contest_requires_pending_approval(self):
        """C1 fix: Cannot contest an audit that is already approved."""
        audit_id = self._create_audit_with_status("pending_approval")
        database.update_audit_status(audit_id, "approved", None)

        with self.assertRaises(ValueError) as ctx:
            database.update_audit_status(
                audit_id, "contestation_pending_review", "Motivo"
            )
        self.assertIn("invalida", str(ctx.exception).lower())

    def test_approve_works_from_pending_approval(self):
        """C1 sanity: Normal approve flow still works."""
        audit_id = self._create_audit_with_status("pending_approval")
        database.update_audit_status(audit_id, "approved", None)
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "approved")

    def test_contest_works_from_pending_approval(self):
        """C1 sanity: Normal contest flow still works."""
        audit_id = self._create_audit_with_status("pending_approval")
        database.update_audit_status(
            audit_id, "contestation_pending_review", "Nota incorreta"
        )
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "contestation_pending_review")

    def test_approve_from_contestation_pending_review(self):
        """C1: Admin can reject contestation (approve from contestation_pending_review)."""
        audit_id = self._create_audit_with_status("pending_approval")
        database.update_audit_status(
            audit_id, "contestation_pending_review", "Motivo"
        )
        # This should still work (admin rejecting contestation)
        database.update_audit_status(audit_id, "approved", None)
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "approved")

    # --- C3: Review fields preserved ---
    def test_review_fields_preserved_across_review_flow(self):
        """C3 fix: Review metadata must not be wiped during review flow transitions."""
        audit_id = self._create_audit_with_status("pending_approval")
        database.update_audit_status(
            audit_id, "contestation_pending_review", "Nota discrepante"
        )

        # Admin reviews and rejects contestation
        database.finalize_contestation_review(
            audit_id,
            verdict="rejected",
            defense="Nota original mantida.",
            reviewed_by="admin.qa",
        )

        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "approved")
        self.assertEqual(audit["contestation_verdict"], "rejected")
        self.assertEqual(audit["review_defense"], "Nota original mantida.")
        self.assertEqual(audit["reviewed_by"], "admin.qa")
        self.assertIsNotNone(audit["reviewed_at"])


    # --- T1: Reevaluate persistence ---
    def test_reevaluate_persists_via_update_audit_result(self):
        """T1 fix: update_audit_result must update scores for an existing audit."""
        audit_id = self._create_audit_with_status("pending_approval")

        # Get the input_hash of the created audit
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        input_hash = audit["input_hash"]

        # Create a new result with different scores
        new_result = AuditResult(
            score=5.0,
            maxPossibleScore=10.0,
            summary="Reevaluated: score reduced",
            details=[
                AuditResultDetail(
                    criterionId="C01",
                    label="Saudacao",
                    status="fail",
                    weight=10.0,
                    obtainedScore=5.0,
                    comment="Falhou na reavaliacao",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde editado")
            ],
            operatorName="Operador Teste",
            operatorId="OP-001",
            timestamp="2026-03-12T12:00:00",
            source_type="audio",
            ai_feedback="Feedback atualizado na reavaliacao",
        )

        updated_id = database.update_audit_result(
            input_hash, new_result, ai_feedback="Feedback atualizado na reavaliacao"
        )
        self.assertEqual(updated_id, audit_id)

        # Verify the update
        updated_audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(updated_audit["score"], 5.0)
        self.assertEqual(updated_audit["summary"], "Reevaluated: score reduced")
        self.assertEqual(
            updated_audit["ai_feedback"], "Feedback atualizado na reavaliacao"
        )

    def test_update_audit_result_returns_none_for_unknown_hash(self):
        """T1: update_audit_result returns None when hash doesn't exist."""
        result = self._make_result()
        updated_id = database.update_audit_result("nonexistent-hash", result)
        self.assertIsNone(updated_id)


if __name__ == "__main__":
    unittest.main()
