import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.audit_evaluator import _normalize_validate_and_score_evaluation  # noqa: E402
from core.qualification_audit import apply_qualification_result_override  # noqa: E402
from schemas import AuditAlert, AuditCriterion  # noqa: E402


class TestQualificationAudit(unittest.TestCase):
    def setUp(self):
        self.qualification = AuditCriterion(
            id="q1",
            label="O operador realizou a qualificação do atendimento corretamente",
            weight=0.3,
        )
        self.other = AuditCriterion(id="c1", label="Saudacao?", weight=0.7)
        self.alert = AuditAlert(
            id="LOGISTICA-PARADA",
            label="Parada Indevida - Motorista",
            context="Ligacao sobre parada indevida.",
            criteria=[self.qualification, self.other],
        )

    def _audio_quality(self, reason: str, **extra):
        source_metadata = {"huawei_call_reason": reason}
        source_metadata.update(extra)
        return {"audit_pipeline": {"source_metadata": source_metadata}}

    def test_marks_qualification_as_pass_when_huawei_reason_matches_alert(self):
        payload = {
            "summary": "Resumo",
            "details": [{"criterionId": "q1", "status": "fail", "comment": "IA nao tem metadata"}],
            "fatal_flags": [],
        }

        result = apply_qualification_result_override(
            payload,
            [self.qualification],
            alert=self.alert,
            audio_quality=self._audio_quality("PARADA"),
            sector_id="logistica",
        )

        detail = result["details"][0]
        self.assertEqual(detail["status"], "pass")
        self.assertIn("Qualificação validada por motivo Huawei: PARADA", detail["comment"])
        self.assertIn("Motivo Huawei: PARADA", detail["evidence_text"])
        self.assertEqual(detail["evidence_validation"]["method"], "external_metadata")
        self.assertEqual(detail["evidence_validation"]["status"], "pass")

    def test_marks_qualification_as_pass_when_huawei_reason_does_not_match_alert(self):
        payload = {
            "summary": "Resumo",
            "details": [{"criterionId": "q1", "status": "pass", "comment": "IA sem metadata"}],
            "fatal_flags": [],
        }

        result = apply_qualification_result_override(
            payload,
            [self.qualification],
            alert=self.alert,
            audio_quality=self._audio_quality("ASSUNTO ADMINISTRATIVO"),
            sector_id="logistica",
        )

        detail = result["details"][0]
        self.assertEqual(detail["status"], "pass")
        self.assertIn("Qualificação validada por motivo Huawei", detail["comment"])

    def test_does_not_apply_to_risk_sectors(self):
        payload = {
            "summary": "Resumo",
            "details": [{"criterionId": "q1", "status": "fail", "comment": "mantem manual"}],
            "fatal_flags": [],
        }

        result = apply_qualification_result_override(
            payload,
            [self.qualification],
            alert=AuditAlert(id="UTI-PARADA-MOT", label="Parada Indevida - Motorista", context="", criteria=[self.qualification]),
            audio_quality=self._audio_quality("PARADA"),
            sector_id="uti",
        )

        self.assertEqual(result, payload)

    def test_normalization_applies_override_before_evidence_summary(self):
        payload = {
            "summary": "Resumo",
            "details": [
                {"criterionId": "q1", "status": "fail", "comment": "IA nao sabe"},
                {
                    "criterionId": "c1",
                    "status": "pass",
                    "comment": "Saudou",
                    "timestamp": "00:00 - 00:01",
                    "evidence_text": "Operador: bom dia",
                },
            ],
            "fatal_flags": [],
        }

        normalized = _normalize_validate_and_score_evaluation(
            payload,
            [self.qualification, self.other],
            [{"start": "00:00", "end": "00:01", "text": "Operador: bom dia"}],
            alert=self.alert,
            audio_quality=self._audio_quality("PARADA"),
            sector_id="logistica",
        )

        details = {item["criterionId"]: item for item in normalized["details"]}
        self.assertEqual(details["q1"]["status"], "pass")
        self.assertEqual(details["q1"]["evidence_validation"]["method"], "external_metadata")
        self.assertEqual(normalized["evidence_quality"]["matched_evidence"], 1)


if __name__ == "__main__":
    unittest.main()
