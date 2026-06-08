import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch, ANY

from fastapi import HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database  # noqa: E402
from routers.audit import get_audit_draft, run_reevaluate_audit, save_audit_draft  # noqa: E402
from routers.system import force_send_to_supervisor, save_to_dashboard  # noqa: E402
from schemas import (  # noqa: E402
    AuditAlert,
    AuditCriterion,
    AuditResult,
    AuditResultDetail,
    ReevaluateRequest,
    TranscriptionSegment,
)


def _build_result(*, score: float = 8.0, input_hash: str | None = "hash-edit") -> AuditResult:
    return AuditResult(
        score=score,
        maxPossibleScore=10.0,
        summary="Resumo",
        ai_feedback="Feedback",
        details=[
            AuditResultDetail(
                criterionId="C01",
                label="Saudacao",
                status="pass" if score else "fail",
                weight=10.0,
                obtainedScore=score,
                comment="Comentario",
            )
        ],
        transcription=[TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde")],
        operatorName="Operadora",
        operatorId="",
        timestamp="2026-04-20T10:00:00",
        input_hash=input_hash,
        source_type="audio",
    )


class TestAuditEditPersistence(unittest.TestCase):
    @patch("db.database._sync_arquivo_salvo_for_audit")
    @patch("repositories.audits.update_audit_result", return_value=42)
    def test_update_audit_result_syncs_archive_when_hash_is_found(
        self,
        _mock_update,
        mock_sync,
    ):
        updated_id = database.update_audit_result("hash-edit", _build_result(score=5.0))

        self.assertEqual(updated_id, 42)
        mock_sync.assert_called_once_with(42)

    @patch("db.database._sync_arquivo_salvo_for_audit")
    @patch("repositories.audits.update_audit_result", return_value=None)
    def test_update_audit_result_does_not_sync_when_hash_is_unknown(
        self,
        _mock_update,
        mock_sync,
    ):
        updated_id = database.update_audit_result("hash-ausente", _build_result(score=5.0))

        self.assertIsNone(updated_id)
        mock_sync.assert_not_called()

    @patch("routers.system.database.queue_audit_for_supervisor_review")
    @patch("repositories.audits.get_audit_by_id", return_value={"id": 42, "status": "pending_approval"})
    @patch("routers.system.database.update_audit_result", return_value=42)
    @patch("repositories.audits.get_audit_by_hash", return_value=_build_result())
    def test_save_existing_audit_updates_score_without_forcing_archive_status(
        self,
        _mock_get_by_hash,
        mock_update,
        _mock_get_by_id,
        mock_queue,
    ):
        response = save_to_dashboard(_build_result(score=5.0), _user={"username": "admin", "role": "admin"})

        self.assertTrue(response["success"])
        self.assertEqual(response["audit_id"], 42)
        self.assertEqual(response["review_status"], "pending_approval")
        mock_update.assert_called_once()
        mock_queue.assert_not_called()

    @patch(
        "repositories.audits.get_audit_by_id",
        side_effect=[
            {"id": 42, "status": "awaiting_pair"},
            {"id": 42, "status": "pending_approval"},
        ],
    )
    @patch("routers.system.database.update_audit_status")
    def test_force_send_uses_database_status_wrapper_and_returns_persisted_status(
        self,
        mock_update_status,
        _mock_get_by_id,
    ):
        response = force_send_to_supervisor(42, _user={"username": "admin", "role": "admin"})

        mock_update_status.assert_called_once_with(42, "pending_approval")
        self.assertTrue(response["success"])
        self.assertEqual(response["audit_id"], 42)
        self.assertEqual(response["review_status"], "pending_approval")

    @patch("repositories.audits.get_audit_by_id", return_value={"id": 42, "status": "approved"})
    @patch("routers.system.database.update_audit_status")
    def test_force_send_rejects_non_archived_audit(
        self,
        mock_update_status,
        _mock_get_by_id,
    ):
        with self.assertRaises(HTTPException) as ctx:
            force_send_to_supervisor(42, _user={"username": "admin", "role": "admin"})

        self.assertEqual(ctx.exception.status_code, 409)
        mock_update_status.assert_not_called()

    @patch("routers.audit.database.update_audit_result_by_id")
    @patch("routers.audit.get_supervisor_audit_for_user", return_value={"id": 42})
    @patch("routers.audit.database.get_latest_audit_id_by_input_hash", return_value=42)
    @patch("routers.audit.reevaluate_audit", new_callable=AsyncMock)
    def test_reevaluate_preserves_input_hash_and_persists_authorized_audit(
        self,
        mock_reevaluate,
        mock_get_latest,
        mock_authorize,
        mock_update,
    ):
        mock_reevaluate.return_value = _build_result(score=5.0, input_hash=None)
        request = ReevaluateRequest(
            transcription=[TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde editado")],
            alert=AuditAlert(
                id="alerta",
                label="Alerta",
                criteria=[AuditCriterion(id="C01", label="Saudacao", weight=10.0)],
            ),
            operator_name="Operadora",
            operator_id="",
            sector_id="cadastro",
            input_hash="hash-edit",
        )

        result = asyncio.run(run_reevaluate_audit(request, _user={"username": "admin", "role": "admin"}))

        self.assertEqual(result.input_hash, "hash-edit")
        mock_get_latest.assert_called_once_with("hash-edit")
        mock_authorize.assert_called_once_with({"username": "admin", "role": "admin"}, 42)
        mock_update.assert_called_once()
        self.assertEqual(mock_update.call_args.args[0], 42)

    @patch("routers.audit.database.update_audit_result_by_id")
    @patch("routers.audit.get_supervisor_audit_for_user", side_effect=HTTPException(status_code=403))
    @patch("routers.audit.database.get_latest_audit_id_by_input_hash", return_value=42)
    @patch("routers.audit.reevaluate_audit", new_callable=AsyncMock)
    def test_reevaluate_rejects_unauthorized_input_hash_before_ai_call(
        self,
        mock_reevaluate,
        _mock_get_latest,
        _mock_authorize,
        mock_update,
    ):
        request = ReevaluateRequest(
            transcription=[TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde editado")],
            alert=AuditAlert(
                id="alerta",
                label="Alerta",
                criteria=[AuditCriterion(id="C01", label="Saudacao", weight=10.0)],
            ),
            operator_name="Operadora",
            operator_id="",
            sector_id="cadastro",
            input_hash="hash-edit",
        )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run_reevaluate_audit(request, _user={"username": "supervisor", "role": "supervisor"}))

        self.assertEqual(ctx.exception.status_code, 403)
        mock_reevaluate.assert_not_awaited()
        mock_update.assert_not_called()

    @patch("repositories.audits.upsert_audit_draft")
    def test_save_audit_draft_uses_frontend_json_fields_and_username_scope(self, mock_upsert):
        payload = {
            "details_json": '[{"criterionId":"C01"}]',
            "transcription_json": '[{"text":"fala"}]',
        }

        result = asyncio.run(save_audit_draft("hash-edit", payload, user={"username": "auditor"}))

        self.assertEqual(result, {"ok": True})
        mock_upsert.assert_called_once()
        self.assertEqual(mock_upsert.call_args.args[1:], ("hash-edit", "auditor", payload["details_json"], payload["transcription_json"]))

    @patch(
        "repositories.audits.get_audit_draft",
        return_value={
            "details_json": '[{"criterionId":"C01"}]',
            "transcription_json": '[{"text":"fala"}]',
            "updated_at": "2026-05-20T10:00:00",
        },
    )
    def test_get_audit_draft_returns_frontend_shape(self, mock_get):
        result = asyncio.run(get_audit_draft("hash-edit", user={"username": "auditor"}))

        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[1:], ("hash-edit", "auditor"))
        self.assertTrue(result["ok"])
        self.assertEqual(result["draft"]["details_json"], '[{"criterionId":"C01"}]')
        self.assertEqual(result["draft"]["transcription_json"], '[{"text":"fala"}]')


if __name__ == "__main__":
    unittest.main()
