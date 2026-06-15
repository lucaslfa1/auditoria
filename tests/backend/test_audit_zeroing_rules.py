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

    def test_password_fail_does_not_zero_when_driver_denies_password_before_cpf(self):
        result = result_from_raw(
            {
                "summary": "Condutor sem senha validado por CPF.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "fail",
                        "comment": "A senha nao foi confirmada porque o condutor informou que nao tinha senha.",
                    },
                    {
                        "criterionId": "saudacao",
                        "status": "pass",
                        "comment": "Saudacao realizada.",
                    },
                ],
                "fatal_flags": [],
            },
            [
                AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0),
                AuditCriterion(id="saudacao", label="Realizou saudação?", weight=1.0),
            ],
            transcription_data=[
                {"start": "00:00", "end": "00:02", "text": "Operador: O senhor confirma a senha de seguranca?"},
                {"start": "00:02", "end": "00:04", "text": "Motorista: Eu nao tenho senha, nao recebi."},
                {"start": "00:04", "end": "00:06", "text": "Operador: Entao confirma seu CPF, por favor."},
                {"start": "00:06", "end": "00:09", "text": "Motorista: 12345678901."},
            ],
            sector_id="bas",
        )

        self.assertEqual(result.score, 1.0)
        self.assertNotIn("Nota zerada", result.summary)

    def test_false_cpf_fatal_flag_is_ignored_when_password_fallback_is_legitimate(self):
        result = result_from_raw(
            {
                "summary": "Condutor sem senha validado por CPF.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "pass",
                        "comment": "Condutor informou que nao tinha senha; CPF foi usado como fallback.",
                    }
                ],
                "fatal_flags": ["solicitar_senha_ou_cpf"],
            },
            [AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0)],
            transcription_data=[
                {"start": "00:00", "end": "00:02", "text": "Operador: Pode confirmar a senha de seguranca?"},
                {"start": "00:02", "end": "00:04", "text": "Motorista: Nao tenho a senha."},
                {"start": "00:04", "end": "00:06", "text": "Operador: Tudo bem, confirma o CPF."},
            ],
            sector_id="bas",
        )

        self.assertEqual(result.score, 2.0)
        self.assertNotIn("Nota zerada", result.summary)
        self.assertNotIn("solicitar_senha_ou_cpf", result.fatal_flags)

    def test_direct_cpf_request_without_password_denial_still_zeroes(self):
        result = result_from_raw(
            {
                "summary": "Operador pediu CPF direto.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "pass",
                        "comment": "Operador validou CPF.",
                    }
                ],
                "fatal_flags": ["solicitar_senha_ou_cpf"],
            },
            [AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0)],
            transcription_data=[
                {"start": "00:00", "end": "00:02", "text": "Operador: Confirma seu CPF, por favor."},
                {"start": "00:02", "end": "00:05", "text": "Motorista: 12345678901."},
            ],
            sector_id="bas",
        )

        self.assertEqual(result.score, 0.0)
        self.assertIn("Nota zerada", result.summary)
        self.assertIn("solicitar_senha_ou_cpf", result.fatal_flags)

    def test_operator_assumed_denial_without_driver_confirmation_still_zeroes(self):
        # Regra 2026-06-12: a confirmacao de "nao tem senha" PRECISA vir do
        # motorista. O operador presumir ("o senhor nao tem a senha, ne?") e
        # ir direto pro CPF, sem o motorista confirmar, NAO e fallback legitimo
        # e deve zerar.
        result = result_from_raw(
            {
                "summary": "Operador presumiu ausencia de senha e foi pro CPF.",
                "details": [
                    {
                        "criterionId": "senha",
                        "status": "pass",
                        "comment": "Operador validou CPF.",
                    }
                ],
                "fatal_flags": ["solicitar_senha_ou_cpf"],
            },
            [AuditCriterion(id="senha", label="Confirmou a senha de segurança?", weight=2.0)],
            transcription_data=[
                {"start": "00:00", "end": "00:03", "text": "Operador: O senhor nao tem a senha, ne? Entao confirma o CPF."},
                {"start": "00:03", "end": "00:06", "text": "Motorista: 12345678901."},
            ],
            sector_id="bas",
        )

        self.assertEqual(result.score, 0.0)
        self.assertIn("Nota zerada", result.summary)
        self.assertIn("solicitar_senha_ou_cpf", result.fatal_flags)


if __name__ == "__main__":
    unittest.main()
