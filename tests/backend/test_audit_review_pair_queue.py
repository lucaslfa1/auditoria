import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestAuditReviewPairQueue(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_audit_review_pair_queue_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _build_result(self, *, operator_name: str, operator_id: str, timestamp: str) -> AuditResult:
        return AuditResult(
            score=8.0,
            maxPossibleScore=10.0,
            summary="Auditoria para fila em dupla",
            details=[
                AuditResultDetail(
                    criterionId="CR01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=8.0,
                    comment="Registro valido",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:03", text="Operador: bom dia")
            ],
            operatorName=operator_name,
            operatorId=operator_id,
            timestamp=timestamp,
            source_type="audio",
        )

    def test_first_audit_waits_for_second_before_supervisor(self):
        first = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Par",
                operator_id="OP-PAIR",
                timestamp="2026-03-12T18:00:00",
            ),
            input_hash="pair-hash-1",
            alert_id="alerta-1",
            alert_label="Alerta 1",
            operator_id="OP-PAIR",
            sector_id="bas",
        )

        audit = audits.get_audit_by_id(database.get_connection, first["audit_id"])
        self.assertEqual(first["status"], "awaiting_pair")
        self.assertIsNotNone(audit)
        self.assertEqual(audit["status"], "awaiting_pair")

    def test_second_audit_releases_pair_to_supervisor(self):
        first = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Par",
                operator_id="OP-PAIR",
                timestamp="2026-03-12T18:05:00",
            ),
            input_hash="pair-hash-2a",
            alert_id="alerta-1",
            alert_label="Alerta 1",
            operator_id="OP-PAIR",
            sector_id="bas",
        )
        second = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Par",
                operator_id="OP-PAIR",
                timestamp="2026-03-12T18:10:00",
            ),
            input_hash="pair-hash-2b",
            alert_id="alerta-2",
            alert_label="Alerta 2",
            operator_id="OP-PAIR",
            sector_id="bas",
        )

        first_audit = audits.get_audit_by_id(database.get_connection, first["audit_id"])
        second_audit = audits.get_audit_by_id(database.get_connection, second["audit_id"])

        self.assertEqual(second["status"], "pending_approval")
        self.assertEqual(first_audit["status"], "pending_approval")
        self.assertEqual(second_audit["status"], "pending_approval")

    def test_approving_one_audit_promotes_next_waiting_audit(self):
        first = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Promocao",
                operator_id="OP-NEXT",
                timestamp="2026-03-12T18:20:00",
            ),
            input_hash="pair-hash-3a",
            alert_id="alerta-1",
            alert_label="Alerta 1",
            operator_id="OP-NEXT",
            sector_id="fenix",
        )
        second = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Promocao",
                operator_id="OP-NEXT",
                timestamp="2026-03-12T18:25:00",
            ),
            input_hash="pair-hash-3b",
            alert_id="alerta-2",
            alert_label="Alerta 2",
            operator_id="OP-NEXT",
            sector_id="fenix",
        )
        third = database.queue_audit_for_supervisor_review(
            self._build_result(
                operator_name="Operador Promocao",
                operator_id="OP-NEXT",
                timestamp="2026-03-12T18:30:00",
            ),
            input_hash="pair-hash-3c",
            alert_id="alerta-3",
            alert_label="Alerta 3",
            operator_id="OP-NEXT",
            sector_id="fenix",
        )

        self.assertEqual(audits.get_audit_by_id(database.get_connection, third["audit_id"])["status"], "awaiting_pair")

        database.update_audit_status(first["audit_id"], "approved")

        updated_second = audits.get_audit_by_id(database.get_connection, second["audit_id"])
        updated_third = audits.get_audit_by_id(database.get_connection, third["audit_id"])

        self.assertEqual(updated_second["status"], "pending_approval")
        self.assertEqual(updated_third["status"], "pending_approval")


if __name__ == "__main__":
    unittest.main()
