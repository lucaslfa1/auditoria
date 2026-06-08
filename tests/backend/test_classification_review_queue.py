import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestClassificationReviewQueue(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_classification_review_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sync_inserts_pending_low_confidence_item(self):
        review_id = database.sincronizar_fila_revisao_classificacao(
            input_hash="hash-low-confidence",
            nome_arquivo="random-call.wav",
            setor_previsto="logistica",
            alerta_previsto="4.4.1",
            confianca=0.61,
            operador_previsto="Operador X",
            precisa_revisao=True,
            prioridade="medium",
            motivos_revisao=["baixa_confianca"],
            metadata={"filename_upload": "random-call.wav"},
        )

        self.assertIsInstance(review_id, int)
        queue = database.listar_fila_revisao_classificacao(limit=10, status="pending")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["nome_arquivo"], "random-call.wav")
        self.assertEqual(queue[0]["motivos_revisao"], ["baixa_confianca"])
        self.assertEqual(queue[0]["prioridade"], "medium")

    def test_sync_auto_resolves_existing_item_when_confident(self):
        database.sincronizar_fila_revisao_classificacao(
            input_hash="hash-rerun",
            nome_arquivo="call.wav",
            setor_previsto="desconhecido",
            alerta_previsto="desconhecido",
            confianca=0.22,
            erro="Short transcription",
            precisa_revisao=True,
            prioridade="high",
            motivos_revisao=["erro_classificacao", "setor_nao_identificado", "baixa_confianca"],
        )

        database.sincronizar_fila_revisao_classificacao(
            input_hash="hash-rerun",
            nome_arquivo="call.wav",
            setor_previsto="logistica",
            alerta_previsto="4.4.1",
            confianca=0.91,
            operador_previsto="Operador Y",
            precisa_revisao=False,
            prioridade="low",
            motivos_revisao=[],
        )

        pending_queue = database.listar_fila_revisao_classificacao(limit=10, status="pending")
        self.assertEqual(pending_queue, [])

        full_queue = database.listar_fila_revisao_classificacao(limit=10, status="all")
        self.assertEqual(len(full_queue), 1)
        self.assertEqual(full_queue[0]["status"], "auto_resolved")
        self.assertEqual(full_queue[0]["setor_previsto"], "logistica")
        self.assertEqual(full_queue[0]["motivos_revisao"], [])


if __name__ == "__main__":
    unittest.main()
