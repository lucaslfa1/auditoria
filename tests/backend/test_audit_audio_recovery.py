from repositories import operators
import asyncio
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation as automation  # noqa: E402
from routers.audit import _recover_audit_audio_from_classified_queue, _safe_persist  # noqa: E402
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment  # noqa: E402


class TestAuditAudioRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path(__file__).resolve().parent / "_tmp_audit_audio_recovery"
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        self.classified_root = self.tmp_root / "classified"
        self.classified_root.mkdir(parents=True, exist_ok=True)
        self.original_classified_dir = os.environ.get("CLASSIFIED_AUDIO_STORAGE_DIR")
        os.environ["CLASSIFIED_AUDIO_STORAGE_DIR"] = str(self.classified_root)

    def tearDown(self):
        if self.original_classified_dir is None:
            os.environ.pop("CLASSIFIED_AUDIO_STORAGE_DIR", None)
        else:
            os.environ["CLASSIFIED_AUDIO_STORAGE_DIR"] = self.original_classified_dir
        shutil.rmtree(self.tmp_root, ignore_errors=True)

    def _audit_result(self) -> AuditResult:
        return AuditResult(
            score=8,
            maxPossibleScore=10,
            summary="Resumo",
            details=[
                AuditResultDetail(
                    criterionId="1",
                    label="Saudacao",
                    status="pass",
                    weight=10,
                    obtainedScore=10,
                    comment="Ok",
                )
            ],
            transcription=[TranscriptionSegment(start="00:00", end="00:01", text="teste")],
            operatorName="Operadora",
            operatorId="OP-1",
            input_hash="audit-hash",
            source_type="audio",
            # selected_strategy obrigatoria para o cache ser elegivel
            # (_satisfies_transcription_policy do candidate selector).
            audio_quality={"transcription_provider": {"selected_strategy": "fast"}},
        )

    def test_route_recovery_attaches_classified_audio_when_audit_file_is_missing(self):
        (self.classified_root / "queue.wav").write_bytes(b"RIFFrecovered")
        queue_item = {
            "nome_arquivo": "ligacao.wav",
            "metadata": {"classified_audio_path": "queue.wav"},
        }

        with patch(
            "routers.audit.database.obter_fila_revisao_classificacao_por_auditoria",
            return_value=queue_item,
        ) as find_queue:
            with patch(
                "routers.audit.database.attach_audio_to_audit_record",
                return_value={
                    "audio_storage_path": "2026/04/audit_31_hash.wav",
                    "audio_original_filename": "ligacao.wav",
                    "audio_mime_type": "audio/wav",
                    "audio_size_bytes": len(b"RIFFrecovered"),
                },
            ) as attach_audio:
                recovered = _recover_audit_audio_from_classified_queue(
                    31,
                    {"input_hash": "audit-hash"},
                    None,
                )

        self.assertEqual(recovered["audio_storage_path"], "2026/04/audit_31_hash.wav")
        find_queue.assert_called_once_with(31, "audit-hash")
        attach_audio.assert_called_once()
        kwargs = attach_audio.call_args.kwargs
        self.assertEqual(kwargs["audio_bytes"], b"RIFFrecovered")
        self.assertEqual(kwargs["audio_mime_type"], "audio/wav")
        self.assertEqual(kwargs["original_filename"], "ligacao.wav")
        self.assertEqual(kwargs["input_hash"], "audit-hash")

    def test_automation_attaches_audio_when_existing_audit_is_reused(self):
        (self.classified_root / "queue.wav").write_bytes(b"RIFFexisting")
        item = {
            "input_hash": "queue-hash",
            "nome_arquivo": "ligacao.wav",
            "setor_previsto": "bas",
            "alerta_previsto": "BAS-PRIORITARIO-POLICIA",
            "operador_previsto": "Operadora",
            "metadata": {"classified_audio_path": "queue.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador", return_value={"name": "Operadora"}):
            with patch("core.automation.compute_input_hash", return_value="audit-hash"):
                with patch("repositories.audits.get_audit_by_hash", return_value=self._audit_result()):
                    with patch("core.automation.database.persist_audit_artifacts", return_value=31) as persist:
                        with patch("core.automation._mark_item_status") as mark_status:
                            asyncio.run(automation._audit_single_item(item))

        persist.assert_called_once()
        persist_kwargs = persist.call_args.kwargs
        self.assertTrue(persist_kwargs["from_cache"])
        self.assertEqual(persist_kwargs["input_hash"], "audit-hash")
        self.assertEqual(persist_kwargs["audio_bytes"], b"RIFFexisting")
        self.assertEqual(persist_kwargs["audio_mime_type"], "audio/wav")
        self.assertEqual(persist_kwargs["original_filename"], "ligacao.wav")
        mark_status.assert_called_once()
        metadata_merge = mark_status.call_args.kwargs["metadata_merge"]
        self.assertEqual(metadata_merge["audit_id"], 31)
        self.assertEqual(metadata_merge["audit_input_hash"], "audit-hash")

    def test_classified_audio_loader_rejects_path_traversal(self):
        outside = self.tmp_root / "outside.wav"
        outside.write_bytes(b"RIFFoutside")
        (self.classified_root / "inside.wav").write_bytes(b"RIFFinside")

        self.assertIsNone(automation.load_classified_audio("../outside.wav"))
        self.assertIsNone(automation.open_classified_audio_stream("../outside.wav"))
        self.assertEqual(automation.load_classified_audio("inside.wav"), b"RIFFinside")

    def test_safe_persist_reraises_storage_failures(self):
        with patch("routers.audit.database.persist_audit_artifacts", side_effect=RuntimeError("storage failed")):
            with self.assertRaises(RuntimeError):
                _safe_persist(self._audit_result(), input_hash="audit-hash")


if __name__ == "__main__":
    unittest.main()
