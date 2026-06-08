import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.automation_rules import filtrar_chamadas, get_call_duration_seconds, get_call_reason_text


class TestAutomationRules(unittest.TestCase):
    def test_get_call_duration_seconds_falls_back_to_call_begin_and_end(self):
        chamada = {
            "callBegin": 1776893124000,
            "callEnd": 1776893299000,
        }

        self.assertEqual(get_call_duration_seconds(chamada), 175)

    def test_filtrar_chamadas_allows_missing_reason_for_llm_triage(self):
        chamadas = [
            {
                "callId": "call-1",
                "callBegin": 1776893124000,
                "callEnd": 1776893299000,
                "leaveReason": 16,
            }
        ]

        filtradas = filtrar_chamadas(
            chamadas,
            {
                "duracao_min_segundos": 90,
                "motivos_alvo": ["PARADA"],
                "use_llm_triage": True,
            },
        )

        self.assertEqual(len(filtradas), 1)
        self.assertEqual(filtradas[0]["duration"], 175)

    def test_filtrar_chamadas_keeps_reason_required_when_llm_is_not_used(self):
        chamadas = [
            {
                "callId": "call-1",
                "callBegin": 1776893124000,
                "callEnd": 1776893299000,
                "leaveReason": 16,
            }
        ]

        filtradas = filtrar_chamadas(
            chamadas,
            {
                "duracao_min_segundos": 90,
                "motivos_alvo": ["PARADA"],
                "use_llm_triage": False,
            },
        )

        self.assertEqual(filtradas, [])

    def test_filtrar_chamadas_keeps_native_reason_mismatch_for_llm_triage(self):
        chamadas = [
            {"callId": "call-match", "duration": 120, "callReason": "PARADA"},
            {"callId": "call-mismatch", "duration": 120, "callReason": "ASSUNTO ADMINISTRATIVO"},
        ]

        filtradas = filtrar_chamadas(
            chamadas,
            {
                "duracao_min_segundos": 90,
                "motivos_alvo": ["PARADA"],
                "use_llm_triage": True,
            },
        )

        self.assertEqual([item["callId"] for item in filtradas], ["call-match", "call-mismatch"])
        self.assertEqual([item["native_reason_match"] for item in filtradas], [True, False])

    def test_get_call_reason_text_uses_huawei_native_reason_aliases(self):
        self.assertEqual(
            get_call_reason_text({"talkRemark": "Devolucao parcial"}),
            "Devolucao parcial",
        )
        self.assertEqual(
            get_call_reason_text({"huawei_call_reason": "Antecedentes"}),
            "Antecedentes",
        )


if __name__ == "__main__":
    unittest.main()
