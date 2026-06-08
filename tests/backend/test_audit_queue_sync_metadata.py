"""Regression: the manual audit flow must persist audit_input_hash on the
review queue metadata, matching the automation flow contract.

Background: the kickoff of Module 2 (`docs/reviews/module-2-auditoria-kickoff-2026-04-09.md`)
flagged that a real case ended up with `fila_revisao_classificacao.status = 'audited'`
but without a locatable `audit_input_hash`. Root cause was asymmetry between the
two sync paths:

- `automation._audit_single_item` (batch): persists both `audit_id` and `audit_input_hash`.
- `database.persist_audit_artifacts._sync_queue_as_audited` (manual upload): used
  to persist only `audit_id`, leaving the queue orphaned for any crosslink that
  relies on `audit_input_hash`.

This test pins the symmetric contract.
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from db.domain_constants import REVIEW_QUEUE_STATUS_AUDITED


class TestManualAuditQueueSyncMetadata(unittest.TestCase):
    def _make_result(self):
        return SimpleNamespace(
            score=9.0,
            maxPossibleScore=10.0,
            summary="resumo",
            details=[],
            transcription=[],
            operatorName="Operador Teste",
            operatorId="OP-123",
            timestamp="2026-04-14T09:00:00",
            source_type="audio",
        )

    @patch.object(database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(database, "_attach_audio_to_audit_record")
    @patch.object(database, "save_audit", return_value=42)
    @patch("repositories.operators.buscar_colaborador_por_id_huawei", return_value=None)
    @patch("repositories.operators.buscar_colaborador_por_nome", return_value=None)
    def test_manual_persist_includes_audit_input_hash_in_queue_metadata(
        self,
        _mock_buscar_nome,
        _mock_buscar_huawei,
        _mock_save,
        _mock_attach,
        mock_update_queue,
    ):
        result = self._make_result()

        audit_id = database.persist_audit_artifacts(
            result,
            from_cache=False,
            input_hash="manual-hash-abc",
            alert_id="alert-1",
            alert_label="Alerta Teste",
            operator_id="OP-123",
            sector_id="logistica",
            audio_bytes=b"fake-audio",
            audio_mime_type="audio/wav",
            original_filename="ligacao.wav",
        )

        self.assertEqual(audit_id, 42)
        mock_update_queue.assert_called_once()

        _, kwargs = mock_update_queue.call_args
        self.assertEqual(kwargs["status"], REVIEW_QUEUE_STATUS_AUDITED)

        metadata = kwargs["metadata_merge"]
        self.assertEqual(metadata["audit_id"], 42)
        self.assertEqual(
            metadata["audit_input_hash"],
            "manual-hash-abc",
            msg=(
                "Manual audit flow must persist audit_input_hash on queue metadata "
                "to keep symmetry with automation._audit_single_item and allow "
                "crosslink lookups from queue to audits table."
            ),
        )
        self.assertIn("audited_at", metadata)


if __name__ == "__main__":
    unittest.main()
