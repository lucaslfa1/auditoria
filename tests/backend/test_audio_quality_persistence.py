import os
import sys
import unittest
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestAudioQualityPersistence(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_audio_quality_{uuid.uuid4().hex}.db"
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _build_result(self, *, score: float, audio_quality: dict | None, operator_name: str, timestamp: str):
        return AuditResult(
            score=score,
            maxPossibleScore=10.0,
            summary=f"Resumo {operator_name}",
            details=[
                AuditResultDetail(
                    criterionId="CR01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=score,
                    comment="Teste"
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:05", text="Operador: teste")
            ],
            operatorName=operator_name,
            operatorId=f"ID-{operator_name}",
            timestamp=timestamp,
            source_type="audio",
            audio_quality=audio_quality,
        )

    def test_save_and_load_audio_quality(self):
        result = self._build_result(
            score=9.0,
            audio_quality={
                "score": 0.32,
                "quality": "muito_baixa",
                "notes": ["Volume muito baixo"],
                "details": {"sample_rate": 8000},
                "review_recommended": True,
                "review_priority": "high",
                "review_reasons": ["score_de_diarizacao_muito_baixo"],
            },
            operator_name="Alice",
            timestamp="2026-03-03T13:00:00"
        )

        database.save_audit(
            result,
            input_hash="hash-audio-quality",
            alert_id="alerta-1",
            alert_label="Alerta Teste",
            operator_id="ID-Alice",
            sector_id="bas"
        )

        cached = audits.get_audit_by_hash(database.get_connection, "hash-audio-quality")
        self.assertIsNotNone(cached)
        self.assertEqual(cached.audit_scope, "call_quality")
        self.assertEqual(cached.audio_quality["quality"], "muito_baixa")
        self.assertEqual(cached.audio_quality["details"]["sample_rate"], 8000)
        self.assertTrue(cached.audio_quality["review_recommended"])
        self.assertEqual(cached.audio_quality["review_priority"], "high")

    def test_low_audio_quality_remains_in_call_metrics_and_incidents_are_disabled(self):
        valid_result = self._build_result(
            score=8.0,
            audio_quality={
                "score": 0.82,
                "quality": "boa",
                "notes": ["Qualidade adequada"],
                "details": {"sample_rate": 16000}
            },
            operator_name="Bruno",
            timestamp="2026-03-03T13:10:00"
        )
        invalid_result = self._build_result(
            score=1.0,
            audio_quality={
                "score": 0.22,
                "quality": "muito_baixa",
                "notes": ["78% de silencio"],
                "details": {"sample_rate": 8000}
            },
            operator_name="Carla",
            timestamp="2026-03-03T13:20:00"
        )

        database.save_audit(
            valid_result,
            input_hash="hash-valid",
            alert_id="alerta-1",
            alert_label="Alerta Bom",
            operator_id="ID-Bruno",
            sector_id="bas",
            status="approved"
        )
        database.save_audit(
            invalid_result,
            input_hash="hash-invalid",
            alert_id="alerta-2",
            alert_label="Alerta Infra",
            operator_id="ID-Carla",
            sector_id="bas",
            status="approved"
        )

        stats = database.get_stats()
        history = database.get_history(limit=10)
        incidents = database.get_technical_incidents(limit=10, sector_id="bas")

        self.assertEqual(stats["total_audits"], 2)
        self.assertEqual(stats["telephony_audits"], 0)
        self.assertEqual(stats["average_score"], 4.5)
        self.assertEqual(stats["average_score_percentage"], 45.0)
        self.assertEqual(len(history), 2)
        self.assertEqual({history[0]["operator"], history[1]["operator"]}, {"Bruno", "Carla"})
        self.assertEqual(incidents, [])


if __name__ == "__main__":
    unittest.main()
