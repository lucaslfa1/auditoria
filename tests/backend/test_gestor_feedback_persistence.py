import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestGestorFeedbackPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_gestor_feedback_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _create_audit(self, operator_id: str) -> int:
        result = AuditResult(
            score=8.0,
            maxPossibleScore=10.0,
            summary="Teste de feedback gestor",
            details=[
                AuditResultDetail(
                    criterionId="CR01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=8.0,
                    comment="Teste",
                )
            ],
            transcription=[
                TranscriptionSegment(
                    start="00:00",
                    end="00:03",
                    text="Operador: bom dia",
                )
            ],
            operatorName="Operador QA",
            operatorId=operator_id,
            timestamp="2026-03-04T16:30:00",
            source_type="audio",
        )

        database.save_audit(
            result,
            input_hash=f"hash-{operator_id}",
            alert_id="alerta-feedback",
            alert_label="Alerta Feedback",
            operator_id=operator_id,
            sector_id="logistica",
            status="pending_approval",
        )

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM audits WHERE operator_id = %s ORDER BY id DESC LIMIT 1", (operator_id,))
        row = c.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        return int(row[0])

    def test_save_and_get_feedback(self):
        audit_id = self._create_audit("OP-001")

        saved = database.save_gestor_feedback(
            audit_id=audit_id,
            gestor_nome="Maria Silva",
            feedback_texto="Bom trabalho",
            pontos_melhoria="Manter padrao",
        )
        self.assertTrue(saved)

        feedback = database.get_gestor_feedback(audit_id)
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["audit_id"], audit_id)
        self.assertEqual(feedback["gestor_nome"], "Maria Silva")
        self.assertEqual(feedback["feedback_texto"], "Bom trabalho")
        self.assertEqual(feedback["pontos_melhoria"], "Manter padrao")

    def test_save_feedback_updates_existing_record(self):
        audit_id = self._create_audit("OP-002")

        self.assertTrue(
            database.save_gestor_feedback(
                audit_id=audit_id,
                gestor_nome="Maria Silva",
                feedback_texto="Primeiro feedback",
                pontos_melhoria="Ajustar saudacao",
            )
        )
        self.assertTrue(
            database.save_gestor_feedback(
                audit_id=audit_id,
                gestor_nome="Maria Silva",
                feedback_texto="Feedback atualizado",
                pontos_melhoria="Manter consistencia",
            )
        )

        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM gestor_feedbacks WHERE audit_id = %s", (audit_id,))
        count = int(c.fetchone()[0])
        conn.close()
        self.assertEqual(count, 1)

        feedback = database.get_gestor_feedback(audit_id)
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["feedback_texto"], "Feedback atualizado")
        self.assertEqual(feedback["pontos_melhoria"], "Manter consistencia")

    def test_contestation_pending_review_remains_visible_with_status_and_reason(self):
        audit_id = self._create_audit("OP-003")
        database.update_audit_status(audit_id, "contestation_pending_review", "Exemplo obrigatório já selecionado")

        audits = database.get_audits_for_export()
        contested = next((audit for audit in audits if audit["id"] == audit_id), None)

        self.assertIsNotNone(contested)
        self.assertEqual(contested["status"], "contestation_pending_review")
        self.assertEqual(contested["contestation_reason"], "Exemplo obrigatório já selecionado")


if __name__ == "__main__":
    unittest.main()
