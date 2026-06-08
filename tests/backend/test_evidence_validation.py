import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.evidence_validation import summarize_evidence_coverage, validate_evidence_against_transcription


class TestEvidenceValidation(unittest.TestCase):
    def test_marks_literal_evidence_as_matched(self):
        payload = {
            "summary": "ok",
            "details": [
                {
                    "criterionId": "identificacao",
                    "status": "pass",
                    "comment": "Localizado.",
                    "evidence_text": "Operador: bom dia, fala Ana.",
                }
            ],
        }
        transcription = [
            {"start": "00:00", "end": "00:03", "text": "Operador: bom dia, fala Ana."}
        ]

        result = validate_evidence_against_transcription(payload, transcription)

        detail = result["details"][0]
        self.assertTrue(detail["evidence_validation"]["matched"])
        self.assertEqual(detail["evidence_validation"]["method"], "literal")
        self.assertEqual(detail["comment"], "Localizado.")

    def test_marks_normalized_evidence_as_matched(self):
        payload = {
            "details": [
                {
                    "criterionId": "cpf",
                    "status": "pass",
                    "comment": "CPF confirmado.",
                    "evidence_text": "Motorista: meu cpf e 123",
                }
            ],
        }
        transcription = [
            {"start": "00:00", "end": "00:03", "text": "Motorista: meu CPF é 123."}
        ]

        result = validate_evidence_against_transcription(payload, transcription)

        self.assertTrue(result["details"][0]["evidence_validation"]["matched"])
        self.assertEqual(result["details"][0]["evidence_validation"]["method"], "normalized")

    def test_appends_comment_when_evidence_is_not_found(self):
        payload = {
            "details": [
                {
                    "criterionId": "senha",
                    "status": "fail",
                    "comment": "Senha nao solicitada.",
                    "evidence_text": "Operador pediu a senha.",
                }
            ],
        }
        transcription = [
            {"start": "00:00", "end": "00:03", "text": "Operador: informe o CPF."}
        ]

        result = validate_evidence_against_transcription(payload, transcription)

        detail = result["details"][0]
        self.assertFalse(detail["evidence_validation"]["matched"])
        self.assertEqual(detail["evidence_validation"]["status"], "not_found")
        self.assertIn("nao foi localizada na transcricao", detail["comment"])

    def test_empty_evidence_is_annotated_without_comment_noise(self):
        payload = {
            "details": [
                {
                    "criterionId": "despedida",
                    "status": "pass",
                    "comment": "Atende por benevolencia; criterio sem aplicabilidade na ligacao.",
                    "evidence_text": "",
                }
            ],
        }

        result = validate_evidence_against_transcription(payload, [])

        detail = result["details"][0]
        self.assertEqual(detail["evidence_validation"]["status"], "missing")
        self.assertEqual(detail["comment"], "Atende por benevolencia; criterio sem aplicabilidade na ligacao.")

    def test_summarize_evidence_coverage_requires_matched_evidence_for_evaluable_details(self):
        payload = {
            "details": [
                {
                    "criterionId": "saudacao",
                    "status": "pass",
                    "evidence_text": "Operador: bom dia.",
                    "evidence_validation": {"matched": True},
                },
                {
                    "criterionId": "senha",
                    "status": "fail",
                    "evidence_text": "",
                    "evidence_validation": {"matched": False, "status": "missing"},
                },
                {
                    "criterionId": "mudo",
                    "status": "pass",
                    "evidence_text": "",
                    "evidence_validation": {"matched": False, "status": "missing"},
                },
            ]
        }

        summary = summarize_evidence_coverage(payload)

        self.assertEqual(summary["evaluable_details"], 3)
        self.assertEqual(summary["matched_evidence"], 1)
        self.assertEqual(summary["missing_evidence"], 2)
        self.assertTrue(summary["review_recommended"])
        self.assertEqual(summary["matched_ratio"], 0.333)


if __name__ == "__main__":
    unittest.main()
