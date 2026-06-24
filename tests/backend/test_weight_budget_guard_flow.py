"""Fluxo da trava: create/update_criterion BLOQUEIAM antes de mutar.

Usa um cursor falso só para o caminho de BLOQUEIO (que nem chega ao INSERT/UPDATE
nem ao audit_log): prova que, quando a soma passaria de 10, a função levanta
``AlertWeightBudgetExceeded`` sem executar a escrita e dá rollback. Não testa a
correção do SQL (isso é coberto por um smoke-test read-only contra o banco real);
testa o CONTROLE DE FLUXO da trava. Sem banco — sempre roda.
"""
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from repositories.admin_criteria import (
    AlertWeightBudgetExceeded,
    create_criterion,
    update_criterion,
)

_CRITERION_ROW = (
    316536, "CHECKLIST-VEICULO", "qualificacao",
    "Realizou a qualificação correta do atendimento?", 0.3,
    "desc", "boolean", 0, None, None, "manual",
)


class _FakeCursor:
    def __init__(self, existing_sum, existing_row=None):
        self._existing_sum = existing_sum
        self._existing_row = existing_row
        self.executed = []
        self._last = ""

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        self._last = sql

    def fetchone(self):
        s = self._last or ""
        if "SUM(weight)" in s:
            return (self._existing_sum,)
        if s.strip().startswith("SELECT id, alert_id"):
            return self._existing_row
        if "RETURNING id" in s:
            return (999,)
        return None

    @property
    def rowcount(self):
        return 1


class _FakeConn:
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


class TestWeightBudgetGuardFlow(unittest.TestCase):
    def test_create_over_budget_raises_before_insert(self):
        cur = _FakeCursor(existing_sum=9.7)
        conn = _FakeConn(cur)
        with self.assertRaises(AlertWeightBudgetExceeded):
            create_criterion(
                lambda: conn,
                alert_id="CHECKLIST-VEICULO",
                chave="novo",
                label="Novo critério",
                weight=0.5,  # 9.7 + 0.5 = 10.2 -> passa de 10
                alterado_por="pytest",
                motivo="teste",
            )
        self.assertFalse(any("INSERT INTO audit_criteria" in s for s, _ in cur.executed))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)

    def test_update_over_budget_raises_before_update(self):
        cur = _FakeCursor(existing_sum=9.7, existing_row=_CRITERION_ROW)
        conn = _FakeConn(cur)
        with self.assertRaises(AlertWeightBudgetExceeded):
            update_criterion(
                lambda: conn,
                316536,
                chave="qualificacao",
                label="Realizou a qualificação correta do atendimento?",
                weight=5.0,  # outros 9.7 + 5.0 = 14.7 -> passa de 10
                description="desc",
                type="boolean",
                deflator=0,
                evaluation_type="manual",
                alterado_por="pytest",
                motivo="teste",
            )
        self.assertFalse(any(s.strip().startswith("UPDATE audit_criteria") for s, _ in cur.executed))
        self.assertTrue(conn.rolled_back)
        self.assertFalse(conn.committed)


if __name__ == "__main__":
    unittest.main()
