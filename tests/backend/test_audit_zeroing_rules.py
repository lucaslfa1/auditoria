import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.evaluation import result_from_raw
from schemas import AuditCriterion


class TestAuditZeroingRules(unittest.TestCase):
    def test_revealing_wrong_password_zeroes_bas_audit(self):
        result = result_from_raw(
            {
                "summary": "Atendimento com falha de senha.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "pass",
                        "comment": "A senha foi solicitada.",
                    }
                ],
                "fatal_flags": ["senha_errada_revelada"],
            },
            [AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0)],
            transcription_data=[{"start": "00:00", "end": "00:05", "text": "Operador: senha incorreta."}],
            sector_id="bas",
        )

        self.assertEqual(result.score, 0.0)
        self.assertIn("senha informada estava incorreta", result.summary)
        self.assertIn("senha_errada_revelada", result.fatal_flags)

    def test_cpf_fallback_without_fatal_flag_does_not_zero(self):
        result = result_from_raw(
            {
                "summary": "Condutor sem senha informou CPF como fallback.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "pass",
                        "comment": "Condutor informou que nao tinha senha; CPF foi usado como fallback legitimo.",
                    }
                ],
                "fatal_flags": [],
            },
            [AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0)],
            transcription_data=[{"start": "00:00", "end": "00:05", "text": "Motorista: nao recebi a senha."}],
            sector_id="bas",
        )

        self.assertEqual(result.score, 2.0)
        self.assertNotIn("Nota zerada", result.summary)


if __name__ == "__main__":
    unittest.main()
