"""Integração da trava de pesos contra um PostgreSQL real (branch Neon de teste).

Prova que `create_criterion`/`update_criterion` bloqueiam de fato quando a soma
dos pesos do alerta passaria de 10, executando o SQL real do `_alert_weight_sum`
(cursor falso não pega bug de SQL). Roda só quando há PG disponível; NUNCA contra
produção (guard do conftest). Os testes de bloqueio dão rollback e não mutam dados;
o teste do caminho permitido restaura o valor original.
"""
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

try:
    from db.connection import get_connection
    _pg_available = True
    try:
        _c = get_connection()
        _c.close()
    except Exception:
        _pg_available = False
except Exception:
    _pg_available = False

from repositories.admin_criteria import (
    AlertWeightBudgetExceeded,
    _alert_weight_sum,
    update_criterion,
)

CHECKLIST_ALERT = "CHECKLIST-VEICULO"
QUALIFICATION_ID = 316536  # "Realizou a qualificação correta do atendimento?", peso 0.3


@unittest.skipUnless(_pg_available, "PostgreSQL not available")
class TestWeightBudgetIntegration(unittest.TestCase):
    def _weight(self, criterion_id: int) -> float:
        conn = get_connection()
        try:
            c = conn.cursor()
            c.execute("SELECT weight FROM audit_criteria WHERE id = %s", (criterion_id,))
            row = c.fetchone()
            return float(row[0]) if row else None
        finally:
            conn.close()

    def test_alert_weight_sum_reads_real_total(self):
        conn = get_connection()
        try:
            c = conn.cursor()
            total = _alert_weight_sum(c, CHECKLIST_ALERT)
            self.assertAlmostEqual(total, 10.0, places=2)
            without_qualification = _alert_weight_sum(c, CHECKLIST_ALERT, exclude_id=QUALIFICATION_ID)
            self.assertAlmostEqual(without_qualification, 9.7, places=2)
        finally:
            conn.close()

    def test_update_over_budget_is_blocked_and_persists_nothing(self):
        before = self._weight(QUALIFICATION_ID)
        self.assertIsNotNone(before)
        with self.assertRaises(AlertWeightBudgetExceeded):
            # bumpar a qualificação para 5.0 levaria o alerta a 14.7 -> bloqueia
            update_criterion(
                get_connection,
                QUALIFICATION_ID,
                chave=None,
                label="Realizou a qualificação correta do atendimento?",
                weight=5.0,
                description=None,
                type="boolean",
                deflator=0,
                evaluation_type="manual",
                alterado_por="pytest",
                motivo="teste trava de pesos",
            )
        self.assertEqual(self._weight(QUALIFICATION_ID), before)

    def test_update_within_budget_is_allowed(self):
        before = self._weight(QUALIFICATION_ID)
        try:
            # reduzir para 0.2 deixa o alerta em 9.9 (<= 10) -> permitido
            update_criterion(
                get_connection,
                QUALIFICATION_ID,
                chave=None,
                label="Realizou a qualificação correta do atendimento?",
                weight=0.2,
                description="A qualificação correta ajuda a categorizar e analisar a qualidade do atendimento.",
                type="boolean",
                deflator=0,
                evaluation_type="manual",
                alterado_por="pytest",
                motivo="teste trava de pesos (permitido)",
            )
            self.assertAlmostEqual(self._weight(QUALIFICATION_ID), 0.2, places=2)
        finally:
            # restaura o valor original para não deixar resíduo no branch
            update_criterion(
                get_connection,
                QUALIFICATION_ID,
                chave=None,
                label="Realizou a qualificação correta do atendimento?",
                weight=before,
                description="A qualificação correta ajuda a categorizar e analisar a qualidade do atendimento.",
                type="boolean",
                deflator=0,
                evaluation_type="manual",
                alterado_por="pytest",
                motivo="restaura peso original",
            )


if __name__ == "__main__":
    unittest.main()
