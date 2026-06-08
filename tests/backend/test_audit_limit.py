"""Tests for the monthly audit limit (max 2 per operator per month)."""

import asyncio
import json
import os
import sys
import unittest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database
from repositories import audits
from repositories import operators
from repositories.common import CALL_QUALITY_SCOPE
from db.domain_constants import AUDIT_STATUS_DISCARDED
from repositories.audits import (
    _resolve_open_review_queue,
    get_audit_by_hash,
    get_audit_media_record_by_hash,
    get_operator_audit_count_for_month,
)
from routers.audit import run_audit
from schemas import AuditAlert, AuditCriterion, AuditResult, AuditResultDetail, TranscriptionSegment


class TestAuditLimitRouter(unittest.TestCase):
    """Tests for the HTTP 429 block when limit is exceeded."""

    def _auditable_operator(self, name="Joao", operator_id="OP-001"):
        return {"name": name, "matricula": operator_id, "preferredId": operator_id}

    def test_audit_limit_exceeded_returns_429(self):
        background_tasks = MagicMock()
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value=self._auditable_operator("Joao", "OP-001"),
        ), patch("routers.audit.get_operator_audit_count_for_month") as mock_count, patch(
            "routers.audit._get_configured_monthly_audit_quota",
            return_value=2,
        ):
            mock_count.return_value = 2

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(run_audit(
                    _user=user,
                    file=file_mock,
                    alert_json=alert_json,
                    operator_name="Joao",
                    operator_id="OP-001",
                    sector_id=None,
                    audio_date="2026-03-10",
                    force_override=False,
                ))
            self.assertEqual(ctx.exception.status_code, 429)
            self.assertIn("Limite mensal excedido", ctx.exception.detail)
            self.assertIn("03/2026", ctx.exception.detail)
            mock_count.assert_called_once_with(
                database.get_connection,
                "Joao",
                2026,
                3,
                operator_id="OP-001",
            )

    def test_audit_invalid_audio_date_returns_400(self):
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run_audit(
                _user=user,
                file=file_mock,
                alert_json=alert_json,
                operator_name="Joao",
                operator_id="OP-001",
                sector_id=None,
                audio_date="10/03/2026",
                force_override=False,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Data do audio invalida", ctx.exception.detail)

    def test_audit_limit_3_also_blocked(self):
        """Operator with 3 existing audits should still be blocked."""
        background_tasks = MagicMock()
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.wav"
        file_mock.read = AsyncMock(return_value=b"RIFF")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value=self._auditable_operator("Maria", "OP-002"),
        ), patch("routers.audit.get_operator_audit_count_for_month") as mock_count, patch(
            "routers.audit._get_configured_monthly_audit_quota",
            return_value=2,
        ):
            mock_count.return_value = 3

            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(run_audit(
                    _user=user,
                    file=file_mock,
                    alert_json=alert_json,
                    operator_name="Maria",
                    operator_id=None,
                    sector_id=None,
                    force_override=False,
                ))
            self.assertEqual(ctx.exception.status_code, 429)

    def test_audit_limit_ok_passes_through(self):
        """Operator with 1 audit should be allowed to proceed."""
        background_tasks = MagicMock()
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value=self._auditable_operator("Joao", "OP-001"),
        ), patch("routers.audit.get_operator_audit_count_for_month") as mock_count, patch(
            "routers.audit._get_configured_monthly_audit_quota",
            return_value=2,
        ):
            mock_count.return_value = 1

            with patch("routers.audit.process_audit_with_ai", new_callable=AsyncMock) as mock_process:
                fake_result = MagicMock()
                fake_result.timestamp = "2026-01-01"
                mock_process.return_value = (fake_result, "hash", False)

                with patch("routers.audit.ensure_supported_upload") as mock_ensure:
                    mock_ensure.return_value = "audio/mpeg"

                    with patch("routers.audit.database.persist_audit_artifacts") as mock_persist:
                        resp = asyncio.run(run_audit(
                            _user=user,
                            file=file_mock,
                            alert_json=alert_json,
                            operator_name="Joao",
                            operator_id=None,
                            sector_id=None,
                        ))
                    self.assertIsNotNone(resp)
                    mock_persist.assert_called_once()
                    self.assertEqual(mock_persist.call_args.kwargs["audio_bytes"], b"fake")
                    self.assertEqual(mock_persist.call_args.kwargs["audio_mime_type"], "audio/mpeg")

    def test_manual_audit_respects_configured_quota_above_two(self):
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")
        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value=self._auditable_operator("Joao", "OP-001"),
        ), patch("routers.audit.get_operator_audit_count_for_month", return_value=2), patch(
            "routers.audit._get_configured_monthly_audit_quota",
            return_value=3,
        ), patch("routers.audit.process_audit_with_ai", new_callable=AsyncMock) as mock_process, patch(
            "routers.audit.ensure_supported_upload",
            return_value="audio/mpeg",
        ), patch("routers.audit.database.persist_audit_artifacts") as mock_persist:
            fake_result = MagicMock()
            mock_process.return_value = (fake_result, "hash", False)

            resp = asyncio.run(run_audit(
                _user=user,
                file=file_mock,
                alert_json=alert_json,
                operator_name="Joao",
                operator_id="OP-001",
                sector_id=None,
                force_override=False,
            ))

        self.assertIs(resp, fake_result)
        mock_persist.assert_called_once()

    def test_manual_upload_revalidates_alert_criteria_from_catalog(self):
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")
        alert_json = json.dumps({
            "id": "ALERTA",
            "label": "Payload antigo",
            "context": "Payload antigo",
            "criteria": [{"id": "OLD", "label": "Antigo", "weight": 1.0}],
        })
        canonical_alert = AuditAlert(
            id="ALERTA",
            label="Catalogo",
            context="Catalogo",
            criteria=[AuditCriterion(id="NEW", label="Novo", weight=10.0)],
        )

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value=self._auditable_operator("Joao", "OP-001"),
        ), patch("routers.audit.get_operator_audit_count_for_month", return_value=0), patch(
            "routers.audit._get_configured_monthly_audit_quota",
            return_value=2,
        ), patch("core.automation._build_alert_from_classification", return_value=canonical_alert), patch(
            "routers.audit.process_audit_with_ai",
            new_callable=AsyncMock,
        ) as mock_process, patch("routers.audit.ensure_supported_upload", return_value="audio/mpeg"), patch(
            "routers.audit.database.persist_audit_artifacts"
        ):
            fake_result = MagicMock()
            mock_process.return_value = (fake_result, "hash", False)

            asyncio.run(run_audit(
                _user=user,
                file=file_mock,
                alert_json=alert_json,
                operator_name="Joao",
                operator_id="OP-001",
                sector_id="logistica",
                force_override=False,
            ))

        used_alert = mock_process.call_args.args[2]
        self.assertEqual(used_alert.label, "Catalogo")
        self.assertEqual([criterion.id for criterion in used_alert.criteria], ["NEW"])

    def test_audit_missing_operator_name_returns_400(self):
        """When operator_name is empty, the router should return 400."""
        background_tasks = MagicMock()
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run_audit(
                _user=user,
                file=file_mock,
                alert_json=alert_json,
                operator_name="",
                operator_id=None,
                sector_id=None,
            ))
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("obrigatório", ctx.exception.detail)

    def test_audit_unknown_operator_returns_400_before_quota(self):
        user = {"username": "test", "role": "admin"}
        file_mock = MagicMock()
        file_mock.filename = "test.mp3"
        file_mock.read = AsyncMock(return_value=b"fake")

        alert_json = json.dumps({
            "id": "test", "sector": "test", "label": "test",
            "context": "test", "criteria": [],
        })

        with patch("repositories.operators.resolve_auditable_colaborador", return_value=None), patch(
            "routers.audit.get_operator_audit_count_for_month"
        ) as mock_count:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(run_audit(
                    _user=user,
                    file=file_mock,
                    alert_json=alert_json,
                    operator_name="Fantasma",
                    operator_id="GHOST-001",
                    sector_id="logistica",
                    force_override=False,
                ))

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Operador nao auditavel", ctx.exception.detail)
        mock_count.assert_not_called()


class TestAuditLimitRepositoryQuery(unittest.TestCase):
    """Unit tests for quota identity/date filtering without a real database."""

    class _Cursor:
        def __init__(self, row=(2,), search_name="ana souza", search_id="op-777"):
            self.row = row
            self.search_name = search_name
            self.search_id = search_id
            self.query = ""
            self.params = None

        def execute(self, query, params):
            self.query = query
            self.params = params

        def mogrify(self, template, params):
            return (template % params).encode('utf-8') if isinstance(template, str) else template

        def fetchone(self):
            return self.row
            
        def fetchall(self):
            return [(self.search_name, self.search_id, self.row[0])]

    class _Connection:
        def __init__(self, cursor):
            self._cursor = cursor
            self.closed = False

        def cursor(self):
            return self._cursor

        def close(self):
            self.closed = True

    def test_count_uses_audit_date_and_operator_identity(self):
        cursor = self._Cursor(row=(2,))
        conn = self._Connection(cursor)

        count = get_operator_audit_count_for_month(
            lambda: conn,
            "Ana Souza",
            2026,
            4,
            operator_id="OP-777",
        )

        self.assertEqual(count, 2)
        self.assertIn("COUNT(DISTINCT", cursor.query)
        self.assertIn("COALESCE(audit_date, timestamp)", cursor.query)
        self.assertIn("operator_id", cursor.query)
        self.assertIn("operator_name", cursor.query)
        self.assertIn("status", cursor.query)
        self.assertIn("op-777", cursor.query.lower())
        self.assertEqual(
            cursor.params,
            (
                "2026-04-01",
                "2026-05-01",
                CALL_QUALITY_SCOPE,
                CALL_QUALITY_SCOPE,
                "discarded",
            ),
        )
        self.assertTrue(conn.closed)

    def test_hash_cache_lookup_ignores_discarded_audits(self):
        cursor = self._Cursor(row=None)
        conn = self._Connection(cursor)

        result = get_audit_by_hash(lambda: conn, "hash-descartado")

        self.assertIsNone(result)
        self.assertIn("discarded_at IS NULL", cursor.query)
        self.assertIn("COALESCE(status, '') <> %s", cursor.query)
        self.assertIn("ORDER BY id DESC", cursor.query)
        self.assertEqual(cursor.params, ("hash-descartado", AUDIT_STATUS_DISCARDED))
        self.assertTrue(conn.closed)

    def test_hash_media_lookup_ignores_discarded_audits(self):
        cursor = self._Cursor(row=None)
        conn = self._Connection(cursor)

        result = get_audit_media_record_by_hash(lambda: conn, "hash-descartado")

        self.assertIsNone(result)
        self.assertIn("discarded_at IS NULL", cursor.query)
        self.assertIn("COALESCE(status, '') <> %s", cursor.query)
        self.assertIn("ORDER BY id DESC", cursor.query)
        self.assertEqual(cursor.params, ("hash-descartado", AUDIT_STATUS_DISCARDED))
        self.assertTrue(conn.closed)

    def test_count_can_match_by_operator_id_without_name(self):
        cursor = self._Cursor(row=(1,), search_name="", search_id="op-123")
        conn = self._Connection(cursor)

        count = get_operator_audit_count_for_month(
            lambda: conn,
            "",
            2026,
            12,
            operator_id="OP-123",
        )

        self.assertEqual(count, 1)
        self.assertIn("operator_id", cursor.query)
        self.assertEqual(len(cursor.params), 5)
        self.assertIn("op-123", cursor.query.lower())

    def test_pair_queue_uses_operator_id_plus_legacy_blank_id_name(self):
        class Cursor:
            def __init__(self):
                self.query = ""
                self.params = None

            def execute(self, query, params):
                self.query = query
                self.params = params

            def fetchall(self):
                return []

        cursor = Cursor()

        rows = _resolve_open_review_queue(
            cursor,
            operator_name="Ana Souza",
            operator_id="OP-777",
        )

        self.assertEqual(rows, [])
        self.assertIn("operator_id", cursor.query)
        self.assertIn("operator_name", cursor.query)
        self.assertIn(" OR ", cursor.query.upper())
        self.assertIn("TRIM(COALESCE(operator_id, '')) = ''", cursor.query)
        self.assertEqual(cursor.params[0], "OP-777")
        self.assertEqual(cursor.params[1], "Ana Souza")


@unittest.skip("Requires PostgreSQL — uses legacy DB_NAME pattern incompatible with PG migration")
class TestAuditLimitRepository(unittest.TestCase):
    """Integration tests for get_operator_audit_count_for_month with real DB."""

    def setUp(self):
        self.db_path = os.path.join(
            os.path.dirname(__file__),
            f"test_audit_limit_{uuid.uuid4().hex}.db",
        )
        self.original_db_name = database.DB_NAME
        database.DB_NAME = self.db_path
        database.init_db()

    def tearDown(self):
        database.DB_NAME = self.original_db_name
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _make_result(self, name="Operador Teste"):
        return AuditResult(
            score=8.0,
            maxPossibleScore=10.0,
            summary="Test audit",
            details=[
                AuditResultDetail(
                    criterionId="C01", label="Saudacao", status="pass",
                    weight=10.0, obtainedScore=10.0, comment="OK",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde")
            ],
            operatorName=name,
            operatorId="OP-001",
            timestamp="2026-04-12T12:00:00",
            source_type="audio",
        )

    def test_count_zero_when_no_audits(self):
        count = get_operator_audit_count_for_month(
            database.get_connection, "Operador Inexistente", 2026, 4,
        )
        self.assertEqual(count, 0)

    def test_count_increments_with_audits_in_same_month(self):
        result = self._make_result()
        database.save_audit(result, input_hash="limit-1", sector_id="fenix")
        database.save_audit(result, input_hash="limit-2", sector_id="fenix")

        count = get_operator_audit_count_for_month(
            database.get_connection, "Operador Teste", 2026, 4,
        )
        self.assertEqual(count, 2)

    def test_count_does_not_include_different_month(self):
        result = self._make_result()
        database.save_audit(result, input_hash="limit-mar", sector_id="fenix")

        # March should have 0 because the audit timestamp is April
        count = get_operator_audit_count_for_month(
            database.get_connection, "Operador Teste", 2026, 3,
        )
        self.assertEqual(count, 0)

        # April should have 1
        count_april = get_operator_audit_count_for_month(
            database.get_connection, "Operador Teste", 2026, 4,
        )
        self.assertEqual(count_april, 1)

    def test_count_is_case_insensitive(self):
        result = self._make_result("Maria Santos")
        database.save_audit(result, input_hash="limit-ci", sector_id="uti")

        count_lower = get_operator_audit_count_for_month(
            database.get_connection, "maria santos", 2026, 4,
        )
        count_upper = get_operator_audit_count_for_month(
            database.get_connection, "MARIA SANTOS", 2026, 4,
        )
        self.assertEqual(count_lower, 1)
        self.assertEqual(count_upper, 1)

    def test_count_empty_name_returns_zero(self):
        count = get_operator_audit_count_for_month(
            database.get_connection, "", 2026, 4,
        )
        self.assertEqual(count, 0)

    def test_december_boundary(self):
        """Audits in December should not leak into January count."""
        result = self._make_result()
        result_dec = AuditResult(
            score=8.0, maxPossibleScore=10.0, summary="Dec audit",
            details=[AuditResultDetail(
                criterionId="C01", label="Saudacao", status="pass",
                weight=10.0, obtainedScore=10.0, comment="OK",
            )],
            transcription=[TranscriptionSegment(start="00:00", end="00:05", text="Boa tarde")],
            operatorName="Operador Teste", operatorId="OP-001",
            timestamp="2026-12-15T12:00:00", source_type="audio",
        )
        database.save_audit(result_dec, input_hash="limit-dec", sector_id="fenix")

        count_dec = get_operator_audit_count_for_month(
            database.get_connection, "Operador Teste", 2026, 12,
        )
        count_jan = get_operator_audit_count_for_month(
            database.get_connection, "Operador Teste", 2027, 1,
        )
        self.assertEqual(count_dec, 1)
        self.assertEqual(count_jan, 0)

    def test_different_operators_have_independent_counts(self):
        result_a = self._make_result("Operador A")
        result_b = self._make_result("Operador B")
        database.save_audit(result_a, input_hash="limit-a1", sector_id="uti")
        database.save_audit(result_a, input_hash="limit-a2", sector_id="uti")
        database.save_audit(result_b, input_hash="limit-b1", sector_id="uti")

        count_a = get_operator_audit_count_for_month(
            database.get_connection, "Operador A", 2026, 4,
        )
        count_b = get_operator_audit_count_for_month(
            database.get_connection, "Operador B", 2026, 4,
        )
        self.assertEqual(count_a, 2)
        self.assertEqual(count_b, 1)


if __name__ == "__main__":
    unittest.main()
