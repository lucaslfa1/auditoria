import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.audit_rules import (  # noqa: E402
    get_fatal_flag_reason_text,
    get_fatal_flag_sectors,
    get_fatal_keywords_for_sector,
    get_sector_prompt_rules,
    password_rule_applies_to_sector,
)


class TestAuditRulesConfig(unittest.TestCase):
    def test_loads_sector_prompt_rules_from_config(self):
        cadastro = get_sector_prompt_rules("cadastro")

        self.assertIsNotNone(cadastro)
        self.assertEqual(cadastro["label"], "Cadastro")
        self.assertEqual(cadastro["tipo_ligacao"], "Ligacao Receptiva")
        self.assertIn("45 segundos", cadastro["regras_zeragem"])

    def test_password_rule_scope_is_config_driven(self):
        self.assertFalse(password_rule_applies_to_sector("logistica"))
        self.assertTrue(password_rule_applies_to_sector("transferencia"))

    def test_fatal_flags_and_keywords_are_config_driven(self):
        self.assertEqual(get_fatal_flag_sectors("bloqueio_cadastro"), {"cadastro"})
        self.assertIn("bloqueio", get_fatal_flag_reason_text("bloqueio_cadastro"))
        self.assertIn("senha ou cpf", get_fatal_keywords_for_sector("bas"))


if __name__ == "__main__":
    unittest.main()
