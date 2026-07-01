"""Triagem de áudio puro: identidade do operador resolvida pela FALA (v1.3.212).

Cobre a extração do primeiro nome falado, a detecção de setor falado (desempate)
e o resolvedor `resolve_operator_from_speech` — incluindo os casos conservadores
(ambíguo => revisão manual) e de robustez (falha de banco => None, nunca levanta).
"""

import unittest
from unittest.mock import patch

from core import classification


class TestExtracaoNomeFalado(unittest.TestCase):
    def test_extrai_primeiro_nome_das_apresentacoes_reais(self):
        casos = {
            "Alô, aqui é a Valéria da base de logística da MST": "valeria",
            "cadastro Opentech Dayane, boa noite, com quem eu falo?": "dayane",
            "Aqui o Vinicius do setor de temperatura da Opentech": "vinicius",
            "me chamo Gabrielle, eu sou de uma base de sinistro": "gabrielle",
            "Meu nome é Marcela da central de sinistro da Opentech": "marcela",
        }
        for fala, esperado in casos.items():
            with self.subTest(fala=fala):
                self.assertEqual(
                    classification._extract_spoken_operator_first_name(fala), esperado
                )

    def test_nao_extrai_quando_nao_ha_apresentacao(self):
        # "falo com o Everson" é o operador PEDINDO o nome do outro, não o dele.
        self.assertIsNone(
            classification._extract_spoken_operator_first_name("Oi, eu falo com o Everson Soares?")
        )
        self.assertIsNone(
            classification._extract_spoken_operator_first_name("Bom dia, tudo bem com você?")
        )

    def test_ignora_token_que_nao_e_nome(self):
        # "aqui a gente vai verificar" -> "gente" é stopword, não vira nome.
        self.assertIsNone(
            classification._extract_spoken_operator_first_name("aqui a gente vai verificar pra você")
        )


class TestSetorFalado(unittest.TestCase):
    def test_detecta_setores_pelos_termos_falados(self):
        self.assertIn("logistica", classification._spoken_sector_ids("base de logística, temperatura do baú"))
        self.assertIn("cadastro", classification._spoken_sector_ids("consulta de cadastro e antecedentes"))
        self.assertEqual(set(), classification._spoken_sector_ids("oi, tudo bem? só um momento"))


class TestResolveOperatorFromSpeech(unittest.TestCase):
    def test_unico_candidato_resolve(self):
        cand = {"name": "Dayane Rodrigues de Lara", "setor": "cadastro", "matricula": "123"}
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
            return_value=[cand],
        ):
            self.assertEqual(
                classification.resolve_operator_from_speech("cadastro Opentech Dayane, boa noite"),
                cand,
            )

    def test_homonimos_desempatados_pelo_setor_falado(self):
        c1 = {"name": "Valeria Alpha", "setor": "logistica"}
        c2 = {"name": "Valeria Beta", "setor": "bas"}
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
            return_value=[c1, c2],
        ), patch(
            "core.classification._get_effective_db_sector",
            side_effect=lambda rh: rh.get("setor"),
        ):
            self.assertEqual(
                classification.resolve_operator_from_speech("aqui é a Valéria da base de logística"),
                c1,
            )

    def test_homonimos_sem_desempate_vao_para_manual(self):
        c1 = {"name": "Valeria Alpha", "setor": "logistica"}
        c2 = {"name": "Valeria Beta", "setor": "bas"}
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
            return_value=[c1, c2],
        ), patch(
            "core.classification._get_effective_db_sector",
            side_effect=lambda rh: rh.get("setor"),
        ):
            self.assertIsNone(
                classification.resolve_operator_from_speech("aqui é a Valéria, tudo bem?")
            )

    def test_sem_candidato_retorna_none(self):
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
            return_value=[],
        ):
            self.assertIsNone(classification.resolve_operator_from_speech("me chamo Fulano"))

    def test_sem_nome_falado_nem_consulta_o_banco(self):
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
        ) as mock_lookup:
            self.assertIsNone(classification.resolve_operator_from_speech("bom dia, tudo bem?"))
            mock_lookup.assert_not_called()

    def test_falha_de_banco_nao_propaga(self):
        with patch(
            "repositories.operators.listar_colaboradores_por_primeiro_nome",
            side_effect=RuntimeError("db down"),
        ):
            self.assertIsNone(
                classification.resolve_operator_from_speech("aqui é a Valéria da logística")
            )


if __name__ == "__main__":
    unittest.main()
