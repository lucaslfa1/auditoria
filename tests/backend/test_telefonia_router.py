import asyncio
import os
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers import review as review_router
from routers import telefonia


def _queue_item(status: str = "auto_resolved") -> dict:
    return {
        "id": 10,
        "input_hash": "hash-123",
        "nome_arquivo": "huawei_call.wav",
        "setor_previsto": "logistica",
        "alerta_previsto": "ENTREGA",
        "operador_previsto": "Operador Teste",
        "status": status,
        "metadata": {
            "origem": "huawei_sync",
            "source_type": "audio",
            "classified_audio_path": "hash-123.wav",
            "huawei_duration": 65,
        },
    }


def _pdf_queue_item(status: str = "auto_resolved") -> dict:
    item = _queue_item(status)
    item["input_hash"] = "hash-pdf"
    item["nome_arquivo"] = "relatorio_huawei.pdf"
    item["metadata"] = {
        **item["metadata"],
        "source_type": "pdf",
        "classified_audio_path": "hash-pdf.pdf",
    }
    return item


def _sent_to_triage_queue_item() -> dict:
    item = _queue_item("pending")
    item["input_hash"] = "hash-triage"
    item["metadata"] = {
        **item["metadata"],
        "is_manual": True,
        "telefonia_triage_requested_at": "2026-05-13T12:00:00+00:00",
        "telefonia_triage_requested_by": "auditor",
    }
    item["motivos_revisao"] = ["aguardando_triagem", "enviado_para_triagem_telefonia"]
    return item


def _risk_inbound_queue_item() -> dict:
    item = _queue_item("downloaded")
    item["input_hash"] = "hash-risk-inbound"
    item["setor_previsto"] = "DIST - VERDE"
    item["metadata"] = {
        **item["metadata"],
        "operator_sector_real": "DIST - VERDE",
        "huawei_is_call_in": True,
        "huawei_caller_no": "0011999999999",
        "huawei_callee_no": "61197",
        "huawei_work_no": "61197",
    }
    return item


def _celula_queue_item() -> dict:
    item = _queue_item("downloaded")
    item["input_hash"] = "hash-celula"
    item["setor_previsto"] = "DIST E CELULA - VERDE"
    item["metadata"] = {
        **item["metadata"],
        "operator_sector_real": "DIST E CELULA - VERDE",
        "huawei_is_call_in": False,
    }
    return item


def _manual_queue_item(status: str = "pending") -> dict:
    item = _queue_item(status)
    item["input_hash"] = "hash-manual"
    item["nome_arquivo"] = "manual_call.wav"
    item["metadata"] = {
        "source_type": "audio",
        "classified_audio_path": "manual-call.wav",
    }
    return item


class _FakeCleanupCursor:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.executions: list[tuple[str, object]] = []

    def execute(self, query: str, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows


class _FakeCleanupConnection:
    def __init__(self, rows: list[dict]):
        self.cursor_obj = _FakeCleanupCursor(rows)
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class TestTelefoniaRouter(unittest.TestCase):
    # O gate `telefonia_cron_sync_ativa` e o intervalo `automacao_intervalo_segundos`
    # foram removidos em 2026-06-12 (revisao item 4): o /cron/sync agora depende
    # apenas do CRON_SECRET_TOKEN + autogovernanca do pipeline D-1
    # (huawei_d1_enabled, horario, um lote por dia).

    def test_cron_sync_d_minus_1_dispara_pipeline_sem_gate_proprio(self):
        # Pipeline desligado deve ser decidido DENTRO do executar_d_minus_1_pipeline
        # (gate huawei_d1_enabled), nao por flag propria do endpoint.
        request = SimpleNamespace(headers={"Authorization": "Bearer secret"})
        run_pipeline = AsyncMock(return_value={"status": "disabled", "message": "Pipeline D-1 desligado nas configurações."})

        with patch.dict(os.environ, {"CRON_SECRET_TOKEN": "secret"}, clear=False), patch(
            "core.huawei_d_minus_1.executar_d_minus_1_pipeline",
            run_pipeline,
        ):
            result = asyncio.run(telefonia.cron_sync_d_minus_1(request))

        self.assertEqual(result["status"], "disabled")
        run_pipeline.assert_awaited_once()

    def test_cron_sync_d_minus_1_does_not_force_huawei_classification(self):
        request = SimpleNamespace(headers={"Authorization": "Bearer secret"})
        run_pipeline = AsyncMock(return_value={"status": "ok", "baixadas": 1})

        with patch.dict(
            os.environ,
            {"CRON_SECRET_TOKEN": "secret", "HUAWEI_SYNC_ENABLE_CLASSIFY": "false"},
            clear=False,
        ), patch(
            "core.huawei_d_minus_1.executar_d_minus_1_pipeline",
            run_pipeline,
        ):
            result = asyncio.run(telefonia.cron_sync_d_minus_1(request))
            classify_flag = os.environ.get("HUAWEI_SYNC_ENABLE_CLASSIFY")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(classify_flag, "false")
        run_pipeline.assert_awaited_once()

    def test_proxima_execucao_d1_usa_retry_pendente_antes_de_amanha(self):
        now_sp = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)
        last_attempt_sp = now_sp - timedelta(minutes=20)

        proxima = telefonia._calcular_proxima_execucao_d1_sp(
            now_sp=now_sp,
            horario_raw="06:00",
            enabled=True,
            ultima_execucao={"status": "partial", "attempts": 1},
            last_attempt_sp=last_attempt_sp,
            max_retries=4,
            retry_intervalo_minutos=60,
        )

        self.assertEqual(proxima, now_sp + timedelta(minutes=40))

    def test_proxima_execucao_d1_retry_vencido_cai_para_horario_diario(self):
        # Retry ja vencido (last_attempt + intervalo no passado) NAO deve virar
        # "now + 1 min" eternamente (gerava o aviso "Proxima: em 1 min" preso na
        # UI); cai para o proximo horario diario real.
        now_sp = datetime(2026, 5, 10, 14, 0, tzinfo=timezone.utc)
        last_attempt_sp = now_sp - timedelta(minutes=90)

        proxima = telefonia._calcular_proxima_execucao_d1_sp(
            now_sp=now_sp,
            horario_raw="06:00",
            enabled=True,
            ultima_execucao={"status": "error", "attempts": 2},
            last_attempt_sp=last_attempt_sp,
            max_retries=4,
            retry_intervalo_minutos=60,
        )

        # horario diario 06:00 ja passou hoje (now=14:00) -> amanha 06:00
        self.assertEqual(proxima, datetime(2026, 5, 11, 6, 0, tzinfo=timezone.utc))

    def test_recording_item_expõe_url_de_audio_e_acao_de_triagem(self):
        result = telefonia._recording_item_from_queue(_queue_item())

        self.assertEqual(result["audio_url"], "/api/telefonia/recordings/hash-123/audio")
        self.assertTrue(result["audio_available"])
        self.assertTrue(result["can_send_to_triage"])
        self.assertEqual(result["triage_status"], "auto_resolved")
        self.assertEqual(result["duration"], 65)

    def test_recording_item_prefere_nome_oficial_resolvido_por_id_huawei(self):
        item = _queue_item()
        item["operador_previsto"] = "Operador Teste"
        item["operator_name"] = "Jhaves Daniel Marques"

        result = telefonia._recording_item_from_queue(item)

        self.assertEqual(result["operator_name"], "Jhaves Daniel Marques")

    def test_recording_item_expõe_bloqueio_de_triagem_manual(self):
        result = telefonia._recording_item_from_queue(_queue_item("needs_manual_triage"))

        self.assertEqual(result["triage_status"], "needs_manual_triage")
        self.assertEqual(result["triage_status_label"], "Triagem manual")
        self.assertFalse(result["can_send_to_audit"])
        self.assertFalse(result["can_send_to_triage"])

    def test_recording_filter_rejects_pdf_reports_from_telefonia(self):
        self.assertTrue(telefonia._is_huawei_recording_item(_queue_item()))
        self.assertFalse(telefonia._is_huawei_recording_item(_pdf_queue_item()))

    def test_get_huawei_queue_item_rejects_pdf_report_as_recording(self):
        with patch.object(telefonia.database, "obter_fila_revisao_classificacao_por_hash", return_value=_pdf_queue_item()):
            with self.assertRaises(HTTPException) as ctx:
                telefonia._get_huawei_queue_item_or_404("hash-pdf")

        self.assertEqual(ctx.exception.status_code, 404)

    def test_listar_gravacoes_omite_pdf_reports(self):
        with patch.object(
            telefonia.classification_review,
            "listar_fila_revisao_classificacao",
            return_value=[_queue_item(), _pdf_queue_item()],
        ):
            result = asyncio.run(telefonia.listar_gravacoes(_user={"username": "admin"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["input_hash"], "hash-123")

    def test_listar_gravacoes_omite_item_ja_enviado_para_triagem(self):
        with patch.object(
            telefonia.classification_review,
            "listar_fila_revisao_classificacao",
            return_value=[_queue_item("downloaded"), _sent_to_triage_queue_item()],
        ):
            result = asyncio.run(telefonia.listar_gravacoes(_user={"username": "admin"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["input_hash"], "hash-123")

    def test_limpar_telefonia_reconhece_metadata_jsonb_dict(self):
        rows = [
            {
                "input_hash": "hash-huawei",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "classification_status": "pending",
                    "huawei_call_id": "CALL-1",
                },
            },
            {
                "input_hash": "hash-triage",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "classification_status": "pending",
                    "huawei_call_id": "CALL-2",
                    "telefonia_triage_requested_at": "2026-05-13T12:00:00+00:00",
                },
            },
        ]
        conn = _FakeCleanupConnection(rows)

        with patch.object(telefonia.database, "get_connection", return_value=conn):
            result = telefonia.remover_todas_gravacoes(_user={"username": "admin"})

        self.assertEqual(result["deleted"], 1)
        delete_queue = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM fila_revisao_classificacao" in query
        ]
        delete_logs = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM huawei_sync_logs" in query
        ]
        self.assertEqual(delete_queue[0][0], ["hash-huawei"])
        self.assertEqual(delete_logs[0][0], ["CALL-1"])
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)

    def test_limpar_triagem_preserva_huawei_nao_enviado_com_metadata_jsonb_dict(self):
        rows = [
            {
                "input_hash": "hash-huawei",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "classification_status": "pending",
                    "is_manual": False,
                    "huawei_call_id": "CALL-1",
                },
            },
            {
                "input_hash": "hash-triage",
                "metadata_json": {
                    "origem": "huawei_sync",
                    "classification_status": "pending",
                    "is_manual": True,
                    "huawei_call_id": "CALL-2",
                },
            },
            {
                "input_hash": "hash-upload",
                "metadata_json": {
                    "source_type": "audio",
                    "classified_audio_path": "manual.wav",
                },
            },
        ]
        conn = _FakeCleanupConnection(rows)

        with patch.object(review_router.database, "get_connection", return_value=conn):
            result = review_router.clear_pending_classification_queue(_user={"username": "admin"})

        self.assertEqual(result["deleted"], 2)
        delete_queue = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM fila_revisao_classificacao" in query
        ]
        delete_logs = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM huawei_sync_logs" in query
        ]
        self.assertEqual(delete_queue[0][0], ["hash-triage", "hash-upload"])
        self.assertEqual(delete_logs[0][0], ["CALL-2"])
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)

    def test_listar_gravacoes_omite_receptiva_de_setor_de_risco(self):
        with patch.object(
            telefonia.classification_review,
            "listar_fila_revisao_classificacao",
            return_value=[_queue_item("downloaded"), _risk_inbound_queue_item()],
        ):
            result = asyncio.run(telefonia.listar_gravacoes(_user={"username": "admin"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["input_hash"], "hash-123")

    def test_listar_gravacoes_omite_celula_fora_da_telefonia(self):
        with patch.object(
            telefonia.classification_review,
            "listar_fila_revisao_classificacao",
            return_value=[_queue_item("downloaded"), _celula_queue_item()],
        ):
            result = asyncio.run(telefonia.listar_gravacoes(_user={"username": "admin"}))

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["input_hash"], "hash-123")

    def test_bloqueio_de_celula_tambem_reconhece_receptivo(self):
        item = _queue_item("downloaded")
        item["setor_previsto"] = "RECEPTIVO"

        self.assertEqual(
            telefonia._huawei_recording_direction_block(item),
            ("setor_nao_telefonia", "celula_atendimento"),
        )

    def test_obter_audio_gravacao_serve_bytes_do_audio_classificado(self):
        def _stream():
            yield b"RIFFdemo"

        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=_queue_item()):
            with patch.object(telefonia, "open_classified_audio_stream", return_value=(_stream(), 8)):
                response = telefonia.obter_audio_gravacao("hash-123", _user={"username": "admin"})

        self.assertEqual(response.media_type, "audio/wav")
        self.assertIn("inline", response.headers["content-disposition"])
        self.assertEqual(response.headers["content-length"], "8")

    def test_enviar_gravacao_para_triagem_marca_status_pending(self):
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=_queue_item()):
            with patch.object(telefonia.classification_review, "atualizar_status_fila_revisao_classificacao", return_value=True) as update:
                result = telefonia.enviar_gravacao_para_triagem(
                    "hash-123",
                    user={"username": "auditor"},
                )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "pending")
        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs["status"], "pending")
        self.assertIn("enviado_para_triagem_telefonia", update.call_args.kwargs["motivos_revisao_append"])
        self.assertEqual(update.call_args.kwargs["metadata_merge"]["telefonia_triage_requested_by"], "auditor")

    def test_enviar_gravacao_auditada_para_triagem_retorna_conflito(self):
        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=_queue_item("audited"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                telefonia.enviar_gravacao_para_triagem("hash-123", user={"username": "auditor"})

        self.assertEqual(ctx.exception.status_code, 409)

    def test_enviar_gravacao_receptiva_de_risco_para_triagem_retorna_conflito(self):
        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=_risk_inbound_queue_item(),
        ):
            with self.assertRaises(HTTPException) as ctx:
                telefonia.enviar_gravacao_para_triagem("hash-risk-inbound", user={"username": "auditor"})

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("setores de risco", ctx.exception.detail)

    def test_enviar_gravacao_de_celula_para_triagem_retorna_conflito(self):
        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=_celula_queue_item(),
        ):
            with self.assertRaises(HTTPException) as ctx:
                telefonia.enviar_gravacao_para_triagem("hash-celula", user={"username": "auditor"})

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("nao pertence ao modulo Telefonia", ctx.exception.detail)

    def test_auditar_endpoint_rejeita_alerta_desconhecido_antes_de_agendar(self):
        item = _queue_item("pending")
        item["alerta_previsto"] = "desconhecido"

        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch.object(
                telefonia.classification_review,
                "tentar_iniciar_processamento_auditoria",
            ) as start_processing:
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(
                        telefonia.auditar_instantaneamente_gravacao(
                            "hash-123",
                            user={"username": "admin"},
                        )
                    )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Alerta previsto", ctx.exception.detail)
        start_processing.assert_not_called()

    def test_classificar_gravacao_manual_bloqueia_operador_huawei_nao_cadastrado(self):
        item = _queue_item("pending")
        item["metadata"] = {
            **item["metadata"],
            "id_huawei": "99999",
            "operator_id": "99999",
            "operator_sector_real": "Logistica",
        }

        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch("core.automation.load_classified_audio", return_value=b"RIFFdemo"):
                with patch.object(telefonia.operators, "buscar_colaborador_por_id_huawei", return_value=None):
                    with self.assertRaises(HTTPException) as ctx:
                        asyncio.run(
                            telefonia.classificar_gravacao_manual(
                                "hash-123",
                                user={"username": "admin"},
                            )
                        )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("ID Huawei", ctx.exception.detail)

    def test_classificar_gravacao_manual_bloqueia_metadata_huawei_sem_id(self):
        item = _queue_item("pending")

        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch("core.automation.load_classified_audio", return_value=b"RIFFdemo"):
                with self.assertRaises(HTTPException) as ctx:
                    asyncio.run(
                        telefonia.classificar_gravacao_manual(
                            "hash-123",
                            user={"username": "admin"},
                        )
                    )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("sem ID Huawei", ctx.exception.detail)

    def test_remover_gravacao_oficial_apaga_sync_log_para_permitir_redownload(self):
        """Ao deletar gravacao de operador OFICIAL, o call_id deve sair de huawei_sync_logs
        para que o proximo sync possa redescobrir e baixar de novo a chamada."""
        item = _queue_item("pending")
        item["is_oficial"] = True
        item["metadata"] = {
            **item["metadata"],
            "huawei_call_id": "CALL-OFICIAL",
        }
        conn = _FakeCleanupConnection([])

        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=item,
        ):
            with patch.object(telefonia.database, "get_connection", return_value=conn):
                result = telefonia.remover_gravacao("hash-123", _user={"username": "admin"})

        self.assertEqual(result["action"], "deleted")
        delete_logs = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM huawei_sync_logs" in query
        ]
        insert_skips = [
            params for query, params in conn.cursor_obj.executions
            if "INSERT INTO huawei_sync_logs" in query and "skipped_operator" in query
        ]
        self.assertEqual(len(delete_logs), 1)
        self.assertEqual(delete_logs[0][0], "CALL-OFICIAL")
        self.assertEqual(len(insert_skips), 0)
        self.assertTrue(conn.committed)

    def test_remover_gravacao_nao_oficial_insere_skipped_operator(self):
        """Ao deletar gravacao de operador NAO OFICIAL, o call_id deve ser registrado como
        skipped_operator em huawei_sync_logs para nao ser redescoberto."""
        item = _queue_item("pending")
        item["is_oficial"] = False
        item["metadata"] = {
            **item["metadata"],
            "huawei_call_id": "CALL-NAO-OFICIAL",
        }
        conn = _FakeCleanupConnection([])

        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=item,
        ):
            with patch.object(telefonia.database, "get_connection", return_value=conn):
                result = telefonia.remover_gravacao("hash-123", _user={"username": "admin"})

        self.assertEqual(result["action"], "deleted")
        delete_logs = [
            params for query, params in conn.cursor_obj.executions
            if "DELETE FROM huawei_sync_logs" in query
        ]
        insert_skips = [
            params for query, params in conn.cursor_obj.executions
            if "INSERT INTO huawei_sync_logs" in query and "skipped_operator" in query
        ]
        self.assertEqual(len(delete_logs), 0)
        self.assertEqual(len(insert_skips), 1)
        self.assertEqual(insert_skips[0][0], "CALL-NAO-OFICIAL")
        self.assertTrue(conn.committed)

    def test_cancel_sync_sinaliza_cancelamento_quando_coleta_esta_rodando(self):
        original_task = telefonia._LAST_SYNC_TASK
        original_event = telefonia._LAST_SYNC_CANCEL_EVENT
        original_pause_event = telefonia._LAST_SYNC_PAUSE_EVENT
        original_status = dict(telefonia._LAST_SYNC)
        event = threading.Event()
        pause_event = threading.Event()
        cancel_calls = {"n": 0}

        def _fake_cancel() -> None:
            cancel_calls["n"] += 1

        task = SimpleNamespace(done=lambda: False, cancel=_fake_cancel)
        try:
            telefonia._LAST_SYNC_TASK = task
            telefonia._LAST_SYNC_CANCEL_EVENT = event
            telefonia._LAST_SYNC_PAUSE_EVENT = pause_event
            telefonia._LAST_SYNC.update({"status": "running", "result": None, "cancel_requested": False})

            result = asyncio.run(telefonia.cancel_sync(_user={"username": "admin"}))

            self.assertEqual(result["status"], "cancelling")
            self.assertTrue(event.is_set())
            self.assertTrue(telefonia._LAST_SYNC["cancel_requested"])
            self.assertEqual(telefonia._LAST_SYNC["status"], "cancelling")
            # v1.3.89: cancel hard tambem aborta a task asyncio.
            self.assertEqual(cancel_calls["n"], 1)
        finally:
            telefonia._LAST_SYNC_TASK = original_task
            telefonia._LAST_SYNC_CANCEL_EVENT = original_event
            telefonia._LAST_SYNC_PAUSE_EVENT = original_pause_event
            telefonia._LAST_SYNC.clear()
            telefonia._LAST_SYNC.update(original_status)

    def test_pause_sync_seta_evento_e_marca_status_paused(self):
        original_task = telefonia._LAST_SYNC_TASK
        original_event = telefonia._LAST_SYNC_CANCEL_EVENT
        original_pause_event = telefonia._LAST_SYNC_PAUSE_EVENT
        original_status = dict(telefonia._LAST_SYNC)
        try:
            telefonia._LAST_SYNC_TASK = SimpleNamespace(done=lambda: False, cancel=lambda: None)
            telefonia._LAST_SYNC_CANCEL_EVENT = threading.Event()
            telefonia._LAST_SYNC_PAUSE_EVENT = threading.Event()
            telefonia._LAST_SYNC.update({"status": "running", "result": None})

            result = asyncio.run(telefonia.pause_sync(_user={"username": "admin"}))

            self.assertEqual(result["status"], "paused")
            self.assertTrue(telefonia._LAST_SYNC_PAUSE_EVENT.is_set())
            self.assertEqual(telefonia._LAST_SYNC["status"], "paused")
        finally:
            telefonia._LAST_SYNC_TASK = original_task
            telefonia._LAST_SYNC_CANCEL_EVENT = original_event
            telefonia._LAST_SYNC_PAUSE_EVENT = original_pause_event
            telefonia._LAST_SYNC.clear()
            telefonia._LAST_SYNC.update(original_status)

    def test_resume_sync_limpa_evento_e_marca_status_running(self):
        original_task = telefonia._LAST_SYNC_TASK
        original_event = telefonia._LAST_SYNC_CANCEL_EVENT
        original_pause_event = telefonia._LAST_SYNC_PAUSE_EVENT
        original_status = dict(telefonia._LAST_SYNC)
        pause_event = threading.Event()
        pause_event.set()
        try:
            telefonia._LAST_SYNC_TASK = SimpleNamespace(done=lambda: False, cancel=lambda: None)
            telefonia._LAST_SYNC_CANCEL_EVENT = threading.Event()
            telefonia._LAST_SYNC_PAUSE_EVENT = pause_event
            telefonia._LAST_SYNC.update({"status": "paused", "result": None})

            result = asyncio.run(telefonia.resume_sync(_user={"username": "admin"}))

            self.assertEqual(result["status"], "running")
            self.assertFalse(pause_event.is_set())
            self.assertEqual(telefonia._LAST_SYNC["status"], "running")
        finally:
            telefonia._LAST_SYNC_TASK = original_task
            telefonia._LAST_SYNC_CANCEL_EVENT = original_event
            telefonia._LAST_SYNC_PAUSE_EVENT = original_pause_event
            telefonia._LAST_SYNC.clear()
            telefonia._LAST_SYNC.update(original_status)

    def test_cancel_sync_limpa_pause_event_se_existir(self):
        original_task = telefonia._LAST_SYNC_TASK
        original_event = telefonia._LAST_SYNC_CANCEL_EVENT
        original_pause_event = telefonia._LAST_SYNC_PAUSE_EVENT
        original_status = dict(telefonia._LAST_SYNC)
        pause_event = threading.Event()
        pause_event.set()  # sync estava pausado quando o usuario cancela.
        try:
            telefonia._LAST_SYNC_TASK = SimpleNamespace(done=lambda: False, cancel=lambda: None)
            telefonia._LAST_SYNC_CANCEL_EVENT = threading.Event()
            telefonia._LAST_SYNC_PAUSE_EVENT = pause_event
            telefonia._LAST_SYNC.update({"status": "paused", "result": None})

            asyncio.run(telefonia.cancel_sync(_user={"username": "admin"}))

            self.assertFalse(pause_event.is_set())  # cancel limpou.
            self.assertTrue(telefonia._LAST_SYNC_CANCEL_EVENT.is_set())
        finally:
            telefonia._LAST_SYNC_TASK = original_task
            telefonia._LAST_SYNC_CANCEL_EVENT = original_event
            telefonia._LAST_SYNC_PAUSE_EVENT = original_pause_event
            telefonia._LAST_SYNC.clear()
            telefonia._LAST_SYNC.update(original_status)

    def test_auditar_endpoint_retorna_202_processing_e_agenda_background_task(self):
        """Endpoint deve retornar 202 imediatamente apos validacoes, sem rodar IA.

        Padrao long-running: validacoes rapidas + agendamento de BackgroundTask + 202.
        Evita HTTP 504 quando IA leva 1-5 min e ha proxy com timeout curto na frente.
        """
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=_queue_item()):
            with patch("repositories.operators.resolve_auditable_colaborador",
                return_value={"name": "Operador Teste", "matricula": "MAT-1", "preferredId": "OP-1"},
            ):
                with patch.object(telefonia, "load_classified_audio") as load_media:
                    with patch.object(telefonia, "process_audit_with_ai", new=AsyncMock()) as process_audio:
                        with patch.object(telefonia.database, "persist_audit_artifacts") as persist:
                            with patch("repositories.admin_criteria.get_criteria", return_value=[SimpleNamespace(id="C1")]):
                                with patch.object(telefonia, "_start_audit_task") as start_task:
                                    with patch.object(
                                        telefonia.classification_review,
                                        "tentar_iniciar_processamento_auditoria",
                                        return_value={"started": True, "status": "pending"},
                                    ) as claim:
                                        result = asyncio.run(
                                            telefonia.auditar_instantaneamente_gravacao(
                                                "hash-123",
                                                user={"username": "admin"},
                                            )
                                        )

        # Resposta rapida (sem IA, sem persist)
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["input_hash"], "hash-123")
        self.assertIn("started_at", result)
        load_media.assert_not_called()
        process_audio.assert_not_awaited()
        persist.assert_not_called()
        # Fila marcada como processing antes de retornar
        claim.assert_called_once()
        self.assertEqual(claim.call_args.kwargs["metadata_merge"]["audit_task_status"], "processing")
        start_task.assert_called_once()
        self.assertEqual(start_task.call_args.args[0], "hash-123")

    async def _run_auditar_endpoint_until_background_persist(self, item: dict, user: dict):
        audit_result = SimpleNamespace(
            score=8.0,
            maxPossibleScore=10.0,
            source_type="audio",
            operatorName="Operador Teste",
            operatorId="OP-1",
        )
        ctx = {
            "sector_id": "logistica",
            "alert_id": "ENTREGA",
            "operator_name": "Operador Teste",
            "operator_id": "MAT-1",
            "source_type": "audio",
            "filename": item["nome_arquivo"],
            "media_path": item["metadata"]["classified_audio_path"],
            "pipeline_context": None,
        }
        started_tasks = []

        def start_task(input_hash: str, **kwargs):
            task = asyncio.create_task(
                telefonia._process_audit_background_task(input_hash=input_hash, **kwargs)
            )
            started_tasks.append(task)
            return task

        with patch.object(
            telefonia.classification_review,
            "obter_fila_revisao_classificacao_por_hash",
            return_value=item,
        ):
            with patch.object(telefonia, "_extract_audit_context", return_value=ctx):
                with patch.object(telefonia, "_validate_audit_context_or_raise", return_value=ctx):
                    with patch.object(
                        telefonia.classification_review,
                        "tentar_iniciar_processamento_auditoria",
                        return_value={"started": True, "status": "pending"},
                    ) as claim:
                        with patch.object(telefonia, "_start_audit_task", side_effect=start_task):
                            with patch.object(telefonia, "load_classified_audio", return_value=b"RIFFdemo"):
                                with patch.object(
                                    telefonia,
                                    "_build_alert_from_classification",
                                    return_value=SimpleNamespace(label="Entrega"),
                                ):
                                    with patch.object(
                                        telefonia,
                                        "process_audit_with_ai",
                                        new=AsyncMock(return_value=(audit_result, "audit-hash", False)),
                                    ):
                                        with patch.object(
                                            telefonia.database,
                                            "persist_audit_artifacts",
                                            return_value=77,
                                        ) as persist:
                                            with patch.object(
                                                telefonia,
                                                "_sync_saved_file_for_manual_audit",
                                                new=AsyncMock(return_value=True),
                                            ) as sync_saved:
                                                with patch.object(
                                                    telefonia.classification_review,
                                                    "atualizar_status_fila_revisao_classificacao",
                                                    return_value=True,
                                                ) as update_status:
                                                    result = await telefonia.auditar_instantaneamente_gravacao(
                                                        item["input_hash"],
                                                        user=user,
                                                    )
                                                    self.assertEqual(len(started_tasks), 1)
                                                    await started_tasks[0]

        return result, persist, sync_saved, update_status, claim

    def test_auditar_endpoint_audio_automatico_persiste_criado_por_automacao(self):
        item = _queue_item("pending")
        item["metadata"] = {**item["metadata"], "is_manual": False}

        result, persist, sync_saved, update_status, claim = asyncio.run(
            self._run_auditar_endpoint_until_background_persist(
                item,
                user={"username": "admin"},
            )
        )

        self.assertEqual(result["status"], "processing")
        persist.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["criado_por"], "automacao")
        sync_saved.assert_awaited_once_with(77, criado_por="automacao")
        self.assertEqual(
            claim.call_args.kwargs["metadata_merge"]["audit_task_requested_by"],
            "admin",
        )
        self.assertEqual(
            update_status.call_args.kwargs["metadata_merge"]["telefonia_audit_requested_by"],
            "admin",
        )

    def test_auditar_endpoint_audio_manual_preserva_username_em_criado_por(self):
        item = _queue_item("pending")
        item["metadata"] = {**item["metadata"], "is_manual": True}

        result, persist, sync_saved, update_status, claim = asyncio.run(
            self._run_auditar_endpoint_until_background_persist(
                item,
                user={"username": "auditor"},
            )
        )

        self.assertEqual(result["status"], "processing")
        persist.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["criado_por"], "auditor")
        sync_saved.assert_awaited_once_with(77, criado_por="auditor")
        self.assertEqual(
            claim.call_args.kwargs["metadata_merge"]["audit_task_requested_by"],
            "auditor",
        )
        self.assertEqual(
            update_status.call_args.kwargs["metadata_merge"]["telefonia_audit_requested_by"],
            "auditor",
        )

    def test_auditar_endpoint_rejeita_quando_task_ja_em_processing_recente(self):
        """Evita duplo-agendamento se usuario clica duas vezes rapidamente."""
        item = _queue_item("pending")
        item["metadata"] = {
            **item["metadata"],
            "audit_task_status": "processing",
            "audit_task_started_at": datetime.now(timezone.utc).isoformat(),
        }
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    telefonia.auditar_instantaneamente_gravacao(
                        "hash-123",
                        user={"username": "admin"},
                    )
                )

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("ja em processamento", ctx.exception.detail.lower())

    def test_validate_audit_context_rejects_unknown_sector(self):
        item = _queue_item()
        ctx = {
            "sector_id": "setor_inexistente",
            "alert_id": "ENTREGA",
            "operator_name": "Operador Teste",
            "operator_id": "MAT-1",
            "source_type": "audio",
            "filename": "call.wav",
            "pipeline_context": None,
        }

        with patch("repositories.admin_criteria.get_criteria", return_value=[SimpleNamespace(id="C1")]):
            with self.assertRaises(HTTPException) as exc:
                telefonia._validate_audit_context_or_raise(ctx, item)

        self.assertEqual(exc.exception.status_code, 400)
        self.assertIn("Setor", exc.exception.detail)

    def test_auditar_endpoint_rejeita_quando_cota_mensal_excedida(self):
        item = _queue_item("pending")
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch("repositories.admin_criteria.get_criteria", return_value=[SimpleNamespace(id="C1")]):
                with patch("repositories.operators.resolve_auditable_colaborador",
                    return_value={"name": "Operador Teste", "matricula": "MAT-1", "preferredId": "OP-1"},
                ):
                    with patch.object(telefonia, "_get_telefonia_monthly_audit_quota", return_value=2):
                        with patch.object(telefonia.audits, "get_operator_audit_count_for_month", return_value=2):
                            with patch.object(
                                telefonia.classification_review,
                                "atualizar_status_fila_revisao_classificacao",
                                return_value=True,
                            ) as update_status:
                                with self.assertRaises(HTTPException) as exc:
                                    asyncio.run(
                                        telefonia.auditar_instantaneamente_gravacao(
                                            "hash-123",
                                            user={"username": "admin"},
                                        )
                                    )

        self.assertEqual(exc.exception.status_code, 429)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.kwargs["status"], "monthly_capped")
        self.assertEqual(update_status.call_args.kwargs["motivos_revisao_append"], ["cota_mensal_atingida"])
        self.assertEqual(update_status.call_args.kwargs["metadata_merge"]["monthly_cap_operator"], "Operador Teste")

    def test_auditar_endpoint_libera_quando_task_em_processing_estagnado(self):
        """Task com started_at > 10min e considerado stale e nao bloqueia novo run."""
        stale_started_at = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        item = _queue_item("pending")
        item["metadata"] = {
            **item["metadata"],
            "audit_task_status": "processing",
            "audit_task_started_at": stale_started_at,
        }
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch("repositories.operators.resolve_auditable_colaborador",
                return_value={"name": "Operador Teste", "matricula": "MAT-1", "preferredId": "OP-1"},
            ):
                with patch("repositories.admin_criteria.get_criteria", return_value=[SimpleNamespace(id="C1")]):
                    with patch.object(telefonia, "_start_audit_task") as start_task:
                        with patch.object(
                            telefonia.classification_review,
                            "tentar_iniciar_processamento_auditoria",
                            return_value={"started": True, "status": "pending"},
                        ):
                            result = asyncio.run(
                                telefonia.auditar_instantaneamente_gravacao(
                                    "hash-123",
                                    user={"username": "admin"},
                                )
                            )

        self.assertEqual(result["status"], "processing")
        start_task.assert_called_once()

    def test_process_audit_background_task_persiste_audit_e_marca_fila_como_audited(self):
        """Executa o fluxo de IA completo e atualiza fila com audit_task_status='completed'."""
        audit_result = SimpleNamespace(
            score=8.0, maxPossibleScore=10.0, source_type="audio",
            operatorName="Operador Teste", operatorId="OP-1",
        )
        alert = SimpleNamespace(label="Entrega")
        with patch.object(telefonia, "load_classified_audio", return_value=b"RIFFdemo") as load_media:
            with patch.object(telefonia, "_build_alert_from_classification", return_value=alert) as build_alert:
                with patch.object(
                    telefonia, "process_audit_with_ai",
                    new=AsyncMock(return_value=(audit_result, "audit-hash", False)),
                ) as process_audio:
                    with patch.object(telefonia.database, "persist_audit_artifacts", return_value=77) as persist:
                        with patch.object(
                            telefonia, "_sync_saved_file_for_manual_audit",
                            new=AsyncMock(return_value=True),
                        ) as sync_saved:
                            with patch.object(
                                telefonia.classification_review,
                                "atualizar_status_fila_revisao_classificacao",
                                return_value=True,
                            ) as update_status:
                                asyncio.run(
                                    telefonia._process_audit_background_task(
                                        input_hash="hash-123",
                                        sector_id="logistica",
                                        alert_id="ENTREGA",
                                        operator_name="Operador Teste",
                                        operator_id="MAT-1",
                                        source_type="audio",
                                        filename="call.wav",
                                        media_path="hash-123.wav",
                                        criado_por="admin",
                                    )
                                )

        load_media.assert_called_once_with("hash-123.wav", input_hash="hash-123")
        build_alert.assert_called_once_with("logistica", "ENTREGA")
        process_audio.assert_awaited_once()
        persist.assert_called_once()
        self.assertIs(persist.call_args.kwargs["sync_saved_file"], False)
        self.assertEqual(persist.call_args.kwargs["criado_por"], "admin")
        sync_saved.assert_awaited_once_with(77, criado_por="admin")
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.kwargs["status"], "audited")
        merge = update_status.call_args.kwargs["metadata_merge"]
        self.assertEqual(merge["audit_id"], 77)
        self.assertEqual(merge["audit_task_status"], "completed")
        self.assertEqual(merge["audit_input_hash"], "audit-hash")
        self.assertTrue(merge["audit_task_saved_file_available"])

    def test_process_audit_background_task_preserva_timestamp_da_ia_sem_converter_huawei_begin_time(self):
        audit_result = SimpleNamespace(
            score=8.0, maxPossibleScore=10.0, source_type="audio",
            operatorName="Operador Teste", operatorId="OP-1",
            timestamp="2026-05-20T12:00:00",
            audio_date=None,
        )
        huawei_begin_time = 1778670000000  # 2026-05-13 08:00:00 America/Sao_Paulo
        pipeline_context = {
            "origin": "telefonia_manual",
            "source_type": "audio",
            "filename": "call.wav",
            "sector_id": "logistica",
            "alert_id": "ENTREGA",
            "operator_name": "Operador Teste",
            "operator_id": "MAT-1",
            "media_path": "hash-123.wav",
            "source_metadata": {"huawei_begin_time": str(huawei_begin_time)},
        }

        with patch.object(telefonia, "load_classified_audio", return_value=b"RIFFdemo"):
            with patch.object(telefonia, "_build_alert_from_classification", return_value=SimpleNamespace(label="Entrega")):
                with patch.object(
                    telefonia, "process_audit_with_ai",
                    new=AsyncMock(return_value=(audit_result, "audit-hash", False)),
                ):
                    with patch.object(telefonia.database, "persist_audit_artifacts", return_value=77) as persist:
                        with patch.object(telefonia, "_sync_saved_file_for_manual_audit", new=AsyncMock(return_value=True)):
                            with patch.object(
                                telefonia.classification_review,
                                "atualizar_status_fila_revisao_classificacao",
                                return_value=True,
                            ):
                                asyncio.run(
                                    telefonia._process_audit_background_task(
                                        input_hash="hash-123",
                                        sector_id="logistica",
                                        alert_id="ENTREGA",
                                        operator_name="Operador Teste",
                                        operator_id="MAT-1",
                                        source_type="audio",
                                        filename="call.wav",
                                        media_path="hash-123.wav",
                                        criado_por="admin",
                                        pipeline_context=pipeline_context,
                                    )
                                )

        persisted_result = persist.call_args.args[0]
        self.assertIsNone(persisted_result.audio_date)
        self.assertEqual(persisted_result.timestamp, "2026-05-20T12:00:00")

    def test_process_audit_background_task_registra_falha_na_metadata_quando_ia_lanca_excecao(self):
        """IA lanca -> task captura, NAO levanta, e marca audit_task_status='failed'.

        Frontend pega o erro via polling do endpoint /audit-status.
        """
        with patch.object(telefonia, "load_classified_audio", return_value=b"RIFFdemo"):
            with patch.object(telefonia, "_build_alert_from_classification", return_value=SimpleNamespace(label="X")):
                with patch.object(
                    telefonia, "process_audit_with_ai",
                    new=AsyncMock(side_effect=RuntimeError("timeout no Azure OpenAI")),
                ):
                    with patch.object(telefonia.database, "persist_audit_artifacts") as persist:
                        with patch.object(
                            telefonia.classification_review,
                            "atualizar_status_fila_revisao_classificacao",
                            return_value=True,
                        ) as update_status:
                            # NAO deve levantar — erro fica na metadata pro frontend
                            asyncio.run(
                                telefonia._process_audit_background_task(
                                    input_hash="hash-err",
                                    sector_id="logistica",
                                    alert_id="ENTREGA",
                                    operator_name="X",
                                    operator_id="Y",
                                    source_type="audio",
                                    filename="x.wav",
                                    media_path="x.wav",
                                    criado_por="admin",
                                )
                            )

        persist.assert_not_called()
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.kwargs["status"], "pending")
        merge = update_status.call_args.kwargs["metadata_merge"]
        self.assertEqual(merge["audit_task_status"], "failed")
        self.assertIn("timeout no Azure OpenAI", merge["audit_task_error"])

    def test_process_audit_background_task_respeita_cancelamento_antes_de_carregar_midia(self):
        item = _queue_item()
        item["metadata"] = {**item["metadata"], "audit_task_status": "canceled"}
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            with patch.object(telefonia, "load_classified_audio") as load_media:
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(
                        telefonia._process_audit_background_task(
                            input_hash="hash-123",
                            sector_id="logistica",
                            alert_id="ENTREGA",
                            operator_name="X",
                            operator_id="Y",
                            source_type="audio",
                            filename="x.wav",
                            media_path="x.wav",
                            criado_por="admin",
                        )
                    )

        load_media.assert_not_called()

    def test_cancelar_auditoria_cancela_task_ativa_e_reseta_metadata(self):
        class FakeTask:
            def __init__(self):
                self.cancel_called = False

            def done(self):
                return False

            def cancel(self):
                self.cancel_called = True

        item = _queue_item()
        item["metadata"] = {**item["metadata"], "audit_task_status": "processing"}
        task = FakeTask()
        telefonia._ACTIVE_AUDIT_TASKS["hash-123"] = task
        try:
            with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
                with patch.object(
                    telefonia.classification_review,
                    "atualizar_status_fila_revisao_classificacao",
                    return_value=True,
                ) as update_status:
                    result = asyncio.run(telefonia.cancelar_auditoria("hash-123", _user={"username": "admin"}))
        finally:
            telefonia._ACTIVE_AUDIT_TASKS.pop("hash-123", None)

        self.assertTrue(result["success"])
        self.assertTrue(result["task_cancel_requested"])
        self.assertTrue(task.cancel_called)
        update_status.assert_called_once()
        self.assertEqual(update_status.call_args.kwargs["status"], "pending")
        self.assertEqual(update_status.call_args.kwargs["metadata_merge"]["audit_task_status"], "canceled")

    def test_consultar_status_auditoria_retorna_idle_quando_sem_task(self):
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=_queue_item()):
            result = asyncio.run(telefonia.consultar_status_auditoria("hash-123", _user={"username": "admin"}))
        self.assertEqual(result["status"], "idle")

    def test_consultar_status_auditoria_retorna_processing_com_started_at(self):
        started = datetime.now(timezone.utc).isoformat()
        item = _queue_item()
        item["metadata"] = {**item["metadata"], "audit_task_status": "processing", "audit_task_started_at": started}
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            result = asyncio.run(telefonia.consultar_status_auditoria("hash-123", _user={"username": "admin"}))
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["started_at"], started)

    def test_consultar_status_auditoria_retorna_completed_com_audit_id(self):
        item = _queue_item(status="audited")
        item["metadata"] = {**item["metadata"], "audit_id": 77, "audit_task_saved_file_available": True}
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            result = asyncio.run(telefonia.consultar_status_auditoria("hash-123", _user={"username": "admin"}))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["audit_id"], 77)
        self.assertTrue(result["saved_file_available"])

    def test_consultar_status_auditoria_retorna_failed_com_erro(self):
        item = _queue_item()
        item["metadata"] = {**item["metadata"], "audit_task_status": "failed", "audit_task_error": "Azure quota"}
        with patch.object(telefonia.classification_review, "obter_fila_revisao_classificacao_por_hash", return_value=item):
            result = asyncio.run(telefonia.consultar_status_auditoria("hash-123", _user={"username": "admin"}))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_message"], "Azure quota")


class TestClassifyConcurrencySemaphore(unittest.TestCase):
    """Semaforo global de concorrencia das classificacoes manuais (cap Azure)."""

    def setUp(self):
        telefonia._classify_semaphore_state = None

    def tearDown(self):
        telefonia._classify_semaphore_state = None

    def test_default_3_e_reuso_no_mesmo_loop(self):
        async def _check():
            os.environ.pop("TELEFONIA_CLASSIFY_MAX_CONCURRENCY", None)
            telefonia._classify_semaphore_state = None
            sem1 = telefonia._get_classify_semaphore()
            sem2 = telefonia._get_classify_semaphore()
            self.assertIs(sem1, sem2)  # reusa no mesmo loop
            await sem1.acquire()
            await sem1.acquire()
            await sem1.acquire()
            self.assertTrue(sem1.locked())  # default 3 -> cheio apos 3
            sem1.release()
            sem1.release()
            sem1.release()

        asyncio.run(_check())

    def test_env_define_o_cap(self):
        async def _check():
            with patch.dict(os.environ, {"TELEFONIA_CLASSIFY_MAX_CONCURRENCY": "2"}, clear=False):
                telefonia._classify_semaphore_state = None
                sem = telefonia._get_classify_semaphore()
                await sem.acquire()
                await sem.acquire()
                self.assertTrue(sem.locked())  # cap 2 -> cheio apos 2
                sem.release()
                sem.release()

        asyncio.run(_check())

    def test_env_invalido_cai_no_default(self):
        async def _check():
            with patch.dict(os.environ, {"TELEFONIA_CLASSIFY_MAX_CONCURRENCY": "abc"}, clear=False):
                telefonia._classify_semaphore_state = None
                sem = telefonia._get_classify_semaphore()
                await sem.acquire()
                await sem.acquire()
                self.assertFalse(sem.locked())  # default 3 -> 3o slot ainda livre
                await sem.acquire()
                self.assertTrue(sem.locked())
                sem.release()
                sem.release()
                sem.release()

        asyncio.run(_check())


if __name__ == "__main__":
    unittest.main()
