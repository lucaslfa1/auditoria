import asyncio
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.classifier import ClassificationCorrectionPayload, correct_classification


class TestTriagemAudioPuroAprendizado(unittest.TestCase):
    def setUp(self):
        self.user = {"username": "lucas"}

    @patch("db.database.corrigir_classificacao_fila_revisao")
    @patch("db.database.get_ligacao_auditada_por_hash")
    @patch("db.database.registrar_resultado_classificacao")
    @patch("core.ai_feedback.add_feedback")
    def test_correct_classification_creates_feedback_when_changed_and_transcription_present(
        self, mock_add_feedback, mock_reg, mock_get_lig, mock_corrigir
    ):
        mock_corrigir.return_value = {
            "nome_arquivo": "call.wav",
            "input_hash": "hash123",
            "setor_previsto": "uti",
            "alerta_previsto": "UTI-PRIORITARIO-MOT",
            "confianca": 0.9,
            "operador_previsto": "Deirilene",
            "erro": None,
            "status": "reviewed",
            "metadata": {
                "transcription": "alo alo nete da opentech por favor me passa a senha",
                "manual_review_previous": {
                    "setor_previsto": "logistica",
                    "alerta_previsto": "LOGISTICA-PARADA",
                }
            }
        }
        mock_get_lig.return_value = None

        payload = ClassificationCorrectionPayload(
            sector_id="uti",
            alert_id="UTI-PRIORITARIO-MOT",
            operator_name="Deirilene",
        )

        result = asyncio.run(
            correct_classification(
                input_hash="hash123",
                payload=payload,
                user=self.user,
            )
        )

        self.assertIsNotNone(result)
        mock_add_feedback.assert_called_once()
        _, kwargs = mock_add_feedback.call_args
        self.assertEqual(kwargs["tipo"], "classificacao")
        self.assertEqual(kwargs["setor"], "uti")
        self.assertEqual(kwargs["criterio_id"], "UTI-PRIORITARIO-MOT")
        self.assertEqual(kwargs["exemplo_transcricao"], "alo alo nete da opentech por favor me passa a senha")
        self.assertIn("A IA previu incorretamente o setor", kwargs["situacao"])
        self.assertIn("O auditor corrigiu para o setor", kwargs["correcao"])

    @patch("db.database.corrigir_classificacao_fila_revisao")
    @patch("db.database.get_ligacao_auditada_por_hash")
    @patch("core.ai_feedback.add_feedback")
    def test_correct_classification_no_feedback_when_not_changed(
        self, mock_add_feedback, mock_get_lig, mock_corrigir
    ):
        mock_corrigir.return_value = {
            "nome_arquivo": "call.wav",
            "input_hash": "hash123",
            "setor_previsto": "logistica",
            "alerta_previsto": "LOGISTICA-PARADA",
            "confianca": 0.9,
            "operador_previsto": "Deirilene",
            "erro": None,
            "status": "reviewed",
            "metadata": {
                "transcription": "alo alo nete da opentech por favor me passa a senha",
                "manual_review_previous": {
                    "setor_previsto": "logistica",
                    "alerta_previsto": "LOGISTICA-PARADA",
                }
            }
        }
        mock_get_lig.return_value = None

        payload = ClassificationCorrectionPayload(
            sector_id="logistica",
            alert_id="LOGISTICA-PARADA",
            operator_name="Deirilene",
        )

        result = asyncio.run(
            correct_classification(
                input_hash="hash123",
                payload=payload,
                user=self.user,
            )
        )

        self.assertIsNotNone(result)
        mock_add_feedback.assert_not_called()

    @patch("db.database.corrigir_classificacao_fila_revisao")
    @patch("db.database.get_ligacao_auditada_por_hash")
    @patch("core.ai_feedback.add_feedback")
    def test_correct_classification_no_feedback_when_no_transcription(
        self, mock_add_feedback, mock_get_lig, mock_corrigir
    ):
        mock_corrigir.return_value = {
            "nome_arquivo": "call.wav",
            "input_hash": "hash123",
            "setor_previsto": "uti",
            "alerta_previsto": "UTI-PRIORITARIO-MOT",
            "confianca": 0.9,
            "operador_previsto": "Deirilene",
            "erro": None,
            "status": "reviewed",
            "metadata": {
                "manual_review_previous": {
                    "setor_previsto": "logistica",
                    "alerta_previsto": "LOGISTICA-PARADA",
                }
            }
        }
        mock_get_lig.return_value = None

        payload = ClassificationCorrectionPayload(
            sector_id="uti",
            alert_id="UTI-PRIORITARIO-MOT",
            operator_name="Deirilene",
        )

        result = asyncio.run(
            correct_classification(
                input_hash="hash123",
                payload=payload,
                user=self.user,
            )
        )

        self.assertIsNotNone(result)
        mock_add_feedback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
