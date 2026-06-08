import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import audit as core_audit  # noqa: E402
from core.audit_pipeline import (  # noqa: E402
    AUDIT_ORIGIN_MANUAL_UPLOAD,
    AUDIT_ORIGIN_TELEFONIA_MANUAL,
    attach_pipeline_context_to_audio_quality,
    build_manual_upload_context,
    build_queue_audit_context,
    repair_queue_audit_context,
)
from schemas import AuditAlert, AuditCriterion  # noqa: E402


class TestAuditPipelineContext(unittest.TestCase):
    def test_queue_context_repairs_unknown_alert_from_catalog(self):
        item = {
            "input_hash": "queue-hash",
            "nome_arquivo": "call.wav",
            "setor_previsto": "",
            "alerta_previsto": "desconhecido",
            "operador_previsto": "Operador QA",
            "confianca": 0.42,
            "motivos_revisao": ["baixa_confianca"],
            "metadata": {
                "operator_sector_id": "logistica",
                "classified_audio_path": "call.wav",
                "classification_status": "done",
            },
        }

        with patch(
            "core.classification.align_classification_with_catalog",
            return_value={
                "sector_id": "logistica",
                "alert_id": "LOGISTICA-PARADA",
                "alert_label": "Parada",
            },
        ):
            context = repair_queue_audit_context(
                build_queue_audit_context(item, origin=AUDIT_ORIGIN_TELEFONIA_MANUAL)
            )

        self.assertEqual(context.origin, AUDIT_ORIGIN_TELEFONIA_MANUAL)
        self.assertEqual(context.sector_id, "logistica")
        self.assertEqual(context.alert_id, "LOGISTICA-PARADA")
        self.assertTrue(context.context_repair_applied)
        self.assertEqual(context.media_path, "call.wav")
        self.assertEqual(context.classification_confidence, 0.42)
        self.assertEqual(context.review_reasons, ["baixa_confianca"])

    def test_queue_context_preserves_huawei_reason_metadata_for_audit(self):
        context = build_queue_audit_context(
            {
                "input_hash": "queue-hash",
                "nome_arquivo": "call.wav",
                "setor_previsto": "logistica",
                "alerta_previsto": "LOGISTICA-PARADA",
                "metadata": {
                    "huawei_call_reason": "PARADA",
                    "huawei_call_reason_code": "P01",
                    "native_reason_match": True,
                    "native_reason_targets": ["PARADA"],
                },
            },
            origin=AUDIT_ORIGIN_TELEFONIA_MANUAL,
        )

        audio_quality = attach_pipeline_context_to_audio_quality({}, context)

        source_metadata = audio_quality["audit_pipeline"]["source_metadata"]
        self.assertEqual(source_metadata["huawei_call_reason"], "PARADA")
        self.assertEqual(source_metadata["native_reason_targets"], ["PARADA"])


class TestAuditPipelineMetadata(unittest.IsolatedAsyncioTestCase):
    async def test_process_audio_attaches_pipeline_context_and_transcription_strategy(self):
        alert = AuditAlert(
            id="ALERTA",
            label="Alerta",
            context="Contexto",
            criteria=[AuditCriterion(id="C1", label="Saudacao", weight=10.0)],
        )
        context = build_manual_upload_context(
            filename="manual.wav",
            source_type="audio/wav",
            sector_id="logistica",
            alert_id=alert.id,
            alert_label=alert.label,
            operator_name="Operador QA",
            operator_id="MAT-1",
        )
        evaluation = {
            "summary": "Resumo",
            "ai_feedback": "Feedback",
            "details": [
                {
                    "criterionId": "C1",
                    "status": "pass",
                    "comment": "OK",
                    "timestamp": "00:00 - 00:01",
                    "evidence_text": "Operador: bom dia",
                }
            ],
            "fatal_flags": [],
        }

        transcribe_mock = AsyncMock(
            return_value=(
                [{"start": "00:00", "end": "00:01", "text": "Operador: bom dia"}],
                {
                    "selected_strategy": "fast",
                    "selected_provider": "Azure Fast Transcription",
                    "selected_reason": "accepted",
                },
            )
        )

        with patch.dict(os.environ, {"AUDIT_ALLOW_OFFICIAL_CRITERIA_TEST_FALLBACK": "true"}, clear=False):
            with patch.object(core_audit, "DETERMINISTIC_MODE", False):
                with patch.object(
                    core_audit,
                    "transcribe_audio",
                    new=transcribe_mock,
                ):
                    with patch.object(core_audit, "evaluate_with_ai_priority", new=AsyncMock(return_value=evaluation)):
                        result, _input_hash, _from_cache = await core_audit.process_audit_with_ai(
                            b"RIFFdemo",
                            "audio/wav",
                            alert,
                            "Operador QA",
                            "MAT-1",
                            "logistica",
                            pipeline_context=context,
                        )

        pipeline = result.audio_quality["audit_pipeline"]
        self.assertEqual(pipeline["origin"], AUDIT_ORIGIN_MANUAL_UPLOAD)
        self.assertEqual(pipeline["sector_id"], "logistica")
        self.assertEqual(pipeline["alert_id"], "ALERTA")
        self.assertEqual(pipeline["transcription_strategy"]["selected_strategy"], "fast")
        self.assertTrue(transcribe_mock.await_args.kwargs["allow_degraded_hybrid_fallback"])


if __name__ == "__main__":
    unittest.main()
