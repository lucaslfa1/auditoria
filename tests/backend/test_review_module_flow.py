import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestReviewModuleFlow(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_review_module_flow_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_pending_audit(self, operator_id: str) -> int:
        result = AuditResult(
            score=7.0,
            maxPossibleScore=10.0,
            summary="Auditoria sob contestação",
            details=[
                AuditResultDetail(
                    criterionId="CR01",
                    label="Saudação",
                    status="fail",
                    weight=10.0,
                    obtainedScore=7.0,
                    comment="Sem identificação completa",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:04", text="Atendimento iniciado")
            ],
            operatorName="Operador Revisão",
            operatorId=operator_id,
            timestamp="2026-03-12T20:00:00",
            source_type="audio",
        )
        database.save_audit(
            result,
            input_hash=f"review-flow-{operator_id}",
            operator_id=operator_id,
            sector_id="fenix",
            status="pending_approval",
        )
        conn = database.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM audits WHERE operator_id = %s ORDER BY id DESC LIMIT 1", (operator_id,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            return int(row[0])
        finally:
            conn.close()

    def test_rejecting_contestation_returns_audit_to_official_dashboard(self):
        audit_id = self._create_pending_audit("REV-001")
        database.update_audit_status(audit_id, "contestation_pending_review", "Supervisor contestou a nota.")

        result = database.finalize_contestation_review(
            audit_id,
            verdict="rejected",
            defense="A evidência confirma a nota original.",
            reviewed_by="auditoria.qa",
        )

        self.assertEqual(result["status"], "approved")
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "approved")
        self.assertEqual(audit["contestation_verdict"], "rejected")
        self.assertEqual(audit["review_defense"], "A evidência confirma a nota original.")
        self.assertEqual(audit["reviewed_by"], "auditoria.qa")

    def test_accepting_contestation_sends_audit_to_dashboard_with_changes(self):
        audit_id = self._create_pending_audit("REV-002")
        database.update_audit_status(audit_id, "contestation_pending_review", "Supervisor apontou inconsistência.")

        result = database.finalize_contestation_review(
            audit_id,
            verdict="accepted",
            defense="Contestação aceita por inconsistência no enquadramento.",
            reviewed_by="auditoria.qa",
        )

        # Accepted contestation goes to dashboard as approved (with changes applied)
        self.assertEqual(result["status"], "approved")
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        self.assertEqual(audit["status"], "approved")
        self.assertEqual(audit["contestation_verdict"], "accepted")
        self.assertEqual(audit["review_defense"], "Contestação aceita por inconsistência no enquadramento.")

        approved_audits = database.get_audits_for_export(statuses=["approved"])
        self.assertTrue(any(item["id"] == audit_id for item in approved_audits))


if __name__ == "__main__":
    unittest.main()
