import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.evaluation import parse_json_with_repair  # noqa: E402


class TestJsonRepair(unittest.TestCase):
    def test_parses_markdown_fenced_json_without_model_repair(self):
        payload = parse_json_with_repair(
            '```json\n{"summary":"ok","details":[]}\n```',
            '{"summary":"...","details":[]}',
            max_attempts=0,
        )

        self.assertEqual(payload, {"summary": "ok", "details": []})

    def test_extracts_first_json_object_from_wrapped_text(self):
        payload = parse_json_with_repair(
            'Segue o JSON solicitado:\n{"summary":"ok","details":[{"criterionId":"a"}]}\nObrigado.',
            '{"summary":"...","details":[]}',
            max_attempts=0,
        )

        self.assertEqual(payload["summary"], "ok")
        self.assertEqual(payload["details"][0]["criterionId"], "a")

    def test_uses_injected_azure_client_for_model_repair(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"summary":"fixed","details":[]}'))]
        )

        payload = parse_json_with_repair(
            '{"summary":',
            '{"summary":"...","details":[]}',
            max_attempts=1,
            azure_client=mock_client,
            ai_provider_priority="azure",
            azure_openai_key="key",
            azure_openai_endpoint="https://example.openai.azure.com",
            azure_openai_deployment="gpt-4o",
        )

        self.assertEqual(payload["summary"], "fixed")
        mock_client.chat.completions.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
