import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from core.huawei.teto_operador import (
    CONTADOR_TETO_OPERADOR,
    MOTIVO_LOG_TETO_OPERADOR,
    aplicar_teto_operador,
    avaliar_teto_operador,
    registrar_download_operador,
)


class TestTetoOperadorHuawei(unittest.TestCase):
    def test_bloqueia_quando_operador_atinge_teto_do_ciclo(self):
        operador = {
            "nome": "Operadora Huawei",
            "id_telefonia": "HUA-123",
            "id_huawei": "HUA-123",
        }
        downloads_por_operador = {}
        contadores = {}

        for _ in range(3):
            resultado = aplicar_teto_operador(
                contadores,
                downloads_por_operador,
                operador,
                teto_por_operador=3,
            )
            self.assertFalse(resultado.descartar)
            registrar_download_operador(downloads_por_operador, resultado)

        bloqueio = aplicar_teto_operador(
            contadores,
            downloads_por_operador,
            operador,
            teto_por_operador=3,
        )

        self.assertTrue(bloqueio.descartar)
        self.assertEqual(bloqueio.contador, CONTADOR_TETO_OPERADOR)
        self.assertEqual(bloqueio.motivo_log, MOTIVO_LOG_TETO_OPERADOR)
        self.assertEqual(bloqueio.agent_id, "hua-123")
        self.assertEqual(contadores[CONTADOR_TETO_OPERADOR], 1)

    def test_teto_zero_significa_ilimitado(self):
        operador = {"nome": "Operadora Huawei", "id_huawei": "HUA-123"}
        downloads_por_operador = {("operadora huawei", "hua-123"): 50}

        resultado = avaliar_teto_operador(
            downloads_por_operador,
            operador,
            teto_por_operador=0,
        )

        self.assertFalse(resultado.descartar)
        self.assertIsNone(resultado.contador)

    def test_operador_sem_identidade_nao_e_bloqueado_por_teto(self):
        downloads_por_operador = {("", ""): 50}

        resultado = avaliar_teto_operador(
            downloads_por_operador,
            {},
            teto_por_operador=3,
        )

        self.assertFalse(resultado.descartar)
        self.assertIsNone(resultado.agent_id)


if __name__ == "__main__":
    unittest.main()
