"""Testes do serviço `build_operadores_mes` (painel Auditorias do mês por operador).

Cobrem: ordenação por contagem desc, marcação `cheio` na borda da cota, roster
vazio, cota dinâmica e formato do mês. Mockam roster + contagem bulk + cota, então
não tocam o banco.

Ponto sensível coberto: a chave de contagem usa a MATRÍCULA (é o que
`audits.operator_id` guarda no banco real). Casar por id_telefonia/id_huawei
zeraria a contagem de todos.
"""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import automation_operator_report as report


def _roster(*operadores):
    """Monta um roster no formato de `listar_auditaveis_com_id_huawei`."""
    out = []
    for nome, setor, matricula in operadores:
        out.append(
            {
                "nome": nome,
                "setor": setor,
                "matricula": matricula,
                "id_huawei": f"h-{matricula}",
                "id_telefonia": f"t-{matricula}",
            }
        )
    return out


class TestBuildOperadoresMes(unittest.TestCase):
    def _run(self, roster, counts, cota=2, agora=datetime(2026, 6, 15)):
        captured = {}

        def fake_bulk(get_connection, keys, year, month):
            captured["keys"] = keys
            captured["year"] = year
            captured["month"] = month
            return counts

        with patch.object(report.operators, "listar_auditaveis_com_id_huawei", return_value=roster), \
             patch.object(report, "get_operator_audit_counts_for_month_bulk", side_effect=fake_bulk), \
             patch.object(report, "_get_monthly_audit_quota", return_value=cota):
            result = report.build_operadores_mes(get_connection=lambda: None, agora=agora)
        return result, captured

    def test_ordena_por_contagem_desc_e_marca_cheio(self):
        roster = _roster(
            ("Bruna Cardoso", "Distribuição", "11576"),
            ("Eleanor Sasse", "UTI", "11123"),
            ("Zero Person", "Fênix", "99999"),
        )
        counts = {
            ("eleanor sasse", "11123"): 2,
            ("bruna cardoso", "11576"): 1,
            # Zero Person ausente → default 0
        }
        result, _ = self._run(roster, counts, cota=2)

        nomes = [o["nome"] for o in result["operadores"]]
        self.assertEqual(nomes, ["Eleanor Sasse", "Bruna Cardoso", "Zero Person"])

        por_nome = {o["nome"]: o for o in result["operadores"]}
        self.assertEqual(por_nome["Eleanor Sasse"]["auditorias_mes"], 2)
        self.assertTrue(por_nome["Eleanor Sasse"]["cheio"])
        self.assertEqual(por_nome["Bruna Cardoso"]["auditorias_mes"], 1)
        self.assertFalse(por_nome["Bruna Cardoso"]["cheio"])
        self.assertEqual(por_nome["Zero Person"]["auditorias_mes"], 0)
        self.assertFalse(por_nome["Zero Person"]["cheio"])
        self.assertEqual(por_nome["Eleanor Sasse"]["setor"], "UTI")
        self.assertEqual(por_nome["Eleanor Sasse"]["operator_id"], "11123")
        self.assertEqual(result["cota"], 2)

    def test_chave_de_contagem_usa_matricula(self):
        """Garante que a chave passada ao bulk é (nome, matrícula), não id_telefonia/huawei."""
        roster = _roster(("Eleanor Sasse", "UTI", "11123"))
        result, captured = self._run(roster, {("eleanor sasse", "11123"): 2}, cota=2)
        self.assertIn(("Eleanor Sasse", "11123"), captured["keys"])
        # nenhuma chave deve usar os ids de telefonia/huawei
        ids_usados = {k[1] for k in captured["keys"]}
        self.assertEqual(ids_usados, {"11123"})

    def test_borda_cheio_exata(self):
        roster = _roster(("A", "UTI", "1"), ("B", "UTI", "2"))
        counts = {("a", "1"): 2, ("b", "2"): 1}
        result, _ = self._run(roster, counts, cota=2)
        por_nome = {o["nome"]: o for o in result["operadores"]}
        self.assertTrue(por_nome["A"]["cheio"])   # == cota
        self.assertFalse(por_nome["B"]["cheio"])  # == cota - 1

    def test_roster_vazio(self):
        result, _ = self._run([], {}, cota=2)
        self.assertEqual(result["operadores"], [])
        self.assertEqual(result["cota"], 2)
        self.assertEqual(result["mes"], "2026-06")

    def test_cota_dinamica_recalcula_cheio(self):
        roster = _roster(("Eleanor Sasse", "UTI", "11123"))
        counts = {("eleanor sasse", "11123"): 2}
        result, _ = self._run(roster, counts, cota=3)
        self.assertFalse(result["operadores"][0]["cheio"])  # 2 < 3
        self.assertEqual(result["cota"], 3)

    def test_mes_formatado_e_periodo_passado_ao_bulk(self):
        roster = _roster(("Eleanor Sasse", "UTI", "11123"))
        result, captured = self._run(roster, {}, agora=datetime(2026, 6, 15))
        self.assertEqual(result["mes"], "2026-06")
        self.assertEqual(captured["year"], 2026)
        self.assertEqual(captured["month"], 6)


class TestOperadoresMesEndpoint(unittest.TestCase):
    """O endpoint só delega ao serviço (a lógica é testada acima); aqui garantimos
    o roteamento e que ele devolve o payload do serviço sem mexer nele."""

    def test_endpoint_delega_ao_servico(self):
        from routers import automation as automation_router

        payload = {
            "mes": "2026-06",
            "cota": 2,
            "operadores": [
                {"nome": "Eleanor Sasse", "setor": "UTI", "operator_id": "11123",
                 "auditorias_mes": 2, "cheio": True},
            ],
        }
        with patch.object(automation_router, "build_operadores_mes", return_value=payload) as mock_build:
            result = automation_router.get_operadores_mes(_user=None)

        self.assertEqual(result, payload)
        mock_build.assert_called_once()


if __name__ == "__main__":
    unittest.main()
