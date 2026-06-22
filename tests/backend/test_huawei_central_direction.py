import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from core.huawei_direction import infer_is_call_in_from_central, resolve_huawei_is_call_in
from core.huawei_discovery import HuaweiDiscoveryService


# Números reais da central (47 3481-6122 / 47 2101-6122 + ramais do mesmo bloco).
CENTRAL = {"4734816122", "4721016122", "4734816171", "4734816142", "4721016142"}


class TestInferirDirecaoPelaCentral(unittest.TestCase):
    def test_central_e_quem_ligou_eh_feita(self):
        # central no caller -> ligação FEITA (outbound) -> False
        self.assertIs(
            infer_is_call_in_from_central("4734816122", "5547988887777", CENTRAL),
            False,
        )

    def test_central_e_quem_recebeu_eh_recebida(self):
        # central no callee -> ligação RECEBIDA (inbound) -> True
        self.assertIs(
            infer_is_call_in_from_central("5547988887777", "4721016122", CENTRAL),
            True,
        )

    def test_ignora_ddi_55_e_tronco_0(self):
        # prefixos de DDI/tronco não devem impedir o match por sufixo
        self.assertIs(infer_is_call_in_from_central("554734816122", "1999990000", CENTRAL), False)
        self.assertIs(infer_is_call_in_from_central("19996196108", "034721016122", CENTRAL), True)

    def test_ambos_central_fica_indefinido(self):
        # ligação interna (central dos dois lados) -> não dá pra decidir -> None
        self.assertIsNone(infer_is_call_in_from_central("4734816122", "4721016122", CENTRAL))

    def test_nenhum_central_fica_indefinido(self):
        self.assertIsNone(infer_is_call_in_from_central("11999990000", "11888887777", CENTRAL))

    def test_sem_lista_central_fica_indefinido(self):
        self.assertIsNone(infer_is_call_in_from_central("4734816122", "199", set()))

    def test_vazios_nao_quebram(self):
        self.assertIsNone(infer_is_call_in_from_central("", "", CENTRAL))
        self.assertIsNone(infer_is_call_in_from_central(None, None, CENTRAL))


class TestManifestoUsaCentralComoFallback(unittest.TestCase):
    def _row(self, caller, called):
        # linha de manifesto SEM rótulo explícito de direção e com workNo que
        # não casa com caller/callee (caso real que hoje vira "direção desconhecida").
        return {
            "callId": "1781472534-1001885",
            "caller": caller,
            "called": called,
            "workNo": "76",
            "beginTime": "1781472534000",
            "endTime": "1781472590000",
        }

    def test_recebida_quando_central_e_o_callee(self):
        inter = HuaweiDiscoveryService._manifest_row_to_interacao(
            self._row("5547988887777", "4734816122"), central_numbers=CENTRAL
        )
        self.assertEqual(inter["isCallIn"], "true")

    def test_feita_quando_central_e_o_caller(self):
        inter = HuaweiDiscoveryService._manifest_row_to_interacao(
            self._row("4721016122", "5547988887777"), central_numbers=CENTRAL
        )
        self.assertEqual(inter["isCallIn"], "false")

    def test_rotulo_explicito_continua_vencendo(self):
        # se a linha já trouxer isCallIn, a central não deve sobrescrever
        row = self._row("4721016122", "5547988887777")  # central=caller => feita
        row["isCallIn"] = "true"  # rótulo explícito (recebida) deve prevalecer
        inter = HuaweiDiscoveryService._manifest_row_to_interacao(row, central_numbers=CENTRAL)
        self.assertEqual(inter["isCallIn"], "true")


if __name__ == "__main__":
    unittest.main()
