import asyncio
import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, ANY

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.automation as automation
from db.domain_constants import (
    REVIEW_QUEUE_READY_STATUSES,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    REVIEW_QUEUE_STATUS_REVIEWED,
)
from repositories.classification_review import (
    corrigir_classificacao_fila_revisao,
    listar_fila_revisao_classificacao,
    obter_fila_revisao_classificacao_por_hash,
    sincronizar_fila_revisao_classificacao,
    tentar_iniciar_processamento_auditoria,
)
from repositories.common import normalize_review_status


class _FakeCursor:
    def __init__(self, *, fetchone_results=None, fetchall_results=None):
        self.fetchone_results = list(fetchone_results or [])
        self.fetchall_results = list(fetchall_results or [])
        self.executed = []

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        return list(self.fetchall_results)


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class TestReviewQueueContract(unittest.TestCase):
    def test_normalize_review_status_maps_legacy_aliases(self):
        self.assertEqual(normalize_review_status("classificado"), REVIEW_QUEUE_STATUS_AUTO_RESOLVED)
        self.assertEqual(normalize_review_status("auditado"), "audited")
        self.assertEqual(normalize_review_status("ignorado"), REVIEW_QUEUE_STATUS_MONTHLY_CAPPED)
        self.assertEqual(normalize_review_status("ready"), REVIEW_QUEUE_STATUS_READY_FOR_AUDIT)
        self.assertEqual(normalize_review_status("needs_manual_triage"), REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)
        self.assertEqual(normalize_review_status("blocked_operator"), REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR)

    def test_sync_inserts_auto_resolved_item_when_review_is_not_needed(self):
        cursor = _FakeCursor(fetchone_results=[None, {"id": 77}])
        conn = _FakeConnection(cursor)

        review_id = sincronizar_fila_revisao_classificacao(
            lambda: conn,
            input_hash="hash-auto",
            nome_arquivo="call.wav",
            setor_previsto="logistica",
            alerta_previsto="4.4.1",
            confianca=0.95,
            operador_previsto="Operador X",
            precisa_revisao=False,
        )

        self.assertEqual(review_id, 77)
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)
        query, params = cursor.executed[-1]
        self.assertIn("INSERT INTO fila_revisao_classificacao", query)
        self.assertIn(REVIEW_QUEUE_STATUS_AUTO_RESOLVED, params)

    def test_sync_does_not_overwrite_protected_reviewed_item(self):
        cursor = _FakeCursor(fetchone_results=[{"id": 88, "status": REVIEW_QUEUE_STATUS_REVIEWED}])
        conn = _FakeConnection(cursor)

        review_id = sincronizar_fila_revisao_classificacao(
            lambda: conn,
            input_hash="hash-reviewed",
            nome_arquivo="call.wav",
            setor_previsto="logistica",
            alerta_previsto="4.4.1",
            confianca=0.91,
            operador_previsto="Operador X",
            precisa_revisao=False,
        )

        self.assertEqual(review_id, 88)
        self.assertFalse(conn.committed)
        self.assertTrue(conn.closed)
        self.assertEqual(len(cursor.executed), 1)
        query, params = cursor.executed[0]
        self.assertIn("SELECT id, status FROM fila_revisao_classificacao", query)
        self.assertEqual(params, ("hash-reviewed",))

    def test_try_start_audit_task_claims_row_with_transaction_lock(self):
        cursor = _FakeCursor(fetchone_results=[{"status": REVIEW_QUEUE_STATUS_PENDING, "metadata_json": "{}"}])
        conn = _FakeConnection(cursor)

        result = tentar_iniciar_processamento_auditoria(
            lambda: conn,
            "hash-claim",
            status=REVIEW_QUEUE_STATUS_PENDING,
            metadata_merge={"audit_task_status": "processing", "audit_task_started_at": "2026-05-21T10:00:00+00:00"},
        )

        self.assertTrue(result["started"])
        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)
        self.assertIn("FOR UPDATE", cursor.executed[0][0])
        update_query, update_params = cursor.executed[-1]
        self.assertIn("UPDATE fila_revisao_classificacao", update_query)
        self.assertEqual(update_params[0], REVIEW_QUEUE_STATUS_PENDING)
        self.assertIn('"audit_task_status": "processing"', update_params[1])

    def test_try_start_audit_task_blocks_recent_processing(self):
        metadata = {
            "audit_task_status": "processing",
            "audit_task_started_at": datetime.now(timezone.utc).isoformat(),
        }
        cursor = _FakeCursor(fetchone_results=[{
            "status": REVIEW_QUEUE_STATUS_PENDING,
            "metadata_json": __import__("json").dumps(metadata),
        }])
        conn = _FakeConnection(cursor)

        result = tentar_iniciar_processamento_auditoria(
            lambda: conn,
            "hash-claim",
            status=REVIEW_QUEUE_STATUS_PENDING,
            metadata_merge={"audit_task_status": "processing"},
            inflight_timeout_seconds=int(timedelta(minutes=10).total_seconds()),
        )

        self.assertFalse(result["started"])
        self.assertEqual(result["reason"], "processing")
        self.assertFalse(conn.committed)
        self.assertTrue(conn.rolled_back)
        self.assertEqual(len(cursor.executed), 1)

    def test_ready_for_audit_query_excludes_current_monthly_cap(self):
        cursor = _FakeCursor(fetchall_results=[])
        conn = _FakeConnection(cursor)

        listar_fila_revisao_classificacao(
            lambda: conn,
            limit=50,
            status=REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
        )

        query, params = cursor.executed[-1]
        self.assertIn("monthly_cap_period", query)
        self.assertEqual(params[0], list(REVIEW_QUEUE_READY_STATUSES))
        self.assertEqual(params[1], REVIEW_QUEUE_STATUS_MONTHLY_CAPPED)
        self.assertEqual(params[2], datetime.now().strftime("%Y-%m"))
        self.assertEqual(params[-1], 50)

    def test_pending_query_includes_manual_triage_block_statuses(self):
        cursor = _FakeCursor(fetchall_results=[])
        conn = _FakeConnection(cursor)

        listar_fila_revisao_classificacao(
            lambda: conn,
            limit=25,
            status=REVIEW_QUEUE_STATUS_PENDING,
        )

        query, params = cursor.executed[-1]
        self.assertIn("status = ANY", query)
        self.assertEqual(params[0], REVIEW_QUEUE_STATUS_PENDING)
        self.assertIn(REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE, params[1])
        self.assertIn(REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR, params[1])
        self.assertEqual(params[-1], 25)

    def test_huawei_queue_uses_official_operator_from_huawei_id(self):
        cursor = _FakeCursor(
            fetchall_results=[
                {
                    "id": 2101,
                    "input_hash": "hash-huawei",
                    "nome_arquivo": "call.wav",
                    "setor_previsto": "cadastro",
                    "alerta_previsto": "desconhecido",
                    "confianca": 0.0,
                    "operador_previsto": "Operador Teste",
                    "erro": None,
                    "prioridade": "medium",
                    "motivos_json": "[]",
                    "metadata_json": __import__("json").dumps(
                        {
                            "origem": "huawei_sync",
                            "operator_id_huawei_real": "189",
                            "id_huawei": "189",
                            "operator_id": "189",
                        }
                    ),
                    "status": REVIEW_QUEUE_STATUS_PENDING,
                    "criado_em": None,
                    "atualizado_em": None,
                    "is_oficial": True,
                    "official_operator_name": "Jhaves Daniel Marques",
                    "official_operator_id_huawei": "189",
                    "official_operator_matricula": "11223",
                    "official_operator_name_by_name": None,
                    "official_operator_id_huawei_by_name": None,
                    "official_operator_matricula_by_name": None,
                }
            ]
        )
        conn = _FakeConnection(cursor)

        result = listar_fila_revisao_classificacao(
            lambda: conn,
            limit=10,
            status=REVIEW_QUEUE_STATUS_PENDING,
            origem="huawei_sync",
        )

        query, _ = cursor.executed[-1]
        self.assertIn("official_by_huawei", query)
        self.assertIn("operator_id_huawei_real", query)
        self.assertTrue(result[0]["is_oficial"])
        self.assertEqual(result[0]["operator_name"], "Jhaves Daniel Marques")
        self.assertEqual(result[0]["operator_id"], "189")
        self.assertEqual(result[0]["operator_matricula"], "11223")
        self.assertEqual(result[0]["matricula"], "11223")

    def test_huawei_queue_matches_any_normalized_huawei_identifier(self):
        cursor = _FakeCursor(fetchall_results=[])
        conn = _FakeConnection(cursor)

        listar_fila_revisao_classificacao(
            lambda: conn,
            limit=10,
            status=REVIEW_QUEUE_STATUS_PENDING,
            origem="huawei_sync",
        )

        query, _ = cursor.executed[-1]
        self.assertIn("official_by_huawei", query)
        self.assertIn("= ANY(ARRAY[", query)
        self.assertIn("regexp_replace", query)
        self.assertNotIn("TRIM(c.id_huawei) = COALESCE", query)
        for key in ("operator_id_huawei_real", "huawei_work_no", "agentId", "workNo", "operatorId", "idHuawei"):
            self.assertIn(key, query)

    def test_listar_query_materializes_metadata_jsonb_once(self):
        # Perf guard: a listagem materializa metadata_json::jsonb UMA vez por linha
        # (CTE f_base._mj) antes dos LATERAL joins. Antes, o candidato Huawei
        # `= ANY(ARRAY[...13 chaves...])` re-parseava o JSONB de cada linha da fila
        # a cada linha de colaboradores (seq scan), levando a listagem a ~30s. Se
        # alguem reintroduzir o re-parse no LATERAL, o `f._mj ->> ...` some e este
        # teste quebra.
        cursor = _FakeCursor(fetchall_results=[])
        conn = _FakeConnection(cursor)
        listar_fila_revisao_classificacao(
            lambda: conn, limit=100, status="all", origem="huawei_sync", order_by="recent"
        )
        query, _ = cursor.executed[-1]
        self.assertIn("MATERIALIZED", query)
        self.assertIn("AS _mj", query)
        # candidatos Huawei e match por nome leem o jsonb ja materializado em _mj
        self.assertIn("f._mj ->> 'operator_id_huawei_real'", query)
        self.assertIn("f._mj ->> 'operator_name'", query)

    def test_huawei_queue_uses_official_matricula_from_name_match(self):
        cursor = _FakeCursor(
            fetchall_results=[
                {
                    "id": 2102,
                    "input_hash": "hash-huawei-name",
                    "nome_arquivo": "call-name.wav",
                    "setor_previsto": "cadastro",
                    "alerta_previsto": "desconhecido",
                    "confianca": 0.0,
                    "operador_previsto": "Amanda Muslera",
                    "erro": None,
                    "prioridade": "medium",
                    "motivos_json": "[]",
                    "metadata_json": __import__("json").dumps(
                        {
                            "origem": "huawei_sync",
                            "operator_id_huawei_real": "99999",
                            "operator_name": "Amanda Muslera",
                        }
                    ),
                    "status": REVIEW_QUEUE_STATUS_PENDING,
                    "criado_em": None,
                    "atualizado_em": None,
                    "is_oficial": True,
                    "official_operator_name": None,
                    "official_operator_id_huawei": None,
                    "official_operator_matricula": None,
                    "official_operator_name_by_name": "Amanda Muslera",
                    "official_operator_id_huawei_by_name": "189",
                    "official_operator_matricula_by_name": "11223",
                }
            ]
        )
        conn = _FakeConnection(cursor)

        result = listar_fila_revisao_classificacao(
            lambda: conn,
            limit=10,
            status=REVIEW_QUEUE_STATUS_PENDING,
            origem="huawei_sync",
        )

        query, _ = cursor.executed[-1]
        self.assertIn("official_by_name", query)
        self.assertTrue(result[0]["is_oficial"])
        self.assertEqual(result[0]["operator_name"], "Amanda Muslera")
        self.assertEqual(result[0]["operator_matricula"], "11223")
        self.assertEqual(result[0]["matricula"], "11223")

    def test_huawei_queue_hash_lookup_enriches_operator_matricula(self):
        cursor = _FakeCursor(
            fetchone_results=[
                {
                    "id": 2103,
                    "input_hash": "hash-huawei",
                    "nome_arquivo": "call.wav",
                    "setor_previsto": "cadastro",
                    "alerta_previsto": "desconhecido",
                    "confianca": 0.0,
                    "operador_previsto": "Operador Teste",
                    "erro": None,
                    "prioridade": "medium",
                    "motivos_json": "[]",
                    "metadata_json": __import__("json").dumps(
                        {
                            "origem": "huawei_sync",
                            "operator_id_huawei_real": "189.0",
                            "huawei_work_no": "189",
                        }
                    ),
                    "status": REVIEW_QUEUE_STATUS_PENDING,
                    "criado_em": None,
                    "atualizado_em": None,
                    "is_oficial": True,
                    "official_operator_name": "Jhaves Daniel Marques",
                    "official_operator_id_huawei": "189",
                    "official_operator_matricula": "11223",
                    "official_operator_name_by_name": None,
                    "official_operator_id_huawei_by_name": None,
                    "official_operator_matricula_by_name": None,
                }
            ]
        )
        conn = _FakeConnection(cursor)

        result = obter_fila_revisao_classificacao_por_hash(lambda: conn, "hash-huawei")

        query, params = cursor.executed[-1]
        self.assertIn("= ANY(ARRAY[", query)
        self.assertNotIn("{_normalize_huawei_id_sql", query)
        self.assertEqual(params, ("hash-huawei",))
        self.assertTrue(result["is_oficial"])
        self.assertEqual(result["operator_name"], "Jhaves Daniel Marques")
        self.assertEqual(result["operator_id"], "189")
        self.assertEqual(result["operator_matricula"], "11223")
        self.assertEqual(result["matricula"], "11223")

    def test_manual_correction_persists_reviewed_status_and_metadata_trace(self):
        existing_row = {
            "id": 10,
            "input_hash": "hash-review",
            "nome_arquivo": "call.wav",
            "setor_previsto": "transferencia",
            "alerta_previsto": "UTI-DESVIO-MOT",
            "confianca": 0.63,
            "operador_previsto": "Operador X",
            "erro": "erro anterior",
            "prioridade": "high",
            "motivos_json": '["baixa_confianca", "direction_mismatch"]',
            "metadata_json": '{"classified_audio_path":"hash-review.wav"}',
            "status": REVIEW_QUEUE_STATUS_PENDING,
            "criado_em": "2026-04-08T10:00:00",
            "atualizado_em": "2026-04-08T10:00:00",
        }
        updated_row = dict(existing_row)
        updated_row.update(
            {
                "setor_previsto": "logistica",
                "alerta_previsto": "LOGISTICA-PARADA",
                "operador_previsto": "Operador Corrigido",
                "erro": None,
                "prioridade": "low",
                "motivos_json": "[]",
                "status": "reviewed",
            }
        )
        cursor = _FakeCursor(fetchone_results=[existing_row, updated_row])
        conn = _FakeConnection(cursor)

        result = corrigir_classificacao_fila_revisao(
            lambda: conn,
            "hash-review",
            setor_previsto="logistica",
            alerta_previsto="LOGISTICA-PARADA",
            operador_previsto="Operador Corrigido",
            operator_id="HUA-123",
            revisado_por="tester",
        )

        self.assertTrue(conn.committed)
        self.assertTrue(conn.closed)
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["setor_previsto"], "logistica")
        self.assertEqual(result["alerta_previsto"], "LOGISTICA-PARADA")
        self.assertEqual(result["motivos_revisao"], [])
        update_query, update_params = cursor.executed[1]
        self.assertIn("UPDATE fila_revisao_classificacao", update_query)
        self.assertEqual(update_params[2], "Operador Corrigido")
        metadata_payload = update_params[5]
        self.assertIn('"manual_review_source": "triagem_ui"', metadata_payload)
        self.assertIn('"manual_reviewed_by": "tester"', metadata_payload)
        self.assertIn('"setor_previsto": "transferencia"', metadata_payload)
        self.assertIn('"alerta_previsto": "UTI-DESVIO-MOT"', metadata_payload)
        self.assertIn('"operator_id": "HUA-123"', metadata_payload)

    @patch.object(automation.database, "listar_paths_audio_classificado_fila_revisao", return_value=["keep.wav"])
    def test_cleanup_classified_audio_storage_keeps_referenced_and_removes_old_orphans(self, mock_list_paths):
        temp_root = Path(os.getcwd()) / "tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_dir = temp_root / f"classified_audio_test_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        with patch.dict(os.environ, {"CLASSIFIED_AUDIO_STORAGE_DIR": str(temp_dir)}, clear=False):
            keep_path = temp_dir / "keep.wav"
            orphan_path = temp_dir / "old-orphan.wav"
            recent_path = temp_dir / "recent-orphan.wav"
            keep_path.write_bytes(b"keep")
            orphan_path.write_bytes(b"old")
            recent_path.write_bytes(b"recent")

            old_timestamp = datetime(2026, 1, 1).timestamp()
            os.utime(orphan_path, (old_timestamp, old_timestamp))

            dry_run = automation.cleanup_classified_audio_storage(retention_days=30, dry_run=True)
            applied = automation.cleanup_classified_audio_storage(retention_days=30, dry_run=False)

        self.assertEqual(dry_run["candidates"], ["old-orphan.wav"])
        self.assertEqual(dry_run["deleted"], [])
        self.assertIn("keep.wav", mock_list_paths.return_value)
        self.assertTrue(keep_path.exists())
        self.assertTrue(recent_path.exists())
        self.assertFalse(orphan_path.exists())
        self.assertEqual(applied["deleted"], ["old-orphan.wav"])
        self.assertEqual(applied["referenced"], 1)

    @patch.object(automation, "_audit_single_item_with_timeout", new_callable=AsyncMock)
    @patch.object(automation.asyncio, "sleep", new_callable=AsyncMock)
    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation.database, "listar_fila_revisao_classificacao")
    def test_audit_all_pending_counts_monthly_capped_item_as_blocked(
        self,
        mock_listar,
        mock_atualizar_status,
        mock_sleep,
        mock_audit_single_item,
    ):
        mock_listar.return_value = [
            {
                "input_hash": "hash-operator",
                "nome_arquivo": "call.wav",
                "operador_previsto": "Operador X",
                "status": REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
                "metadata": {},
            }
        ]
        mock_audit_single_item.return_value = {"status": "monthly_capped"}

        # A meta vem do config no DB e o lote operacional e derivado do budget;
        # fixa ambos para manter o assert limit=3 deterministico.
        with patch.object(automation, "_get_automation_audit_batch_size", return_value=3), patch.object(
            automation,
            "_derive_automation_audit_batch_size",
            return_value=3,
        ):
            result = asyncio.run(automation.audit_all_pending())

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["blocked"], 1)
        mock_listar.assert_called_once_with(limit=3, status=REVIEW_QUEUE_STATUS_READY_FOR_AUDIT)
        mock_audit_single_item.assert_awaited_once_with(
            mock_listar.return_value[0],
            timeout_seconds=ANY,
        )
        mock_sleep.assert_awaited_once_with(0.5)
        mock_atualizar_status.assert_not_called()

    @patch.object(automation.database, "descartar_item_automacao", return_value={"discarded": True})
    @patch.object(automation, "_audit_single_item_with_timeout", new_callable=AsyncMock)
    @patch.object(automation.asyncio, "sleep", new_callable=AsyncMock)
    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation.database, "listar_fila_revisao_classificacao")
    def test_audit_all_pending_discards_huawei_inbound_risk_sector(
        self,
        mock_listar,
        mock_update_status,
        mock_sleep,
        mock_audit_single_item,
        mock_descartar,
    ):
        mock_listar.return_value = [
            {
                "input_hash": "risk-inbound-hash",
                "nome_arquivo": "risk-inbound.wav",
                "operador_previsto": "Operador Risco",
                "setor_previsto": "uti",
                "status": REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
                "metadata": {
                    "origem": "huawei_sync",
                    "huawei_is_call_in": True,
                    "operator_sector_id": "uti",
                },
            }
        ]

        with patch.object(automation, "_get_monthly_audit_quota", return_value=999), patch.object(
            automation.database,
            "update_config",
            return_value=True,
        ), patch.object(
            automation,
            "_config_flag",
            return_value=False,
        ):
            result = asyncio.run(automation.audit_all_pending())

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["completed"], 0)
        # Novo contrato: setor de risco/receptiva nao presta p/ telefonia -> DESCARTA
        # (impossivel), nao prende em triagem.
        self.assertEqual(result["discarded"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["blocked"], 0)
        mock_audit_single_item.assert_not_awaited()
        mock_descartar.assert_called_once()
        self.assertEqual(mock_descartar.call_args.args[0], "risk-inbound-hash")
        mock_update_status.assert_not_called()

    def test_huawei_queue_direction_block_normaliza_aliases_reais_de_risco(self):
        item = {
            "setor_previsto": "DIST - VERDE",
            "metadata": {
                "origem": "huawei_sync",
                "huawei_is_call_in": False,
                "huawei_caller_no": "0011999999999",
                "huawei_callee_no": "61197",
                "huawei_work_no": "61197",
            },
        }

        from core.automation_guardrails import AutomationGatekeeper
        # Apos o fix da Fase 1, o campo 'huawei_is_call_in' (explicito) tem prioridade.
        # Sendo 'False' (outbound), a chamada de risco e permitida na automacao.
        self.assertIsNone(
            AutomationGatekeeper.check_eligibility(item)
        )

    def test_huawei_queue_direction_block_bloqueia_celula_fora_da_telefonia(self):
        item = {
            "setor_previsto": "DIST E CELULA - VERDE",
            "metadata": {
                "origem": "huawei_sync",
                "huawei_is_call_in": False,
            },
        }

        from core.automation_guardrails import AutomationGatekeeper
        self.assertEqual(
            AutomationGatekeeper.check_eligibility(item),
            ("setor_nao_telefonia", "celula_atendimento"),
        )

    def test_huawei_queue_direction_block_prefere_setor_real_do_operador(self):
        item = {
            "setor_previsto": "cadastro",
            "metadata": {
                "origem": "huawei_sync",
                "operator_sector_real": "DIST - VERDE",
                "huawei_is_call_in": True,
            },
        }

        from core.automation_guardrails import AutomationGatekeeper

        self.assertEqual(
            AutomationGatekeeper.check_eligibility(item),
            ("receptiva_setor_risco", "distribuicao"),
        )

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-1")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=99)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_uses_public_metadata_contract(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(SimpleNamespace(score=8.5, maxPossibleScore=10.0, audio_quality={"transcription_provider": {"selected_strategy": "fast"}}), "audit-hash-1", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])

        item = {
            "input_hash": "queue-hash-1",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "hash-1.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(sys.modules, {"services": fake_services}):
            asyncio.run(automation._audit_single_item(item))

        mock_compute_input_hash.assert_called_once()
        mock_get_audit_by_hash.assert_called_once_with(ANY, "audit-hash-1")
        mock_load_audio.assert_called_once_with("hash-1.wav", input_hash="queue-hash-1")
        mock_get_mime_type.assert_called_once_with("call.wav")
        fake_services.process_audit_with_ai.assert_awaited_once()
        mock_persist_audit_artifacts.assert_called_once_with(
            fake_services.process_audit_with_ai.return_value[0],
            from_cache=False,
            input_hash="audit-hash-1",
            alert_id="4.4.1",
            alert_label="Alerta de teste",
            operator_id=None,
            sector_id="logistica",
            audio_bytes=b"audio-bytes",
            audio_mime_type="audio/wav",
            original_filename="call.wav",
            status="awaiting_pair",
            criado_por="automacao",
        )
        mock_update_queue_status.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], "audited")
        self.assertEqual(kwargs["metadata_merge"]["audit_id"], 99)
        self.assertEqual(kwargs["metadata_merge"]["audit_input_hash"], "audit-hash-1")

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-repaired")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=1001)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_repairs_unknown_context_before_blocking(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(SimpleNamespace(score=8.5, maxPossibleScore=10.0, audio_quality={"transcription_provider": {"selected_strategy": "fast"}}), "audit-hash-repaired", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Entrega", criteria=[SimpleNamespace(id="c1", label="c1")])
        item = {
            "input_hash": "queue-hash-repair",
            "nome_arquivo": "call.wav",
            "setor_previsto": "",
            "alerta_previsto": "desconhecido",
            "operador_previsto": "Operador X",
            "metadata": {
                "classified_audio_path": "repair.wav",
                "operator_sector_id": "logistica",
                "classification_status": "done",
            },
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch(
            "core.classification.align_classification_with_catalog",
            return_value={"sector_id": "logistica", "alert_id": "ENTREGA", "alert_label": "Entrega"},
        ), patch.dict(sys.modules, {"services": fake_services}):
            asyncio.run(automation._audit_single_item(item))

        mock_build_alert.assert_called_once_with("logistica", "ENTREGA")
        fake_services.process_audit_with_ai.assert_awaited_once()
        mock_persist_audit_artifacts.assert_called_once()
        mock_update_queue_status.assert_called_once()
        merge = mock_update_queue_status.call_args.kwargs["metadata_merge"]
        self.assertEqual(merge["audit_input_hash"], "audit-hash-repaired")
        self.assertTrue(merge["audit_pipeline"]["context_repair"]["applied"])
        self.assertEqual(merge["audit_pipeline"]["origin"], "automation")

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "load_classified_audio")
    @patch("repositories.audits.get_operator_audit_count_for_month", return_value=2)
    @patch.object(automation, "_get_monthly_audit_quota", return_value=2)
    def test_audit_single_item_blocks_metadata_operator_before_cache_lookup(
        self,
        mock_quota,
        mock_count,
        mock_load_audio,
        mock_update_queue_status,
    ):
        item = {
            "input_hash": "queue-hash-metadata-operator",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "",
            "metadata": {
                "operator_name": "Operador Metadata",
                "operator_id": "MAT-9",
                "classified_audio_path": "metadata.wav",
                "audio_date": "2026-05-10",
            },
        }

        # A cota mensal so barra a auditoria no modo legado (rollback). Por padrao
        # (AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP ON) a IA audita e a cota fica no envio ao supervisor.
        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador Metadata", "preferredId": "", "matricula": "MAT-9"},
        ), patch("repositories.audits.get_audit_by_hash") as mock_get_audit_by_hash, patch.dict(
            os.environ, {"AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP": "false"}, clear=False
        ):
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "monthly_capped")
        mock_quota.assert_called_once()
        mock_count.assert_called_once()
        mock_load_audio.assert_not_called()
        mock_get_audit_by_hash.assert_not_called()
        mock_update_queue_status.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], REVIEW_QUEUE_STATUS_MONTHLY_CAPPED)
        self.assertEqual(kwargs["motivos_revisao_append"], ["cota_mensal_atingida"])
        self.assertEqual(kwargs["metadata_merge"]["monthly_cap_period"], "2026-05")
        self.assertEqual(kwargs["metadata_merge"]["monthly_cap_operator"], "Operador Metadata")
        self.assertEqual(kwargs["metadata_merge"]["monthly_cap_operator_id"], "MAT-9")

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="expected-hash")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=99)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_accepts_hash_mismatch_with_warning(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(SimpleNamespace(score=8.5, maxPossibleScore=10.0, audio_quality={"transcription_provider": {"selected_strategy": "fast"}}), "returned-hash", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])
        item = {
            "input_hash": "queue-hash-1",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "hash-1.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.object(
            automation,
            "_get_monthly_audit_quota",
            return_value=2,
        ), patch(
            "repositories.audits.get_operator_audit_count_for_month",
            return_value=0,
        ), patch.dict(sys.modules, {"services": fake_services}):
            res = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(res["status"], "audited")
        # Ensure it passed the returned-hash to persist
        self.assertEqual(mock_persist_audit_artifacts.call_args.kwargs["input_hash"], "returned-hash")

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-review")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=99)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_routes_low_confidence_transcription_to_manual_triage(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        result = SimpleNamespace(
            score=0.0,
            maxPossibleScore=10.0,
            audio_quality={
                "transcription_quality": {
                    "audit_readiness": "review_required",
                    "reasons": ["fallback_de_transcricao_sem_consenso"],
                },
                "transcription_provider": {
                    "selected_strategy": "fast",
                    "selected_reason": "accepted",
                },
            },
        )
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(result, "audit-hash-review", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])
        item = {
            "input_hash": "queue-hash-review",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "review.wav"},
        }

        # Caminho de rollback (AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK=false): transcricao de
        # baixa confianca ainda estaciona em triagem manual em vez de auditar automaticamente.
        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(sys.modules, {"services": fake_services}), patch.dict(
            os.environ, {"AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK": "false"}, clear=False
        ):
            response = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(response["status"], "blocked_transcription_quality")
        fake_services.process_audit_with_ai.assert_awaited_once()
        mock_persist_audit_artifacts.assert_not_called()
        mock_update_queue_status.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)
        self.assertIn("transcricao_requer_revisao", kwargs["motivos_revisao_append"])
        self.assertIn("transcricao_fallback_de_transcricao_sem_consenso", kwargs["motivos_revisao_append"])
        self.assertNotIn("transcricao_automatica_sem_hybrid_dual", kwargs["motivos_revisao_append"])
        self.assertEqual(kwargs["metadata_merge"]["audit_input_hash"], "audit-hash-review")
        self.assertEqual(
            kwargs["metadata_merge"]["audio_quality_review"]["transcription_quality"]["audit_readiness"],
            "review_required",
        )

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-fallback")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=99)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_accepts_fast_ready_transcription_in_automation(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        result = SimpleNamespace(
            score=9.0,
            maxPossibleScore=10.0,
            audio_quality={
                "transcription_quality": {
                    "audit_readiness": "ready",
                    "reasons": [],
                },
                "transcription_provider": {
                    "selected_strategy": "fast",
                    "selected_reason": "accepted",
                },
            },
        )
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(result, "audit-hash-fallback", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])
        item = {
            "input_hash": "queue-hash-fallback",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "fallback.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(sys.modules, {"services": fake_services}):
            response = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(response["status"], "audited")
        mock_persist_audit_artifacts.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], "audited")
        self.assertEqual(kwargs["metadata_merge"]["audit_input_hash"], "audit-hash-fallback")

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-strict")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=99)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_routes_premium_transcription_failure_to_retry(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            side_effect=RuntimeError("hybrid_dual: Whisper falhou em modo estrito")
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])
        item = {
            "input_hash": "queue-hash-strict",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "strict.wav"},
        }

        # AUTOMATION_TRANSIENT_RETRY_LIMIT default virou 1 na v1.3.111 (falha
        # de transcricao -> descarte permanente sem re-tentativa). Este teste
        # valida o ROTEAMENTO de retry quando o limite permite (>1); o caminho
        # default sem retry e coberto por
        # test_automation_audit_on_transcription_risk.py.
        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(sys.modules, {"services": fake_services}), patch.dict(
            os.environ, {"AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"}, clear=False
        ):
            response = asyncio.run(automation._audit_single_item(item))

        # Contrato com retry habilitado: falha de transcricao e transitoria ->
        # RETRY (auto_resolved) ate o limite, depois descarta.
        self.assertEqual(response["status"], "retry_transcription_failed")
        mock_persist_audit_artifacts.assert_not_called()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], REVIEW_QUEUE_STATUS_AUTO_RESOLVED)
        self.assertEqual(kwargs["motivos_revisao_append"], ["transcricao_premium_falhou"])
        self.assertIn("hybrid_dual", kwargs["metadata_merge"]["transcription_error"])

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-1")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=None)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"audio-bytes")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_requires_persisted_audit_id_before_marking_queue_audited(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        fake_services = types.ModuleType("services")
        fake_services.process_audit_with_ai = AsyncMock(
            return_value=(SimpleNamespace(score=8.5, maxPossibleScore=10.0, audio_quality={"transcription_provider": {"selected_strategy": "fast"}}), "audit-hash-1", False)
        )
        mock_build_alert.return_value = SimpleNamespace(label="Alerta de teste", criteria=[SimpleNamespace(id="c1", label="c1")])

        item = {
            "input_hash": "queue-hash-1",
            "nome_arquivo": "call.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador X",
            "metadata": {"classified_audio_path": "hash-1.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(sys.modules, {"services": fake_services}):
            with self.assertRaises(automation.AuditPersistenceError):
                asyncio.run(automation._audit_single_item(item))

        mock_compute_input_hash.assert_called_once()
        mock_persist_audit_artifacts.assert_called_once()
        mock_update_queue_status.assert_not_called()

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-pdf")
    @patch.object(automation.database, "persist_audit_artifacts", return_value=100)
    @patch("repositories.audits.get_audit_by_hash", return_value=None)
    @patch.object(automation, "get_mime_type", return_value="audio/wav")
    @patch.object(automation, "load_classified_audio", return_value=b"%PDF-demo")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_processes_pdf_source_type(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_mime_type,
        mock_get_audit_by_hash,
        mock_persist_audit_artifacts,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        from core import audit as core_audit

        mock_build_alert.return_value = SimpleNamespace(label="Alerta PDF", criteria=[SimpleNamespace(id="c1", label="c1")])
        result = SimpleNamespace(score=9.0, maxPossibleScore=10.0, source_type="pdf")
        item = {
            "input_hash": "queue-hash-pdf",
            "nome_arquivo": "chat.pdf",
            "setor_previsto": "checklist",
            "alerta_previsto": "CHECKLIST-ATENDIMENTO-HORARIO",
            "operador_previsto": "Operador X",
            "metadata": {"classified_file_path": "hash-pdf.pdf", "source_type": "pdf"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.object(
            core_audit,
            "process_pdf_audit",
            new=AsyncMock(return_value=(result, "audit-hash-pdf", False)),
        ) as process_pdf:
            asyncio.run(automation._audit_single_item(item))

        mock_compute_input_hash.assert_called_once()
        mock_get_audit_by_hash.assert_called_once_with(ANY, "audit-hash-pdf")
        mock_load_audio.assert_called_once_with("hash-pdf.pdf", input_hash="queue-hash-pdf")
        mock_get_mime_type.assert_not_called()
        process_pdf.assert_awaited_once_with(
            b"%PDF-demo",
            "application/pdf",
            mock_build_alert.return_value,
            "Operador X",
            None,
            "checklist",
            pipeline_context=ANY,
        )
        mock_persist_audit_artifacts.assert_called_once_with(
            result,
            from_cache=False,
            input_hash="audit-hash-pdf",
            alert_id="CHECKLIST-ATENDIMENTO-HORARIO",
            alert_label="Alerta PDF",
            operator_id=None,
            sector_id="checklist",
            audio_bytes=None,
            audio_mime_type=None,
            original_filename="chat.pdf",
            status="awaiting_pair",
            criado_por="automacao",
        )
        mock_update_queue_status.assert_called_once()

    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "compute_input_hash", return_value="audit-hash-pdf")
    @patch("repositories.audits.get_audit_media_record_by_hash", return_value={"id": 123})
    @patch("repositories.audits.get_audit_by_hash")
    @patch.object(automation, "load_classified_audio", return_value=b"%PDF-demo")
    @patch.object(automation, "_build_alert_from_classification")
    def test_audit_single_item_reuses_cached_pdf_audit_id(
        self,
        mock_build_alert,
        mock_load_audio,
        mock_get_audit_by_hash,
        mock_get_audit_media_record_by_hash,
        mock_compute_input_hash,
        mock_update_queue_status,
    ):
        mock_build_alert.return_value = SimpleNamespace(label="Alerta PDF", criteria=[SimpleNamespace(id="c1", label="c1")])
        mock_get_audit_by_hash.return_value = SimpleNamespace(score=9.0, maxPossibleScore=10.0, source_type="pdf")
        item = {
            "input_hash": "queue-hash-pdf",
            "nome_arquivo": "chat.pdf",
            "setor_previsto": "checklist",
            "alerta_previsto": "CHECKLIST-ATENDIMENTO-HORARIO",
            "operador_previsto": "Operador X",
            "metadata": {"classified_file_path": "hash-pdf.pdf", "source_type": "pdf"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ):
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["audit_id"], 123)
        mock_load_audio.assert_called_once_with("hash-pdf.pdf", input_hash="queue-hash-pdf")
        mock_compute_input_hash.assert_called_once()
        mock_get_audit_by_hash.assert_called_once_with(ANY, "audit-hash-pdf")
        mock_get_audit_media_record_by_hash.assert_called_once_with(ANY, "audit-hash-pdf")
        mock_update_queue_status.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], "audited")
        self.assertEqual(kwargs["metadata_merge"]["audit_id"], 123)
        self.assertEqual(kwargs["metadata_merge"]["audit_input_hash"], "audit-hash-pdf")

    @patch.object(automation.asyncio, "sleep", new_callable=AsyncMock)
    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation.database, "listar_fila_revisao_classificacao")
    @patch.object(automation, "load_classified_audio", return_value=None)
    def test_audit_all_pending_moves_missing_audio_back_to_pending(
        self,
        mock_load_audio,
        mock_listar,
        mock_update_queue_status,
        mock_sleep,
    ):
        mock_listar.return_value = [
            {
                "input_hash": "queue-hash-missing",
                "nome_arquivo": "missing.wav",
                "setor_previsto": "logistica",
                "alerta_previsto": "4.4.1",
                "operador_previsto": "Operador X",
                "metadata": {"classified_audio_path": "missing.wav"},
            }
        ]

        # Retry habilitado (limite>1) para validar o roteamento de volta a
        # auto_resolved; default v1.3.111 e 1 (descarta na 1a falha).
        with patch("repositories.operators.resolve_auditable_colaborador",
            return_value={"name": "Operador X", "preferredId": "", "matricula": ""},
        ), patch.dict(os.environ, {"AUTOMATION_TRANSIENT_RETRY_LIMIT": "3"}, clear=False):
            result = asyncio.run(automation.audit_all_pending())

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["failed"], 1)
        mock_load_audio.assert_called_once_with("missing.wav", input_hash="queue-hash-missing")
        mock_sleep.assert_awaited_once()
        mock_update_queue_status.assert_called_once()
        _, kwargs = mock_update_queue_status.call_args
        self.assertEqual(kwargs["status"], REVIEW_QUEUE_STATUS_AUTO_RESOLVED)
        self.assertIn("Arquivo classificado nao encontrado", kwargs["erro"])
        self.assertEqual(kwargs["motivos_revisao_append"], ["audio_classificado_ausente"])
        self.assertIn("automation_last_error_at", kwargs["metadata_merge"])


    @patch.object(automation.database, "descartar_item_automacao", return_value={"discarded": True})
    @patch.object(automation.database, "atualizar_status_fila_revisao_classificacao")
    @patch.object(automation, "load_classified_audio")
    def test_audit_single_item_discards_non_auditable_operator(
        self,
        mock_load_audio,
        mock_update_queue_status,
        mock_descartar,
    ):
        # Novo contrato: operador nao auditavel nunca vira auditoria valida -> DESCARTA
        # permanente, nao prende em blocked_operator.
        item = {
            "input_hash": "queue-hash-ghost",
            "nome_arquivo": "ghost.wav",
            "setor_previsto": "logistica",
            "alerta_previsto": "4.4.1",
            "operador_previsto": "Operador Fantasma",
            "metadata": {"classified_audio_path": "ghost.wav"},
        }

        with patch("repositories.operators.resolve_auditable_colaborador", return_value=None):
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "discarded_operator")
        mock_load_audio.assert_not_called()
        mock_descartar.assert_called_once()
        mock_update_queue_status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
