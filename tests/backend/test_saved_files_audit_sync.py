import os
import sys
import unittest
from unittest.mock import patch, ANY

from fastapi import HTTPException


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database  # noqa: E402
from core.saved_files_sync_queue import set_inline_mode  # noqa: E402
from repositories import audits
from routers.saved_files import ArquivoSalvoRequest, ArquivoSalvoUpdate, atualizar_salvo, salvar_arquivo  # noqa: E402
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment  # noqa: E402


class _FakeCursor:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.rowcount = 0

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if str(query).lstrip().upper().startswith("UPDATE"):
            self.rowcount = 1

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class TestSavedFilesAuditSync(unittest.TestCase):
    def _audit_row(self):
        return {
            "id": 42,
            "timestamp": "2026-04-24T10:00:00",
            "audio_date": "2026-04-24",
            "operator_name": "Operador QA",
            "operator_id": "HUA-42",
            "score": 8.0,
            "max_score": 10.0,
            "summary": "Resumo antigo",
            "ai_feedback": "Feedback antigo",
            "details": [
                {
                    "criterionId": "C01",
                    "label": "Saudacao",
                    "status": "pass",
                    "weight": 10.0,
                    "obtainedScore": 8.0,
                    "comment": "OK",
                }
            ],
            "transcription": [{"start": "00:00", "end": "00:03", "text": "Bom dia"}],
            "input_hash": "hash-42",
            "source_type": "audio",
            "audit_scope": "call_quality",
            "audio_quality": None,
        }

    def test_create_saved_file_allows_audit_records(self):
        payload = ArquivoSalvoRequest(
            tipo="Auditoria",
            conteudo="conteudo duplicado",
            audit_id=42,
        )

        with patch("routers.saved_files.database.save_arquivo", return_value=123) as save_file:
            response = salvar_arquivo(payload, user={"username": "admin", "role": "admin"})

        self.assertEqual(response["id"], 123)
        save_file.assert_called_once()

    def test_saved_audit_filename_uses_operator_and_alert_context(self):
        audit = self._audit_row()
        audit.update(
            {
                "alert_label": "Entrega fora do padrao",
                "audio_original_filename": "ligacao_huawei_operador_qa_call_123.wav",
            }
        )

        filename = database._build_saved_audit_filename(audit)
        metadata = database._build_saved_audit_metadata(audit)

        self.assertEqual(filename, "Auditoria_42_operador_qa_entrega_fora_do_padrao.json")
        self.assertEqual(metadata["saved_filename"], filename)
        self.assertEqual(metadata["source_filename"], "ligacao_huawei_operador_qa_call_123.wav")
        self.assertEqual(metadata["audio_original_filename"], "ligacao_huawei_operador_qa_call_123.wav")

    def test_saved_audit_metadata_uses_huawei_call_time_not_audit_timestamp(self):
        audit = self._audit_row()
        audit.update(
            {
                "timestamp": "2026-06-01T17:24:01.555922",
                "audio_date": None,
                "alert_label": "Parada indevida motorista",
            }
        )
        source_metadata = {
            "huawei_call_id": "1780281834-13388",
            "huawei_begin_time": "1780281844000",
        }

        content = database._build_saved_audit_content(audit, source_metadata)
        metadata = database._build_saved_audit_metadata(audit, source_metadata)

        self.assertIn("Data/hora da ligação\n31/05/2026 23:44", content)
        self.assertEqual(metadata["timestamp"], "2026-05-31T23:44:04-03:00")
        self.assertEqual(metadata["audio_date"], "2026-05-31T23:44:04-03:00")
        self.assertEqual(metadata["call_started_at"], "2026-05-31T23:44:04-03:00")
        self.assertEqual(metadata["audit_timestamp"], "2026-06-01T17:24:01.555922")
        self.assertEqual(metadata["source_metadata"]["huawei_call_id"], "1780281834-13388")

    def test_sync_saved_audit_renames_existing_generic_file(self):
        audit = self._audit_row()
        audit.update(
            {
                "alert_label": "Entrega fora do padrao",
                "audio_original_filename": "ligacao_huawei_operador_qa_call_123.wav",
            }
        )

        with patch("repositories.audits.get_audit_by_id", return_value=audit):
            with patch("repositories.saved_files.get_arquivo_by_audit_id", return_value={"id": 7}):
                with patch(
                    "db.database.obter_fila_revisao_classificacao_por_auditoria",
                    return_value={"metadata": {"huawei_begin_time": "1780281844000"}},
                ):
                    with patch("repositories.saved_files.update_arquivo_by_audit_id", return_value=True) as update_file:
                        try:
                            set_inline_mode(True)
                            database.sync_arquivo_salvo_for_audit(42)
                        finally:
                            set_inline_mode(None)

        update_file.assert_called_once()
        kwargs = update_file.call_args.kwargs
        self.assertEqual(kwargs["arquivo"], "Auditoria_42_operador_qa_entrega_fora_do_padrao.json")
        self.assertEqual(kwargs["data_analise"], "2026-05-31T23:44:04-03:00")
        self.assertEqual(kwargs["metadata"]["timestamp"], "2026-05-31T23:44:04-03:00")
        self.assertEqual(kwargs["metadata"]["audit_timestamp"], "2026-04-24T10:00:00")
        self.assertEqual(kwargs["metadata"]["source_filename"], "ligacao_huawei_operador_qa_call_123.wav")

    def test_update_saved_file_route_allows_linked_audit(self):
        item = {
            "id": 7,
            "tipo": "Auditoria",
            "audit_id": 42,
            "sector_id": "cadastro",
        }
        payload = ArquivoSalvoUpdate(
            conteudo="texto divergente",
            score=5.0,
            metadata={
                "summary": "Resumo editado",
                "maxPossibleScore": 10.0,
                "details": [
                    {
                        "criterionId": "C01",
                        "label": "Saudacao",
                        "status": "fail",
                        "weight": 10.0,
                        "obtainedScore": 0.0,
                        "comment": "Corrigido",
                    }
                ],
                "transcription": [{"start": "00:00", "end": "00:03", "text": "Bom dia"}],
            },
        )

        # v1.3.90: update_audit_by_id agora retorna dict com {"updated", "rag_payload"}
        # em vez de bool. Mock alinha com novo contrato.
        from fastapi import BackgroundTasks
        with patch("routers.saved_files.database.get_arquivo_salvo", return_value=item):
            with patch("repositories.audits.get_audit_by_id", return_value=self._audit_row()):
                with patch(
                    "routers.saved_files.database.update_audit_by_id",
                    return_value={"updated": True, "rag_payload": None},
                ) as update_audit:
                    with patch("routers.saved_files.database.update_arquivo_salvo") as update_file:
                        response = atualizar_salvo(
                            7,
                            payload,
                            background_tasks=BackgroundTasks(),
                            _user={"role": "admin"},
                        )

        self.assertTrue(response["success"])
        update_audit.assert_called_once()
        audit_result = update_audit.call_args.args[1]
        self.assertEqual(audit_result.summary, "Resumo editado")
        self.assertEqual(audit_result.score, 5.0)
        self.assertEqual(audit_result.details[0].status, "fail")
        update_file.assert_not_called()

    def test_repository_update_audit_by_id_uses_available_json_loader(self):
        row = {
            "id": 42,
            "details_json": (
                '[{"criterionId":"C01","label":"Saudacao","status":"pass",'
                '"weight":10.0,"obtainedScore":10.0,"comment":"OK"}]'
            ),
            "transcription_json": '[{"start":"00:00","end":"00:03","text":"Bom dia"}]',
            "sector_id": "cadastro",
        }
        cursor = _FakeCursor(row)
        conn = _FakeConnection(cursor)
        result = AuditResult(
            score=10.0,
            maxPossibleScore=10.0,
            summary="Resumo editado",
            ai_feedback="Feedback editado",
            details=[
                AuditResultDetail(
                    criterionId="C01",
                    label="Saudacao",
                    status="pass",
                    weight=10.0,
                    obtainedScore=10.0,
                    comment="OK",
                )
            ],
            transcription=[
                TranscriptionSegment(start="00:00", end="00:03", text="Bom dia corrigido")
            ],
            operatorName="Operador QA",
            source_type="audio",
        )

        outcome = audits.update_audit_by_id(lambda: conn, 42, result, ai_feedback=result.ai_feedback)

        # v1.3.90: retorno agora eh dict, nao bool.
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome["updated"])
        # Sem mudancas de status do auditor -> sem rag_payload (nao foi disparado feedback RLHF).
        self.assertIsNone(outcome.get("rag_payload"))
        self.assertEqual(conn.commits, 1)
        self.assertTrue(conn.closed)
        update_query, update_params = cursor.executed[-1]
        self.assertIn("UPDATE audits", update_query)
        self.assertIn("Bom dia corrigido", update_params[4])

    def test_update_saved_file_route_rejects_missing_linked_audit(self):
        item = {
            "id": 7,
            "tipo": "Auditoria",
            "audit_id": 42,
        }
        payload = ArquivoSalvoUpdate(conteudo="texto divergente", metadata={"summary": "Resumo"})

        from fastapi import BackgroundTasks
        with patch("routers.saved_files.database.get_arquivo_salvo", return_value=item):
            with patch("repositories.audits.get_audit_by_id", return_value=None):
                with self.assertRaises(HTTPException) as ctx:
                    atualizar_salvo(
                        7,
                        payload,
                        background_tasks=BackgroundTasks(),
                        _user={"role": "admin"},
                    )

        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_saved_file_route_allows_non_audit_documents(self):
        item = {
            "id": 7,
            "tipo": "Transcricao",
            "audit_id": None,
        }
        payload = ArquivoSalvoUpdate(conteudo="conteudo atualizado", metadata={"kind": "note"})

        from fastapi import BackgroundTasks
        with patch("routers.saved_files.database.get_arquivo_salvo", return_value=item):
            with patch("routers.saved_files.database.update_arquivo_salvo", return_value=True) as update_file:
                response = atualizar_salvo(
                    7,
                    payload,
                    background_tasks=BackgroundTasks(),
                    _user={"role": "admin"},
                )

        self.assertTrue(response["success"])
        update_file.assert_called_once_with(7, "conteudo atualizado", score=None, metadata={"kind": "note"})


if __name__ == "__main__":
    unittest.main()
