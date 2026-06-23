"""Mensagem final do ciclo de automacao em PT-BR construtivo (sem "erro" falso).

Cobre:
- `summarize_discard_reasons`: traduz os codigos de descarte (discarded_*) para
  rotulos legiveis, ordenados por contagem.
- `build_cycle_completion_message`: monta a frase do painel "Andamento" focada no
  resultado (auditadas/descartadas + motivo), e NAO no generico "verifique o
  detalhe do erro" quando o ciclo foi so parcial pela regra de cobertura.
"""
import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.automation import build_cycle_completion_message, summarize_discard_reasons


class TestSummarizeDiscardReasons(unittest.TestCase):
    def test_vazio_ou_none_retorna_string_vazia(self):
        self.assertEqual(summarize_discard_reasons({}), "")
        self.assertEqual(summarize_discard_reasons(None), "")

    def test_zera_contagens_nulas(self):
        self.assertEqual(summarize_discard_reasons({"discarded_unknown_alert": 0}), "")

    def test_motivo_unico_mostra_so_o_rotulo(self):
        self.assertEqual(
            summarize_discard_reasons({"discarded_unknown_alert": 4}),
            "alerta inelegível",
        )

    def test_varios_motivos_ordenados_por_contagem_com_numero(self):
        self.assertEqual(
            summarize_discard_reasons(
                {"discarded_unknown_alert": 3, "discarded_no_criteria": 1}
            ),
            "alerta inelegível (3), sem critério oficial (1)",
        )

    def test_codigo_desconhecido_usa_fallback_humanizado(self):
        self.assertEqual(
            summarize_discard_reasons({"discarded_foo_bar": 2}),
            "foo bar",
        )


class TestBuildCycleCompletionMessage(unittest.TestCase):
    def test_ok_com_auditada_e_descartadas_mostra_motivo(self):
        msg = build_cycle_completion_message(
            cycle_status="ok",
            baixadas=6,
            auditadas=1,
            descartados=4,
            discard_reasons={"discarded_unknown_alert": 4},
        )
        self.assertEqual(
            msg,
            "Ciclo concluído: 1 auditada e 4 descartadas (alerta inelegível).",
        )

    def test_ok_so_auditadas(self):
        msg = build_cycle_completion_message(
            cycle_status="ok", baixadas=0, auditadas=2, descartados=0
        )
        self.assertEqual(msg, "Ciclo concluído: 2 auditadas.")

    def test_ok_sem_downloads_usa_filtros(self):
        msg = build_cycle_completion_message(
            cycle_status="ok",
            baixadas=0,
            auditadas=0,
            descartados=0,
            zero_download_filters="operador Huawei nao cadastrado: 12",
        )
        self.assertEqual(
            msg,
            "Ciclo concluído sem downloads novos; principais filtros: "
            "operador Huawei nao cadastrado: 12.",
        )

    def test_falha_real_mostra_motivo_e_nao_pede_para_verificar_detalhe(self):
        msg = build_cycle_completion_message(
            cycle_status="partial",
            baixadas=3,
            auditadas=1,
            descartados=0,
            last_error="2 item(ns) falharam na auditoria automatica.",
        )
        self.assertEqual(
            msg,
            "Ciclo concluído com atenção: 2 item(ns) falharam na auditoria automatica.",
        )
        self.assertNotIn("Verifique o detalhe do erro", msg)


if __name__ == "__main__":
    unittest.main()
