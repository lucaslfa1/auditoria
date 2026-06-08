"""Garantias de integridade para chaves bool em `configuracoes`.

Cobre a defesa adicionada em 2026-05-24 após o bug em que a UI gravou "1"
no lugar de "true" para `telefonia_cron_sync_ativa`. O teste evita que essa
divergência volte tanto na função pura `_normalize_boolean_value` quanto na
integração com `update_config`, que é o ponto de entrada real do router.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.configuration import (  # noqa: E402  (path setup acima)
    _BOOLEAN_KEYS,
    _normalize_boolean_value,
    update_config,
)


class TestNormalizeBooleanValue(unittest.TestCase):
    """Função pura — sem I/O. Garante que tokens conhecidos viram true/false."""

    def test_known_truthy_tokens_become_true(self):
        for token in ("true", "True", "TRUE", "1", " 1 ", "yes", "on", "sim", "t"):
            with self.subTest(token=token):
                self.assertEqual(
                    _normalize_boolean_value("telefonia_cron_sync_ativa", token),
                    "true",
                )

    def test_known_falsy_tokens_become_false(self):
        for token in ("false", "False", "0", "no", "off", "nao", "não", "f", " 0 "):
            with self.subTest(token=token):
                self.assertEqual(
                    _normalize_boolean_value("huawei_d1_enabled", token),
                    "false",
                )

    def test_unknown_token_is_preserved_unchanged(self):
        # Valores estranhos passam direto — preserva semântica para chaves bool
        # caso alguém mande algo realmente errado, evitando munge silencioso.
        self.assertEqual(
            _normalize_boolean_value("automacao_hibrida_ativa", "talvez"),
            "talvez",
        )

    def test_non_boolean_key_is_never_touched(self):
        # Chaves que não são booleanas precisam preservar valor literal, mesmo
        # quando o valor coincidentalmente parece um bool.
        self.assertEqual(_normalize_boolean_value("huawei_obs_bucket", "true"), "true")
        self.assertEqual(_normalize_boolean_value("huawei_d1_max_retries", "1"), "1")
        self.assertEqual(_normalize_boolean_value("huawei_d1_horario_execucao", "06:00"), "06:00")

    def test_boolean_keys_whitelist_covers_known_critical_flags(self):
        # Evita regressão se alguém remover uma chave do whitelist sem perceber.
        for chave in (
            "automacao_hibrida_ativa",
            "huawei_d1_enabled",
            "telefonia_cron_sync_ativa",
        ):
            self.assertIn(chave, _BOOLEAN_KEYS)


class TestUpdateConfigPersistsNormalizedBoolean(unittest.TestCase):
    """Integração: UI manda '1', banco recebe 'true' (string canônica)."""

    def _build_connection(self, valor_anterior: str | None = "false"):
        cursor = MagicMock()
        # 1ª chamada: SELECT valor, is_secret — devolve valor_anterior e is_secret=False
        if valor_anterior is None:
            cursor.fetchone.return_value = None
        else:
            cursor.fetchone.return_value = (valor_anterior, False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_ui_sends_one_persists_true(self):
        conn, cursor = self._build_connection(valor_anterior="false")
        factory = lambda: conn  # noqa: E731

        ok = update_config(
            factory,
            "telefonia_cron_sync_ativa",
            "1",
            alterado_por="ui-user",
            motivo="teste",
            origem="ui",
        )

        self.assertTrue(ok)
        # O 2º execute é o UPSERT — confere que o valor persistido foi 'true', não '1'.
        upsert_call = cursor.execute.call_args_list[1]
        params = upsert_call.args[1]
        self.assertEqual(params, ("telefonia_cron_sync_ativa", "true"))

    def test_ui_sends_zero_persists_false(self):
        conn, cursor = self._build_connection(valor_anterior="true")
        factory = lambda: conn  # noqa: E731

        update_config(
            factory,
            "huawei_d1_enabled",
            "0",
            alterado_por="ui-user",
            origem="ui",
        )

        upsert_call = cursor.execute.call_args_list[1]
        self.assertEqual(upsert_call.args[1], ("huawei_d1_enabled", "false"))

    def test_non_boolean_key_preserves_value(self):
        conn, cursor = self._build_connection(valor_anterior="06:00")
        factory = lambda: conn  # noqa: E731

        update_config(
            factory,
            "huawei_d1_horario_execucao",
            "06:00",
            alterado_por="ui-user",
            origem="ui",
        )

        upsert_call = cursor.execute.call_args_list[1]
        self.assertEqual(upsert_call.args[1], ("huawei_d1_horario_execucao", "06:00"))


if __name__ == "__main__":
    unittest.main()
