"""Classificacao do backlog (scripts/reprocess_automation_backlog.py).

Regra: a checagem de ORIGEM vem antes de tudo — triagem manual humana NUNCA e tocada.
Lixo de automacao (alerta inexistente) -> descarte PERMANENTE; transitorio -> reativa.
"""
import importlib.util
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_SCRIPT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "reprocess_automation_backlog.py")
)
_spec = importlib.util.spec_from_file_location("reprocess_backlog", _SCRIPT)
backlog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backlog)


def _huawei(**kw):
    """Item de origem automacao (tem huawei_call_id no metadata)."""
    item = {"metadata": {"huawei_call_id": "C-1"}, "motivos_json": "[]"}
    item.update(kw)
    return item


class TestClassify(unittest.TestCase):
    def test_alerta_desconhecido_de_automacao_descarta_permanente(self):
        item = _huawei(status="pending", alerta_previsto="desconhecido")
        self.assertEqual(backlog._classify(item)[0], "discard_permanent")

    def test_alerta_vazio_de_automacao_descarta_permanente(self):
        item = _huawei(status="needs_manual_triage", alerta_previsto="")
        self.assertEqual(backlog._classify(item)[0], "discard_permanent")

    def test_desconhecido_sem_sinal_de_automacao_e_preservado(self):
        # triagem manual humana com alerta ainda desconhecido -> NAO descarta
        item = {"status": "needs_manual_triage", "alerta_previsto": "desconhecido", "motivos_json": "[]", "metadata": {}}
        self.assertEqual(backlog._classify(item)[0], "noop")

    def test_transcricao_de_automacao_reativa(self):
        item = {
            "status": "needs_manual_triage",
            "alerta_previsto": "LOGISTICA-PARADA",
            "motivos_json": '["aguardando_triagem", "transcricao_score_de_diarizacao_baixo"]',
        }
        self.assertEqual(backlog._classify(item)[0], "reactivate")

    def test_blocked_operator_de_automacao_reativa(self):
        item = _huawei(status="blocked_operator", alerta_previsto="LOGISTICA-PARADA")
        self.assertEqual(backlog._classify(item)[0], "reactivate")

    def test_triagem_manual_humana_preservada(self):
        item = {
            "status": "needs_manual_triage",
            "alerta_previsto": "LOGISTICA-PARADA",
            "motivos_json": '["correcao_manual_pendente"]',
            "metadata": {},
        }
        self.assertEqual(backlog._classify(item)[0], "noop")

    def test_timeout_de_automacao_reseta(self):
        item = _huawei(
            status="pending",
            alerta_previsto="CADASTRO-ANTECEDENTES",
            erro="Timeout ao auditar 'x.wav' apos 219s. O item foi abortado.",
        )
        self.assertEqual(backlog._classify(item)[0], "reset_timeout")

    def test_pending_normal_de_automacao_noop(self):
        item = _huawei(status="pending", alerta_previsto="CADASTRO-ANTECEDENTES", erro=None)
        self.assertEqual(backlog._classify(item)[0], "noop")


class TestIsAutomationItem(unittest.TestCase):
    def test_via_huawei_call_id(self):
        self.assertTrue(backlog._is_automation_item({"metadata": {"huawei_call_id": "C-9"}}, []))

    def test_via_automation_last_error(self):
        self.assertTrue(backlog._is_automation_item({"metadata": {"automation_last_error_at": "2026-05-31T00:00:00Z"}}, []))

    def test_via_origem_huawei_sync(self):
        self.assertTrue(backlog._is_automation_item({"metadata": {"origem": "huawei_sync"}}, []))

    def test_via_motivos_de_automacao(self):
        self.assertTrue(backlog._is_automation_item({"metadata": {}}, ["transcricao_requer_revisao"]))

    def test_sem_sinais_e_manual(self):
        self.assertFalse(backlog._is_automation_item({"metadata": {}}, ["correcao_manual"]))


if __name__ == "__main__":
    unittest.main()
