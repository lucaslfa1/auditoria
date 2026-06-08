import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.classification import ClassificationResult, finalize_classification_result


class TestClassificationReviewPolicy(unittest.TestCase):
    def _build_result(self, **overrides) -> ClassificationResult:
        payload = {
            "filename": "call.wav",
            "sector_id": "logistica",
            "sector_label": "Logistica",
            "alert_id": "LOGISTICA-PARADA",
            "alert_label": "Parada",
            "confidence": 0.95,
            "operator_name": "Operador X",
            "direction": "efetivada",
            "error": None,
            "direction_mismatch": False,
        }
        payload.update(overrides)
        return ClassificationResult(**payload)

    def test_high_confidence_without_structural_issues_skips_review(self):
        result = finalize_classification_result(self._build_result(confidence=0.91))

        self.assertFalse(result.needs_review)
        self.assertEqual(result.review_reasons, [])
        self.assertEqual(result.review_priority, "low")

    def test_low_confidence_routes_to_medium_review(self):
        result = finalize_classification_result(self._build_result(confidence=0.79))

        self.assertTrue(result.needs_review)
        self.assertIn("baixa_confianca", result.review_reasons)
        self.assertNotIn("confianca_muito_baixa", result.review_reasons)
        self.assertEqual(result.review_priority, "medium")

    def test_very_low_confidence_routes_to_high_review(self):
        result = finalize_classification_result(self._build_result(confidence=0.49))

        self.assertTrue(result.needs_review)
        self.assertIn("baixa_confianca", result.review_reasons)
        self.assertIn("confianca_muito_baixa", result.review_reasons)
        self.assertEqual(result.review_priority, "high")

    def test_direction_mismatch_escalates_to_high_review(self):
        result = finalize_classification_result(
            self._build_result(confidence=0.93, direction_mismatch=True)
        )

        self.assertTrue(result.needs_review)
        self.assertIn("direction_mismatch", result.review_reasons)
        self.assertEqual(result.review_priority, "medium")

    def test_unknown_alert_escalates_to_high_review(self):
        result = finalize_classification_result(
            self._build_result(alert_id="desconhecido", alert_label="Nao Identificado", confidence=0.88)
        )

        self.assertTrue(result.needs_review)
        self.assertIn("alerta_nao_identificado", result.review_reasons)
        self.assertEqual(result.review_priority, "high")


if __name__ == "__main__":
    unittest.main()
