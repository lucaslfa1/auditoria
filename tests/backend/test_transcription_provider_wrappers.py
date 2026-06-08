import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import services
import core.transcription
from transcription_providers.common import build_azure_domain_phrases, build_transcription_domain_prompt


class TestTranscriptionProviderWrappers(unittest.TestCase):
    def test_transcribe_audio_azure_delegates_to_adapter(self):
        with patch("core.transcription.run_azure_transcription", return_value=[{"text": "ok"}]) as mocked:
            result = services.transcribe_audio_azure(
                b"audio",
                "Operador",
                "Motorista",
                operator_name="Ana",
                driver_name="Carlos",
                mime_type="audio/wav",
                endpoint_override="https://example.test/openai/deployments/whisper/audio/transcriptions",
                api_key_override="secret",
                sector_id="bas",
            )

        self.assertEqual(result, [{"text": "ok"}])
        args, kwargs = mocked.call_args
        self.assertEqual(args[:5], (b"audio", "Operador", "Motorista", "Ana", "Carlos"))
        self.assertEqual(kwargs["mime_type"], "audio/wav")
        self.assertEqual(kwargs["endpoint_override"], "https://example.test/openai/deployments/whisper/audio/transcriptions")
        self.assertEqual(kwargs["api_key_override"], "secret")
        self.assertEqual(kwargs["sector_id"], "bas")
        self.assertIn("dependencies", kwargs)

    def test_resolve_whisper_prompt_uses_sector_prompt_repository(self):
        with patch("repositories.ai_prompts.get_whisper_prompt_for_sector", return_value="Prompt BAS") as mocked:
            result = core.transcription._resolve_whisper_prompt("bas")

        self.assertEqual(result, "Prompt BAS")
        self.assertEqual(mocked.call_args.args[1], "bas")

    def test_domain_phrases_include_sentinel_vocabulary(self):
        phrases = build_azure_domain_phrases({"corrections": []}, "Ana Silva", "Carlos Souza")

        for expected in ("CEAGESP", "B.O.", "gerenciadora de risco", "jammer", "Base de Sinistros"):
            self.assertIn(expected, phrases)
        self.assertIn("Ana", phrases)
        self.assertIn("Carlos", phrases)

    def test_domain_prompt_preserves_numbers_and_domain_terms(self):
        prompt = build_transcription_domain_prompt({"corrections": []}, "Ana", "Carlos")

        self.assertIn("preserve numeros", prompt)
        self.assertIn("Opentech", prompt)
        self.assertIn("CEAGESP", prompt)

    def test_transcribe_audio_gpt4o_diarize_delegates_to_adapter(self):
        with patch("core.transcription.run_gpt4o_diarize_transcription", return_value=[{"text": "ok"}]) as mocked:
            result = services.transcribe_audio_gpt4o_diarize(
                b"audio",
                "audio/wav",
                "Operador",
                "Motorista",
                endpoint_override="https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01",
                api_key_override="secret",
                operator_name="Ana",
                driver_name="Carlos",
            )

        self.assertEqual(result, [{"text": "ok"}])
        args, kwargs = mocked.call_args
        self.assertEqual(args[:4], (b"audio", "audio/wav", "Operador", "Motorista"))
        self.assertEqual(kwargs["endpoint"], "https://example.test/openai/deployments/gpt/audio/transcriptions?api-version=2024-06-01")
        self.assertEqual(kwargs["api_key"], "secret")
        self.assertEqual(kwargs["auth_mode"], "api_key")
        self.assertEqual(kwargs["model_name"], "gpt-4o-transcribe-diarize")
        self.assertEqual(kwargs["operator_name"], "Ana")
        self.assertEqual(kwargs["driver_name"], "Carlos")
        self.assertIn("dependencies", kwargs)


if __name__ == "__main__":
    unittest.main()
