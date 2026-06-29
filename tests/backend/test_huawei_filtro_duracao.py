import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from core.huawei.filtro_duracao import aplicar_filtro_duracao, avaliar_filtro_duracao


class TestFiltroDuracaoHuawei(unittest.TestCase):
    def test_minimo_e_inclusivo(self):
        abaixo = avaliar_filtro_duracao(
            {"callId": "call-109", "duration": 109},
            minimo_segundos=110,
            maximo_segundos=0,
        )
        no_limite = avaliar_filtro_duracao(
            {"callId": "call-110", "duration": 110},
            minimo_segundos=110,
            maximo_segundos=0,
        )
        acima = avaliar_filtro_duracao(
            {"callId": "call-111", "duration": 111},
            minimo_segundos=110,
            maximo_segundos=0,
        )

        self.assertTrue(abaixo.descartar)
        self.assertEqual(abaixo.contador, "ignoradas_duracao_minima")
        self.assertFalse(no_limite.descartar)
        self.assertIsNone(no_limite.contador)
        self.assertFalse(acima.descartar)

    def test_duracao_desconhecida_nao_descarta_mas_contabiliza(self):
        contadores = {}

        deve_descartar = aplicar_filtro_duracao(
            contadores,
            {"callId": "sem-duracao"},
            minimo_segundos=110,
            maximo_segundos=0,
        )

        self.assertFalse(deve_descartar)
        self.assertEqual(contadores["sem_duracao_consideradas"], 1)

    def test_maximo_opcional_so_bloqueia_quando_configurado(self):
        sem_maximo = avaliar_filtro_duracao(
            {"callId": "longa", "duration": 900},
            minimo_segundos=110,
            maximo_segundos=0,
        )
        com_maximo = avaliar_filtro_duracao(
            {"callId": "longa", "duration": 901},
            minimo_segundos=110,
            maximo_segundos=900,
        )

        self.assertFalse(sem_maximo.descartar)
        self.assertTrue(com_maximo.descartar)
        self.assertEqual(com_maximo.contador, "ignoradas_duracao_maxima")


if __name__ == "__main__":
    unittest.main()
