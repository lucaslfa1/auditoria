"""Testes do guardrail de orcamento (core/cost_guard.py).

Cobrem: contadores persistidos (api_usage_daily), tetos diarios via env,
kill-switch (env e tabela configuracoes), fail-open quando o banco falha e
o encerramento gracioso do lote em audit_all_pending.

Exigem DATABASE_URL apontando para um banco de TESTE ja migrado
(init_db aplicou m20260611_001_api_usage_daily). O guard do conftest impede
execucao contra producao.
"""
import asyncio
import os
import unittest
from unittest import mock

from core import cost_guard


def _pg_available() -> bool:
    try:
        from db.database import get_connection

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM api_usage_daily LIMIT 1")
        return True
    except Exception:
        return False


_PG_OK = _pg_available()


def _limpar_contadores_do_dia() -> None:
    from db.database import get_connection

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM api_usage_daily WHERE data = CURRENT_DATE")
        cur.execute(
            "UPDATE configuracoes SET valor = 'false' WHERE chave = 'cost_kill_switch'"
        )
        conn.commit()


@unittest.skipUnless(_PG_OK, "exige banco de teste migrado (api_usage_daily)")
class TestCostGuardContadores(unittest.TestCase):
    def setUp(self):
        _limpar_contadores_do_dia()
        cost_guard.invalidate_cache()
        self._env = mock.patch.dict(
            os.environ,
            {
                "COST_KILL_SWITCH": "",
                "COST_MAX_LLM_CALLS_PER_DAY": "",
                "COST_MAX_AUDITS_PER_DAY": "",
            },
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        _limpar_contadores_do_dia()
        cost_guard.invalidate_cache()

    def test_record_call_incrementa_e_acumula(self):
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "classificacao")
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "classificacao")
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_SPEECH, "transcricao_fast")
        cost_guard.invalidate_cache()

        usage = cost_guard.get_today_usage()
        self.assertEqual(usage["chamadas_llm"], 2)
        self.assertEqual(usage["chamadas_speech"], 1)
        self.assertEqual(usage["por_categoria"]["azure_openai/classificacao"], 2)

    def test_record_audit_completed_conta_auditoria(self):
        cost_guard.record_audit_completed()
        cost_guard.invalidate_cache()
        usage = cost_guard.get_today_usage()
        self.assertEqual(usage["auditorias"], 1)

    def test_cache_atualiza_sem_esperar_ttl(self):
        # O cache em memoria deve refletir incremento local imediatamente.
        cost_guard.get_today_usage()  # popula o cache do dia
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "avaliacao")
        usage = cost_guard.get_today_usage()
        self.assertGreaterEqual(usage["chamadas_llm"], 1)


@unittest.skipUnless(_PG_OK, "exige banco de teste migrado (api_usage_daily)")
class TestCostGuardTetos(unittest.TestCase):
    def setUp(self):
        _limpar_contadores_do_dia()
        cost_guard.invalidate_cache()

    def tearDown(self):
        _limpar_contadores_do_dia()
        cost_guard.invalidate_cache()

    def test_teto_llm_bloqueia(self):
        with mock.patch.dict(
            os.environ,
            {"COST_KILL_SWITCH": "", "COST_MAX_LLM_CALLS_PER_DAY": "2", "COST_MAX_AUDITS_PER_DAY": "0"},
        ):
            cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "triagem_llm")
            self.assertIsNone(cost_guard.budget_exceeded())
            cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "triagem_llm")
            cost_guard.invalidate_cache()
            motivo = cost_guard.budget_exceeded()
            self.assertIsNotNone(motivo)
            self.assertIn("teto_chamadas_llm", motivo)

    def test_teto_auditorias_bloqueia(self):
        with mock.patch.dict(
            os.environ,
            {"COST_KILL_SWITCH": "", "COST_MAX_LLM_CALLS_PER_DAY": "0", "COST_MAX_AUDITS_PER_DAY": "1"},
        ):
            cost_guard.record_audit_completed()
            cost_guard.invalidate_cache()
            motivo = cost_guard.budget_exceeded()
            self.assertIsNotNone(motivo)
            self.assertIn("teto_auditorias", motivo)

    def test_teto_zero_desativa(self):
        with mock.patch.dict(
            os.environ,
            {"COST_KILL_SWITCH": "", "COST_MAX_LLM_CALLS_PER_DAY": "0", "COST_MAX_AUDITS_PER_DAY": "0"},
        ):
            for _ in range(5):
                cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "avaliacao")
            cost_guard.invalidate_cache()
            self.assertIsNone(cost_guard.budget_exceeded())

    def test_speech_nao_conta_no_teto_llm(self):
        with mock.patch.dict(
            os.environ,
            {"COST_KILL_SWITCH": "", "COST_MAX_LLM_CALLS_PER_DAY": "1", "COST_MAX_AUDITS_PER_DAY": "0"},
        ):
            cost_guard.record_call(cost_guard.PROVIDER_AZURE_SPEECH, "transcricao_fast")
            cost_guard.record_call(cost_guard.PROVIDER_AZURE_SPEECH, "transcricao_fast")
            cost_guard.invalidate_cache()
            self.assertIsNone(cost_guard.budget_exceeded())


class TestCostGuardKillSwitch(unittest.TestCase):
    def test_kill_switch_por_env(self):
        with mock.patch.dict(os.environ, {"COST_KILL_SWITCH": "1"}):
            self.assertEqual(cost_guard.budget_exceeded(), "kill_switch_ativo")

    @unittest.skipUnless(_PG_OK, "exige banco de teste migrado")
    def test_kill_switch_por_configuracao_db(self):
        from db.database import get_connection

        with mock.patch.dict(os.environ, {"COST_KILL_SWITCH": ""}):
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO configuracoes (chave, valor, descricao)
                    VALUES ('cost_kill_switch', 'true', 'Kill-switch de custo (teste)')
                    ON CONFLICT (chave) DO UPDATE SET valor = 'true'
                    """
                )
                conn.commit()
            try:
                self.assertEqual(cost_guard.budget_exceeded(), "kill_switch_ativo")
            finally:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE configuracoes SET valor = 'false' WHERE chave = 'cost_kill_switch'"
                    )
                    conn.commit()


class TestCostGuardFailOpen(unittest.TestCase):
    """Banco indisponivel NAO pode travar o pipeline (fail-open)."""

    def test_record_call_nao_propaga_erro_de_banco(self):
        with mock.patch("db.database.get_connection", side_effect=RuntimeError("db down")):
            cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "avaliacao")  # nao lanca

    def test_budget_exceeded_fail_open(self):
        cost_guard.invalidate_cache()
        with mock.patch.dict(
            os.environ,
            {"COST_KILL_SWITCH": "", "COST_MAX_LLM_CALLS_PER_DAY": "1", "COST_MAX_AUDITS_PER_DAY": "1"},
        ):
            with mock.patch("db.database.get_connection", side_effect=RuntimeError("db down")):
                self.assertIsNone(cost_guard.budget_exceeded())


@unittest.skipUnless(_PG_OK, "exige banco de teste migrado")
class TestAutomationBudgetGate(unittest.TestCase):
    """audit_all_pending encerra o lote graciosamente quando o teto e atingido."""

    def test_lote_encerra_sem_processar_itens(self):
        from core import automation

        fake_item = {"input_hash": "hash_teste_budget", "nome_arquivo": "teste.wav"}
        with mock.patch.object(automation.cost_guard, "budget_exceeded", return_value="teto_chamadas_llm_dia_atingido (5/5)"), \
             mock.patch.object(automation.database, "listar_fila_revisao_classificacao", return_value=[fake_item]), \
             mock.patch.object(automation, "_audit_single_item_with_timeout") as audit_mock:
            result = asyncio.run(automation.audit_all_pending(reset_control_flags=False, max_items=1))

        audit_mock.assert_not_called()
        self.assertEqual(result.get("completed"), 0)
        self.assertIn("teto_chamadas_llm", result.get("budget_blocked_motivo") or "")


if __name__ == "__main__":
    unittest.main()
