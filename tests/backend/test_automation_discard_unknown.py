"""Auto-descarte de itens 'desconhecido' no modo automacao.

Quando a triagem nao casa com nenhum alerta confiavel (alert_id == 'desconhecido')
no ciclo de automacao, o item e DELETADO da fila e contabilizado no resumo do ciclo,
em vez de ficar em needs_manual_triage. Gateado por AUTOMATION_DISCARD_UNKNOWN_ALERTS
(default ON).
"""
import asyncio
import contextlib
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import automation
from core import automation_engine


class TestDiscardFlag(unittest.TestCase):
    def test_flag_default_on_quando_env_ausente(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUTOMATION_DISCARD_UNKNOWN_ALERTS", None)
            self.assertTrue(automation._discard_unknown_alerts_enabled())

    def test_flag_off_quando_env_false(self):
        with patch.dict(os.environ, {"AUTOMATION_DISCARD_UNKNOWN_ALERTS": "false"}, clear=False):
            self.assertFalse(automation._discard_unknown_alerts_enabled())

    def test_flag_on_quando_env_true(self):
        with patch.dict(os.environ, {"AUTOMATION_DISCARD_UNKNOWN_ALERTS": "true"}, clear=False):
            self.assertTrue(automation._discard_unknown_alerts_enabled())


import json
from unittest.mock import MagicMock

from repositories import classification_review


class _DiscardCursor:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def execute(self, sql, params=()):
        self.queries.append((" ".join(sql.split()), tuple(params) if params else ()))

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row else []


class _DiscardConn:
    def __init__(self, cursor, *, commit_error=None):
        self._cursor = cursor
        self._commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1
        if self._commit_error:
            raise self._commit_error

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class TestDescartarRepo(unittest.TestCase):
    def test_descartar_purga_commita_e_nao_depende_de_tabela_de_log(self):
        row = {
            "input_hash": "h1",
            "metadata_json": json.dumps(
                {"huawei_call_id": "C-9", "classified_audio_path": "a.wav"}
            ),
        }
        cur = _DiscardCursor(row)
        conn = _DiscardConn(cur)
        with patch("storage.audit_storage.resolve_stored_audit_audio_path") as mock_resolve:
            fake_file = MagicMock()
            fake_file.unlink.side_effect = lambda **_kwargs: self.assertEqual(conn.commits, 1)
            mock_resolve.return_value = fake_file
            out = classification_review.descartar_item_automacao(
                lambda: conn,
                "h1",
                motivo="triagem_sem_alerta_confiavel",
                log_fields={
                    "nome_arquivo": "call.wav",
                    "setor_previsto": "cadastro",
                    "operador_previsto": "Op X",
                    "confidence": 0.3,
                },
            )
        sqls = " | ".join(q for q, _ in cur.queries)
        self.assertNotIn("automation_discards", sqls)
        self.assertIn("DELETE FROM fila_revisao_classificacao", sqls)
        # Novo contrato: descarte recuperavel NAO deleta o sync_log; faz UPSERT (tombstone)
        # preservando a linha para contar tentativas (anti-loop por call_id).
        self.assertNotIn("DELETE FROM huawei_sync_logs", sqls)
        self.assertIn("INSERT INTO huawei_sync_logs", sqls)
        self.assertIn("discarded_recoverable", sqls)
        fake_file.unlink.assert_called_once()
        self.assertEqual(conn.commits, 1)
        self.assertTrue(out["discarded"])

    def test_descartar_nao_apaga_midia_quando_commit_falha(self):
        row = {
            "input_hash": "h1",
            "metadata_json": json.dumps(
                {"huawei_call_id": "C-9", "classified_audio_path": "a.wav"}
            ),
        }
        cur = _DiscardCursor(row)
        conn = _DiscardConn(cur, commit_error=RuntimeError("commit failed"))
        with patch("storage.audit_storage.resolve_stored_audit_audio_path") as mock_resolve:
            with self.assertRaisesRegex(RuntimeError, "commit failed"):
                classification_review.descartar_item_automacao(
                    lambda: conn,
                    "h1",
                    motivo="triagem_sem_alerta_confiavel",
                    log_fields={"nome_arquivo": "call.wav"},
                )

        sqls = " | ".join(q for q, _ in cur.queries)
        self.assertNotIn("automation_discards", sqls)
        self.assertIn("DELETE FROM fila_revisao_classificacao", sqls)
        self.assertEqual(conn.rollbacks, 1)
        mock_resolve.assert_not_called()

    def test_descartar_item_inexistente_e_noop(self):
        cur = _DiscardCursor(None)
        conn = _DiscardConn(cur)
        out = classification_review.descartar_item_automacao(
            lambda: conn, "missing", motivo="x"
        )
        self.assertFalse(out["discarded"])
        self.assertEqual(conn.commits, 0)

    def test_limpar_antiga_ainda_deleta_via_helper(self):
        # regressao: a extracao de _purgar_item_fila nao pode quebrar o cleanup de 24h
        row = {
            "input_hash": "old1",
            "metadata_json": json.dumps(
                {"huawei_call_id": "C-1", "classified_audio_path": "o.wav"}
            ),
        }
        cur = _DiscardCursor(row)
        conn = _DiscardConn(cur)
        fake_file = MagicMock()
        fake_file.unlink.side_effect = lambda **_kwargs: self.assertEqual(conn.commits, 1)
        with patch("storage.audit_storage.resolve_stored_audit_audio_path", return_value=fake_file):
            out = classification_review.limpar_fila_revisao_classificacao_antiga(lambda: conn, 24)
        sqls = " | ".join(q for q, _ in cur.queries)
        self.assertIn("DELETE FROM fila_revisao_classificacao", sqls)
        self.assertIn("DELETE FROM huawei_sync_logs", sqls)
        self.assertEqual(out["deleted"], 1)
        fake_file.unlink.assert_called_once()


class TestDescartarFacade(unittest.TestCase):
    def test_facade_repassa_get_connection_e_args(self):
        from db import database
        with patch(
            "repositories.classification_review.descartar_item_automacao",
            return_value={"discarded": True},
        ) as mock_repo:
            out = database.descartar_item_automacao(
                "h1", motivo="triagem_sem_alerta_confiavel", log_fields={"nome_arquivo": "x.wav"}
            )
        self.assertTrue(out["discarded"])
        mock_repo.assert_called_once()
        # 1o arg posicional = factory get_connection; 2o = input_hash
        self.assertEqual(mock_repo.call_args.args[1], "h1")
        self.assertEqual(mock_repo.call_args.kwargs["motivo"], "triagem_sem_alerta_confiavel")


def _desconhecido_item():
    return {
        "input_hash": "queue-desconhecido-1",
        "nome_arquivo": "call.wav",
        "setor_previsto": "cadastro",
        "alerta_previsto": "desconhecido",
        "operador_previsto": "Operador X",
        "confianca": 0.3,
        "metadata": {
            "classified_audio_path": "c.wav",
            "huawei_call_id": "C-7",
            "classification_status": "done",
        },
    }


def _fake_ctx(alert_id="desconhecido", sector_id="cadastro"):
    return SimpleNamespace(
        filename="call.wav",
        sector_id=sector_id,
        alert_id=alert_id,
        alert_label="",
        operator_name="Operador X",
        operator_id="MAT-1",
        source_type="audio",
        media_path="c.wav",
        to_audit_metadata=lambda: {"origin": "automation"},
    )


def _reach_validating_context(ctx):
    """Patches que levam o _audit_single_item ate o passo validating_context (834),
    controlando o pipeline_context pos-repair."""
    return [
        patch.object(automation, "repair_queue_audit_context", return_value=ctx),
        patch(
            "core.automation_operator.OperatorGatekeeper.resolve_operator",
            return_value=SimpleNamespace(
                is_valid=True,
                operator_name="Operador X",
                operator_id="MAT-1",
                resolved_operator_dict={},
                block_message=None,
                block_reason=None,
                motivos_revisao_append=[],
                metadata_merge={},
            ),
        ),
        patch("core.automation_operator.QuotaGatekeeper.check_quota", return_value=None),
        patch.object(automation, "_get_monthly_audit_quota", return_value=2),
        patch.object(automation, "apply_resolved_operator"),
        patch.object(automation, "load_classified_audio", return_value=b"audio-bytes"),
    ]


class TestAuditSingleItemHook(unittest.TestCase):
    def test_desconhecido_descartado_quando_flag_on(self):
        item = _desconhecido_item()
        with contextlib.ExitStack() as stack:
            for p in _reach_validating_context(_fake_ctx(alert_id="desconhecido")):
                stack.enter_context(p)
            mock_descartar = stack.enter_context(
                patch.object(automation.database, "descartar_item_automacao", return_value={"discarded": True})
            )
            mock_mark = stack.enter_context(patch.object(automation, "_mark_item_status"))
            stack.enter_context(patch.dict(os.environ, {"AUTOMATION_DISCARD_UNKNOWN_ALERTS": "true"}, clear=False))
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "discarded_unknown_alert")
        mock_descartar.assert_called_once()
        self.assertEqual(mock_descartar.call_args.args[0], "queue-desconhecido-1")
        self.assertTrue(mock_descartar.call_args.kwargs["tombstone"])  # desconhecido = lixo = permanente
        mock_mark.assert_not_called()

    def test_desconhecido_vai_para_triagem_quando_flag_off(self):
        item = _desconhecido_item()
        with contextlib.ExitStack() as stack:
            for p in _reach_validating_context(_fake_ctx(alert_id="desconhecido")):
                stack.enter_context(p)
            mock_descartar = stack.enter_context(
                patch.object(automation.database, "descartar_item_automacao")
            )
            mock_mark = stack.enter_context(patch.object(automation, "_mark_item_status"))
            stack.enter_context(patch.dict(os.environ, {"AUTOMATION_DISCARD_UNKNOWN_ALERTS": "false"}, clear=False))
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "blocked_invalid_context")
        mock_descartar.assert_not_called()
        mock_mark.assert_called_once()
        self.assertEqual(mock_mark.call_args.args[1], automation.REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE)

    def test_setor_ausente_com_alerta_valido_e_descartado(self):
        # Novo contrato: setor ausente nunca vira auditoria valida -> DESCARTA (recuperavel),
        # nao prende em triagem. Gateado por AUTOMATION_DISCARD_MISSING_SECTOR (default ON).
        item = _desconhecido_item()
        with contextlib.ExitStack() as stack:
            for p in _reach_validating_context(_fake_ctx(alert_id="ENTREGA", sector_id="")):
                stack.enter_context(p)
            mock_descartar = stack.enter_context(
                patch.object(automation.database, "descartar_item_automacao", return_value={"discarded": True})
            )
            mock_mark = stack.enter_context(patch.object(automation, "_mark_item_status"))
            mock_build = stack.enter_context(patch.object(automation, "_build_alert_from_classification"))
            stack.enter_context(patch.dict(os.environ, {"AUTOMATION_DISCARD_MISSING_SECTOR": "true"}, clear=False))
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "discarded_invalid_context")
        mock_descartar.assert_called_once()
        self.assertTrue(mock_descartar.call_args.kwargs["tombstone"])  # setor ausente = permanente
        mock_mark.assert_not_called()
        mock_build.assert_not_called()

    def test_setor_ausente_vai_para_triagem_quando_flag_off(self):
        # Rollback: AUTOMATION_DISCARD_MISSING_SECTOR=false -> comportamento legado (triagem).
        item = _desconhecido_item()
        with contextlib.ExitStack() as stack:
            for p in _reach_validating_context(_fake_ctx(alert_id="ENTREGA", sector_id="")):
                stack.enter_context(p)
            mock_descartar = stack.enter_context(
                patch.object(automation.database, "descartar_item_automacao")
            )
            mock_mark = stack.enter_context(patch.object(automation, "_mark_item_status"))
            mock_build = stack.enter_context(patch.object(automation, "_build_alert_from_classification"))
            stack.enter_context(patch.dict(os.environ, {"AUTOMATION_DISCARD_MISSING_SECTOR": "false"}, clear=False))
            result = asyncio.run(automation._audit_single_item(item))

        self.assertEqual(result["status"], "blocked_invalid_context")
        mock_descartar.assert_not_called()
        mock_mark.assert_called_once()
        mock_build.assert_not_called()


class TestAuditAllPendingDiscardSummary(unittest.TestCase):
    def test_descarte_em_lote_nao_incrementa_failed_ou_blocked(self):
        item = _desconhecido_item()
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    automation.database,
                    "listar_fila_revisao_classificacao",
                    return_value=[item],
                )
            )
            stack.enter_context(patch.object(automation.database, "update_config", return_value=True))
            stack.enter_context(patch.object(automation.database, "get_config_value", return_value="false"))
            stack.enter_context(patch.object(automation.AutomationGatekeeper, "check_eligibility", return_value=None))
            audit_single = stack.enter_context(
                patch.object(
                    automation,
                    "_audit_single_item_with_timeout",
                    new_callable=AsyncMock,
                    return_value={"status": "discarded_unknown_alert"},
                )
            )
            stack.enter_context(patch.object(automation.asyncio, "sleep", new_callable=AsyncMock))
            stack.enter_context(patch("core.saved_files_sync_queue.flush", return_value=True))
            stack.enter_context(patch("core.saved_files_sync_queue.queue_size", return_value=0))

            result = asyncio.run(automation.audit_all_pending(max_items=1, time_budget_seconds=60))

        audit_single.assert_awaited_once()
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["discarded"], 1)
        self.assertEqual(result["descartados"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["blocked"], 0)

    def test_ciclo_expõe_descartados_sem_erro(self):
        class Lock:
            def acquire(self):
                return True

            def refresh(self):
                return True

            def release(self):
                pass

        audit_result = {
            "completed": 0,
            "discarded": 1,
            "descartados": 1,
            "failed": 0,
            "blocked": 0,
        }
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(automation_engine, "is_automation_enabled", return_value=True))
            stack.enter_context(patch.object(automation_engine, "_reconcile_stale_running_cycles"))
            stack.enter_context(patch.object(automation_engine, "_AutomationCycleLock", return_value=Lock()))
            stack.enter_context(patch.object(automation_engine, "_create_cycle_run", return_value=101))
            stack.enter_context(patch.object(automation_engine, "_persist_cycle_update"))
            stack.enter_context(patch.object(automation_engine.database, "update_config", return_value=True))
            stack.enter_context(patch.object(automation_engine.database, "get_config_value", return_value="false"))
            stack.enter_context(patch("db.database.limpar_fila_revisao_classificacao_antiga", return_value={"deleted": 0}))
            stack.enter_context(
                patch.object(
                    automation_engine,
                    "executar_d_minus_1_pipeline",
                    new_callable=AsyncMock,
                    return_value={"status": "ok", "executados": []},
                )
            )
            stack.enter_context(
                patch.object(
                    automation_engine,
                    "_audit_all_pending_with_progress",
                    new_callable=AsyncMock,
                    return_value=audit_result,
                )
            )

            result = asyncio.run(automation_engine.run_automation_cycle(source="cloud_scheduler"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["auditadas"], 0)
        self.assertEqual(result["descartados"], 1)
        self.assertIsNone(automation_engine._current_status.get("last_error"))


if __name__ == "__main__":
    unittest.main()
