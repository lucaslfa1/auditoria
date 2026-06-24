"""Trava: a soma dos pesos de um alerta não pode passar de 10.

A nota é calculada como (pontos obtidos / soma dos pesos) * 10. Isso só equivale
a "peso = ponto na escala 0-10" quando a soma dos pesos do alerta é 10. Editar um
peso e deixar a soma passar de 10 reescala todos os critérios e infla a nota (foi
o caso da qualificação: nota 4,00 -> 9,07). Esta trava bloqueia o save que faria a
soma passar de 10. A lógica de decisão é uma função pura (sem banco).
"""
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from repositories.admin_criteria import (
    WEIGHT_BUDGET,
    weight_budget_exceeded,
    weight_budget_message,
)


class TestWeightBudgetGuard(unittest.TestCase):
    def test_budget_is_ten(self):
        self.assertEqual(WEIGHT_BUDGET, 10.0)

    def test_exact_ten_is_allowed(self):
        # alerta com os outros critérios somando 9,7; novo/atualizado peso 0,3 -> 10,0
        self.assertFalse(weight_budget_exceeded(9.7, 0.3))

    def test_under_ten_is_allowed(self):
        # estado em progresso (ex.: após excluir um critério) deve ser permitido
        self.assertFalse(weight_budget_exceeded(9.0, 0.3))

    def test_over_ten_is_blocked(self):
        # 9,7 + 0,4 = 10,1 -> passa de 10 -> bloqueia
        self.assertTrue(weight_budget_exceeded(9.7, 0.4))

    def test_qualification_incident_is_blocked(self):
        # o incidente real: bumpar a qualificação de 0,3 para 5,0 com os demais em 9,7
        self.assertTrue(weight_budget_exceeded(9.7, 5.0))

    def test_float_tolerance_does_not_false_block(self):
        # somas de floats (0.1*n) podem dar 10.000000001; tolerância não pode bloquear o 10 legítimo
        self.assertFalse(weight_budget_exceeded(9.7, 0.30000000000001))

    def test_message_mentions_alert_and_total(self):
        msg = weight_budget_message("CHECKLIST-VEICULO", existing_sum=9.7, new_weight=5.0)
        self.assertIn("CHECKLIST-VEICULO", msg)
        self.assertIn("14.7", msg)
        self.assertIn("10", msg)


if __name__ == "__main__":
    unittest.main()
