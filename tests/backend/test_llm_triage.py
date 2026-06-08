import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import llm_triage


class TestLLMTriage(unittest.IsolatedAsyncioTestCase):
    def _call(self, call_id: str, duration: int, reason: str = "PARADA") -> dict:
        return {
            "callId": call_id,
            "duration": duration,
            "callReason": reason,
            "beginTime": "2026-04-19T10:00:00Z",
        }

    def test_parse_ids_aprovados_ignores_invalid_values_and_caps_result(self):
        payload = '{"ids_aprovados": [2, "1", true, 0, 2, 1]}'

        result = llm_triage._parse_ids_aprovados(payload, total_candidatos=3)

        self.assertEqual(result, [2, 0])

    async def test_returns_empty_when_azure_triage_is_not_configured(self):
        chamadas = [self._call("a", 180), self._call("b", 160)]

        with patch.multiple(
            llm_triage,
            AZURE_OPENAI_KEY="",
            AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
            AZURE_OPENAI_DEPLOYMENT="gpt-4o",
        ):
            result = await llm_triage.filtrar_ligacoes_com_llm(chamadas, "logistica", {})

        self.assertEqual(result, [])

    async def test_selects_llm_approved_calls_from_duration_sorted_candidates(self):
        chamadas = [
            self._call("short", 100),
            self._call("long", 300),
            self._call("medium", 200),
        ]
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"ids_aprovados": [0, 2]}')
                )
            ]
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client_factory = MagicMock(return_value=client)

        with patch.multiple(
            llm_triage,
            AZURE_OPENAI_KEY="key",
            AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
            AZURE_OPENAI_DEPLOYMENT="triage-deployment",
        ):
            with patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncAzureOpenAI=client_factory)}):
                result = await llm_triage.filtrar_ligacoes_com_llm(chamadas, "logistica", {})

        self.assertEqual([call["callId"] for call in result], ["long", "short"])
        client_factory.assert_called_once_with(
            azure_endpoint="https://example.openai.azure.com",
            api_key="key",
            api_version="2025-01-01-preview",
            timeout=llm_triage.LLM_TRIAGE_TIMEOUT_SECONDS,
        )
        _, kwargs = create.call_args
        self.assertEqual(kwargs["model"], "triage-deployment")
        self.assertEqual(kwargs["temperature"], 0)
        self.assertEqual(kwargs["max_tokens"], 200)
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})

    async def test_returns_empty_when_llm_call_fails(self):
        chamadas = [self._call("a", 180), self._call("b", 160)]
        create = AsyncMock(side_effect=RuntimeError("boom"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        client_factory = MagicMock(return_value=client)

        with patch.multiple(
            llm_triage,
            AZURE_OPENAI_KEY="key",
            AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
            AZURE_OPENAI_DEPLOYMENT="triage-deployment",
        ):
            with patch.dict(sys.modules, {"openai": SimpleNamespace(AsyncAzureOpenAI=client_factory)}):
                result = await llm_triage.filtrar_ligacoes_com_llm(chamadas, "logistica", {})

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
