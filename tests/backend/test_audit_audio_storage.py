import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestAuditAudioStorage(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_audit_audio_storage_{uuid.uuid4().hex}.db",
        )
        self.storage_dir = tempfile.mkdtemp(prefix="audit_audio_storage_")
        self.original_db_name = database.DB_NAME
        self.original_storage_dir = os.environ.get("AUDIT_AUDIO_STORAGE_DIR")
        database.DB_NAME = self.db_path
        os.environ["AUDIT_AUDIO_STORAGE_DIR"] = self.storage_dir
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if self.original_storage_dir is None:
            os.environ.pop("AUDIT_AUDIO_STORAGE_DIR", None)
        else:
            os.environ["AUDIT_AUDIO_STORAGE_DIR"] = self.original_storage_dir
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        shutil.rmtree(self.storage_dir, ignore_errors=True)

    def _build_result(self, *, operator_name: str, operator_id: str, timestamp: str) -> AuditResult:
        return AuditResult(
            score=8.5,
            maxPossibleScore=10.0,
            summary="Resumo de auditoria com audio salvo",
            details=[
                AuditResultDetail(
                    criterionId="CR01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=8.5,
                    comment="Operador iniciou a chamada corretamente.",
                )
            ],
            transcription=[
                TranscriptionSegment(
                    start="00:00",
                    end="00:04",
                    text="Operador: bom dia, aqui e da nstech.",
                )
            ],
            operatorName=operator_name,
            operatorId=operator_id,
            timestamp=timestamp,
            source_type="audio",
        )

    def test_persist_audit_artifacts_saves_audio_for_new_audit(self):
        result = self._build_result(
            operator_name="Alice QA",
            operator_id="OP-001",
            timestamp="2026-03-12T16:00:00",
        )

        audit_id = database.persist_audit_artifacts(
            result,
            from_cache=False,
            input_hash="hash-audio-new",
            alert_id="alerta-1",
            alert_label="Alerta Teste",
            operator_id="OP-001",
            sector_id="bas",
            audio_bytes=b"RIFFdemo-audio",
            audio_mime_type="audio/wav",
            original_filename="ligacao_bas.wav",
        )

        self.assertIsInstance(audit_id, int)
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        media = database.get_audit_media_record(audit_id)

        self.assertIsNotNone(audit)
        self.assertTrue(audit["audio_available"])
        self.assertEqual(audit["audio_mime_type"], "audio/wav")
        self.assertEqual(audit["audio_original_filename"], "ligacao_bas.wav")
        self.assertEqual(audit["audio_size_bytes"], len(b"RIFFdemo-audio"))
        self.assertIsNotNone(media)

        stored_path = Path(self.storage_dir) / media["audio_storage_path"]
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_path.read_bytes(), b"RIFFdemo-audio")

    def test_persist_audit_artifacts_backfills_audio_for_cached_audit(self):
        result = self._build_result(
            operator_name="Bruno QA",
            operator_id="OP-002",
            timestamp="2026-03-12T16:15:00",
        )

        cached_audit_id = database.save_audit(
            result,
            input_hash="hash-audio-cache",
            alert_id="alerta-2",
            alert_label="Alerta Cache",
            operator_id="OP-002",
            sector_id="fenix",
        )

        attached_audit_id = database.persist_audit_artifacts(
            result,
            from_cache=True,
            input_hash="hash-audio-cache",
            audio_bytes=b"ID3cached-audio",
            audio_mime_type="audio/mpeg",
            original_filename="ligacao_fenix.mp3",
        )

        self.assertEqual(attached_audit_id, cached_audit_id)
        audit = audits.get_audit_by_id(database.get_connection, cached_audit_id)
        media = database.get_audit_media_record(cached_audit_id)

        self.assertIsNotNone(audit)
        self.assertTrue(audit["audio_available"])
        self.assertEqual(audit["audio_mime_type"], "audio/mpeg")
        self.assertEqual(audit["audio_original_filename"], "ligacao_fenix.mp3")
        self.assertIsNotNone(media)

        stored_path = Path(self.storage_dir) / media["audio_storage_path"]
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_path.read_bytes(), b"ID3cached-audio")


if __name__ == "__main__":
    unittest.main()
