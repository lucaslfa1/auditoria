import os

import sys

import unittest

from unittest.mock import ANY, MagicMock, patch



sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



import db.database as database
from repositories import audits

from db.domain_constants import AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_DISCARDED, AUDIT_STATUS_PENDING_APPROVAL

from repositories.audits import (

    discard_audit,

    enqueue_audit_for_supervisor_review,

    get_audit_media_record_by_id,

    restore_audit,

)

from routers.system import save_to_dashboard

from schemas import AuditResult, AuditResultDetail, TranscriptionSegment





class TestAuditDiscardRepository(unittest.TestCase):

    class _Cursor:

        def __init__(self, row):

            self.row = row

            self.queries = []



        def execute(self, query, params):

            self.queries.append((query, params))



        def fetchone(self):

            return self.row



    class _Connection:

        def __init__(self, cursor):

            self._cursor = cursor

            self.committed = False

            self.closed = False



        def cursor(self):

            return self._cursor



        def commit(self):

            self.committed = True



        def close(self):

            self.closed = True



    def test_discard_audit_marks_status_and_metadata(self):

        cursor = self._Cursor({"id": 42, "status": AUDIT_STATUS_PENDING_APPROVAL})

        conn = self._Connection(cursor)



        result = discard_audit(

            lambda: conn,

            42,

            discarded_by="auditor.teste",

            reason="Ligacao duplicada",

        )



        self.assertEqual(result["status"], AUDIT_STATUS_DISCARDED)

        self.assertEqual(result["previous_status"], AUDIT_STATUS_PENDING_APPROVAL)

        self.assertTrue(conn.committed)

        self.assertTrue(conn.closed)



        update_query, update_params = cursor.queries[1]

        self.assertIn("discarded_at", update_query)

        self.assertIn("pre_discard_status", update_query)

        self.assertEqual(update_params[0], AUDIT_STATUS_DISCARDED)

        self.assertEqual(update_params[2], "auditor.teste")

        self.assertEqual(update_params[3], "Ligacao duplicada")

        # pre_discard_status: permite reverter via /restore para o status anterior.

        self.assertEqual(update_params[4], AUDIT_STATUS_PENDING_APPROVAL)

        self.assertEqual(update_params[5], 42)



    def test_discard_audit_is_idempotent(self):

        cursor = self._Cursor({"id": 42, "status": AUDIT_STATUS_DISCARDED})

        conn = self._Connection(cursor)



        result = discard_audit(lambda: conn, 42, discarded_by="auditor.teste")



        self.assertEqual(result["status"], AUDIT_STATUS_DISCARDED)

        self.assertTrue(result["already_discarded"])

        self.assertEqual(len(cursor.queries), 1)

        self.assertFalse(conn.committed)

        self.assertTrue(conn.closed)





class TestAuditRestoreRepository(unittest.TestCase):

    class _Cursor:

        def __init__(self, row):

            self.row = row

            self.queries = []



        def execute(self, query, params):

            self.queries.append((query, params))



        def fetchone(self):

            return self.row



    class _Connection:

        def __init__(self, cursor):

            self._cursor = cursor

            self.committed = False

            self.closed = False



        def cursor(self):

            return self._cursor



        def commit(self):

            self.committed = True



        def close(self):

            self.closed = True



    def test_restore_audit_returns_to_pre_discard_status(self):

        cursor = self._Cursor(

            {

                "id": 42,

                "status": AUDIT_STATUS_DISCARDED,

                "pre_discard_status": AUDIT_STATUS_PENDING_APPROVAL,

            }

        )

        conn = self._Connection(cursor)



        result = restore_audit(lambda: conn, 42, restored_by="admin.teste")



        self.assertEqual(result["status"], AUDIT_STATUS_PENDING_APPROVAL)

        self.assertEqual(result["previous_status"], AUDIT_STATUS_DISCARDED)

        self.assertTrue(conn.committed)



        update_query, update_params = cursor.queries[1]

        self.assertIn("discarded_at = NULL", update_query)

        self.assertIn("pre_discard_status = NULL", update_query)

        self.assertEqual(update_params[0], AUDIT_STATUS_PENDING_APPROVAL)

        self.assertEqual(update_params[1], 42)



    def test_restore_audit_defaults_to_pending_approval_when_pre_status_missing(self):

        # Auditoria descartada ANTES do fix de persistir pre_discard_status nao

        # tem a informacao salva; o fallback deve ser pending_approval.

        cursor = self._Cursor(

            {"id": 42, "status": AUDIT_STATUS_DISCARDED, "pre_discard_status": None}

        )

        conn = self._Connection(cursor)



        result = restore_audit(lambda: conn, 42, restored_by="admin.teste")



        self.assertEqual(result["status"], AUDIT_STATUS_PENDING_APPROVAL)



    def test_restore_audit_is_idempotent_for_non_discarded(self):

        cursor = self._Cursor(

            {

                "id": 42,

                "status": AUDIT_STATUS_PENDING_APPROVAL,

                "pre_discard_status": None,

            }

        )

        conn = self._Connection(cursor)



        result = restore_audit(lambda: conn, 42, restored_by="admin.teste")



        self.assertTrue(result["already_restored"])

        self.assertEqual(len(cursor.queries), 1)  # only the SELECT

        self.assertFalse(conn.committed)



    def test_restore_audit_raises_when_not_found(self):

        cursor = self._Cursor(None)

        conn = self._Connection(cursor)



        with self.assertRaises(ValueError):

            restore_audit(lambda: conn, 999, restored_by="admin.teste")





class TestAuditDiscardDatabaseWrapper(unittest.TestCase):

    @patch("repositories.audits.rebalance_operator_review_queue")

    @patch("repositories.audits.discard_audit")

    @patch("repositories.audits.get_audit_by_id")

    @patch("db.database.get_connection")

    def test_discard_rebalances_operator_queue(

        self,

        mock_get_connection,

        mock_get_audit_by_id,

        mock_discard_audit,

        mock_rebalance,

    ):

        connection = MagicMock()

        mock_get_connection.return_value = connection

        mock_get_audit_by_id.return_value = {

            "operator_name": "Ana Souza",

            "operator_id": "OP-777",

        }

        mock_discard_audit.return_value = {"id": 42, "status": AUDIT_STATUS_DISCARDED}



        result = database.discard_audit(42, discarded_by="auditor.teste", reason="duplicada")



        self.assertEqual(result["status"], AUDIT_STATUS_DISCARDED)

        mock_discard_audit.assert_called_once()

        mock_rebalance.assert_called_once()

        self.assertEqual(mock_rebalance.call_args.kwargs["operator_name"], "Ana Souza")

        self.assertEqual(mock_rebalance.call_args.kwargs["operator_id"], "OP-777")

        connection.close.assert_called_once()





class TestAuditRestoreDatabaseWrapper(unittest.TestCase):

    @patch("repositories.audits.rebalance_operator_review_queue")

    @patch("repositories.audits.restore_audit")

    @patch("repositories.audits.get_audit_by_id")

    @patch("db.database.get_connection")

    def test_restore_rebalances_operator_queue(

        self,

        mock_get_connection,

        mock_get_audit_by_id,

        mock_restore_audit,

        mock_rebalance,

    ):

        connection = MagicMock()

        mock_get_connection.return_value = connection

        mock_get_audit_by_id.return_value = {

            "operator_name": "Ana Souza",

            "operator_id": "OP-777",

        }

        mock_restore_audit.return_value = {

            "id": 42,

            "status": AUDIT_STATUS_PENDING_APPROVAL,

            "previous_status": AUDIT_STATUS_DISCARDED,

            "restored_by": "admin.teste",

        }



        result = database.restore_audit(42, restored_by="admin.teste")



        self.assertEqual(result["status"], AUDIT_STATUS_PENDING_APPROVAL)

        mock_restore_audit.assert_called_once()

        mock_rebalance.assert_called_once()

        self.assertEqual(mock_rebalance.call_args.kwargs["operator_name"], "Ana Souza")

        self.assertEqual(mock_rebalance.call_args.kwargs["operator_id"], "OP-777")

        self.assertGreaterEqual(connection.close.call_count, 1)



    @patch("repositories.audits.rebalance_operator_review_queue")

    @patch("repositories.audits.restore_audit")

    @patch("repositories.audits.get_audit_by_id")

    @patch("db.database.get_connection")

    def test_restore_skips_rebalance_when_already_restored(

        self,

        mock_get_connection,

        mock_get_audit_by_id,

        mock_restore_audit,

        mock_rebalance,

    ):

        mock_get_connection.return_value = MagicMock()

        mock_get_audit_by_id.return_value = {

            "operator_name": "Ana Souza",

            "operator_id": "OP-777",

        }

        mock_restore_audit.return_value = {

            "id": 42,

            "status": AUDIT_STATUS_PENDING_APPROVAL,

            "already_restored": True,

        }



        database.restore_audit(42, restored_by="admin.teste")



        mock_rebalance.assert_not_called()





class TestAuditSaveToSupervisorHandoff(unittest.TestCase):

    def _build_result(self) -> AuditResult:

        return AuditResult(

            score=8.0,

            maxPossibleScore=10.0,

            summary="Auditoria pronta",

            details=[

                AuditResultDetail(

                    criterionId="c1",

                    label="Criterio",

                    status="pass",

                    weight=1.0,

                    obtainedScore=1.0,

                    comment="OK",

                )

            ],

            transcription=[TranscriptionSegment(start="00:00", end="00:01", text="OK")],

            operatorName="Ana Souza",

            operatorId="OP-777",

            timestamp="2026-04-13T10:00:00",

        )



    @patch("repositories.audits.rebalance_operator_review_queue")

    @patch("repositories.audits.update_audit_audio_storage")

    @patch("repositories.audits.get_audit_media_record_by_hash")

    @patch("repositories.audits.save_audit")

    def test_queue_handoff_links_cached_audio_to_supervisor_audit(

        self,

        mock_save_audit,

        mock_get_media_by_hash,

        mock_update_audio,

        mock_rebalance,

    ):

        mock_save_audit.return_value = 200

        mock_get_media_by_hash.return_value = {

            "id": 100,

            "audio_storage_path": "2026/04/audit_100_hash.wav",

            "audio_original_filename": "ligacao.wav",

            "audio_mime_type": "audio/wav",

            "audio_size_bytes": 1234,

        }

        mock_rebalance.return_value = {

            "pending_ids": [],

            "awaiting_ids": [200],

            "open_ids": [200],

        }



        queued = enqueue_audit_for_supervisor_review(

            lambda: MagicMock(),

            self._build_result(),

            input_hash="hash-com-audio",

            operator_id="OP-777",

            rebalance=False,

        )



        self.assertEqual(queued["audit_id"], 200)

        self.assertEqual(queued["status"], AUDIT_STATUS_AWAITING_PAIR)

        mock_update_audio.assert_called_once_with(

            ANY,

            200,

            audio_storage_path="2026/04/audit_100_hash.wav",

            audio_original_filename="ligacao.wav",

            audio_mime_type="audio/wav",

            audio_size_bytes=1234,

        )



    def test_media_lookup_backfills_audio_from_same_input_hash(self):

        class Cursor:

            def __init__(self):

                self.queries = []

                self.rows = [

                    {

                        "id": 200,

                        "input_hash": "hash-com-audio",

                        "audio_storage_path": None,

                        "audio_original_filename": None,

                        "audio_mime_type": None,

                        "audio_size_bytes": None,

                    },

                    {

                        "id": 100,

                        "input_hash": "hash-com-audio",

                        "audio_storage_path": "2026/04/audit_100_hash.wav",

                        "audio_original_filename": "ligacao.wav",

                        "audio_mime_type": "audio/wav",

                        "audio_size_bytes": 1234,

                    },

                ]



            def execute(self, query, params):

                self.queries.append((query, params))



            def fetchone(self):

                return self.rows.pop(0) if self.rows else None



        class Connection:

            def __init__(self, cursor):

                self._cursor = cursor

                self.committed = False

                self.closed = False



            def cursor(self):

                return self._cursor



            def commit(self):

                self.committed = True



            def close(self):

                self.closed = True



        cursor = Cursor()

        conn = Connection(cursor)



        media = get_audit_media_record_by_id(lambda: conn, 200)



        self.assertEqual(media["id"], 200)

        self.assertEqual(media["audio_storage_path"], "2026/04/audit_100_hash.wav")

        self.assertTrue(conn.committed)

        self.assertTrue(conn.closed)

        update_query, update_params = cursor.queries[2]

        self.assertIn("UPDATE audits", update_query)

        self.assertEqual(update_params[-1], 200)



    @patch("repositories.audits.get_audit_by_hash")

    @patch("routers.system.database.queue_audit_for_supervisor_review")

    def test_save_uses_result_operator_id_when_query_param_is_missing(self, mock_queue, mock_get_hash):

        mock_get_hash.return_value = None

        mock_queue.return_value = {

            "audit_id": 99,

            "status": AUDIT_STATUS_PENDING_APPROVAL,

            "pending_count": 2,

            "open_count": 2,

        }

        result = self._build_result()



        response = save_to_dashboard(result, _user={"username": "admin", "role": "admin"})



        self.assertEqual(response["review_status"], AUDIT_STATUS_AWAITING_PAIR)

        self.assertEqual(mock_queue.call_args.kwargs["operator_id"], "OP-777")

        self.assertEqual(mock_queue.call_args.kwargs["rebalance"], False)





if __name__ == "__main__":

    unittest.main()



