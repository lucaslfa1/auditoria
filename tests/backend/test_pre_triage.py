import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import pre_triage


class TestPreTriagemDirecao(unittest.IsolatedAsyncioTestCase):
    def test_infer_direction_detects_inbound_service_greeting(self):
        result = pre_triage._infer_direction_from_segments(
            [
                {
                    "text": "Operador: Alo Opentech, bom dia, como posso ajudar?",
                }
            ]
        )

        self.assertTrue(result)

    def test_infer_direction_detects_outbound_when_external_answers_first(self):
        result = pre_triage._infer_direction_from_segments(
            [
                {"text": "Motorista: Alo?"},
                {"text": "Operador: Bom dia, eu falo com o senhor Joao?"},
            ]
        )

        self.assertFalse(result)

    def test_infer_direction_detects_outbound_operator_contact_opening(self):
        result = pre_triage._infer_direction_from_segments(
            [
                {
                    "text": "Operador: Alo, boa noite, eu falo com o condutor Marcos?",
                }
            ]
        )

        self.assertFalse(result)

    def test_infer_direction_keeps_ambiguous_operator_greeting_unknown(self):
        result = pre_triage._infer_direction_from_segments(
            [
                {
                    "text": "Operador: Alo, bom dia.",
                }
            ]
        )

        self.assertIsNone(result)

    async def test_analyze_call_direction_uses_diarized_excerpt(self):
        with patch("core.pre_triage._slice_audio_to_wav", return_value=b"wav") as slicer:
            with patch(
                "core.pre_triage._transcribe_diarized_excerpt",
                return_value=[{"text": "Operador: Alo Opentech, bom dia, como posso ajudar?"}],
            ) as transcribe:
                result = await pre_triage.analyze_call_direction(b"audio", duration_ms=1234)

        self.assertTrue(result)
        slicer.assert_called_once_with(b"audio", 1234)
        transcribe.assert_called_once_with(b"wav")

    async def test_service_greeting_overrides_ambiguous_ai(self):
        """Frase de atendimento forte do operador classifica receptiva (INBOUND)
        ANTES da IA, mesmo que a IA responda OUTBOUND. Resolve o vazamento por
        'AMBIGUOUS' em setores de risco."""
        import json
        from unittest.mock import AsyncMock, MagicMock

        fake_resp = MagicMock()
        fake_resp.choices = [
            MagicMock(message=MagicMock(content=json.dumps({"direcao": "OUTBOUND", "analise": "mock"})))
        ]
        fake_client = MagicMock()
        fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

        with patch("core.pre_triage._slice_audio_to_wav", return_value=b"wav"), patch(
            "core.pre_triage._transcribe_diarized_excerpt",
            return_value=[{"text": "Operador: Em que posso ajudar?"}],
        ), patch.dict(
            os.environ, {"AZURE_OPENAI_ENDPOINT": "https://x", "AZURE_OPENAI_KEY": "y"}
        ), patch("openai.AsyncAzureOpenAI", return_value=fake_client):
            result = await pre_triage.analyze_call_direction(b"audio")

        # A frase determinística deve decidir receptiva sem depender da IA.
        self.assertTrue(result)
        fake_client.chat.completions.create.assert_not_awaited()


class TestDetectServiceGreeting(unittest.TestCase):
    def _utt(self, text):
        return pre_triage._first_utterances([{"text": text}])

    def test_detects_offer_to_help(self):
        self.assertTrue(pre_triage._detect_service_greeting(self._utt("Operador: Em que posso ajudar?")))

    def test_detects_central_greeting_by_operator(self):
        self.assertTrue(
            pre_triage._detect_service_greeting(self._utt("Operador: Central de atendimento, bom dia."))
        )

    def test_rejects_outbound_contact_opening(self):
        self.assertFalse(
            pre_triage._detect_service_greeting(self._utt("Operador: Bom dia, eu falo com o senhor Joao?"))
        )

    def test_detects_thanks_for_calling(self):
        # Saudacao de quem RECEBE a ligacao (frase de atendimento adicional).
        self.assertTrue(
            pre_triage._detect_service_greeting(self._utt("Operador: Opentech, obrigada por ligar."))
        )

    def test_rejects_when_outbound_reason_marker_present(self):
        # Ativa: operador liga e diz o MOTIVO; um "posso ajudar" solto nao deve
        # transformar a ligacao em receptiva (evita descartar ativa legitima).
        self.assertFalse(
            pre_triage._detect_service_greeting(
                self._utt(
                    "Operador: Bom dia, estou entrando em contato referente ao veiculo, posso ajudar?"
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
