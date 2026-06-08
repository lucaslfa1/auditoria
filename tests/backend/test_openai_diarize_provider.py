import os
import sys
import unittest
from unittest.mock import patch

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from transcription_providers.openai_diarize import (
    GPT4oDiarizeTranscriptionDependencies,
    transcribe_audio_gpt4o_diarize,
)


class _FakeResponse:
    def __init__(self, *, ok: bool, payload: dict | None = None, status_code: int = 200, text: str = ""):
        self.ok = ok
        self._payload = payload or {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.ok:
            return None
        error = requests.HTTPError(f"{self.status_code} error")
        error.response = self
        raise error


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        self.posts.append((args, kwargs))
        if not self._responses:
            raise AssertionError("No fake responses remaining")
        return self._responses.pop(0)


class TestOpenAIDiarizeProvider(unittest.TestCase):
    def _dependencies(self):
        return GPT4oDiarizeTranscriptionDependencies(
            guess_audio_filename=lambda mime: "audio.wav",
            get_transcription_timeout_seconds=lambda: 30,
            get_retry_count=lambda: 1,
            get_retry_delay_seconds=lambda: 0.0,
            build_domain_prompt=lambda operator_name, driver_name: (
                f"Opentech, CEAGESP, senha. Operador={operator_name}; Motorista={driver_name}"
            ),
            normalize_company_name=lambda text: text,
            filter_hallucinations=lambda text: text,
            remove_emojis=lambda text: text,
            deduplicate_transcription_segments=lambda segments: segments,
            sleep=lambda seconds: None,
        )

    def test_transcribe_audio_gpt4o_diarize_retries_once_after_server_error(self):
        success_payload = {
            "segments": [
                {"speaker": "speaker_1", "start": 0.0, "end": 2.0, "text": "Bom dia, aqui e a central."},
                {"speaker": "speaker_2", "start": 2.1, "end": 4.0, "text": "Estou no cliente aguardando."},
            ]
        }
        fake_session = _FakeSession(
            [
                _FakeResponse(ok=False, status_code=500, text="server_error"),
                _FakeResponse(ok=True, payload=success_payload),
            ]
        )

        with (
            patch(
                "transcription_providers.openai_diarize.create_requests_session",
                return_value=fake_session,
            ),
            patch(
                "transcription_providers.openai_diarize.finalize_speaker_segments",
                return_value=[{"start": "00:00", "end": "00:04", "text": "Operador: teste"}],
            ),
        ):
            result = transcribe_audio_gpt4o_diarize(
                b"audio",
                "audio/wav",
                "Operador",
                "Motorista",
                endpoint="https://example.test/openai/deployments/gpt/audio/transcriptions",
                api_key="secret",
                operator_name="Ana",
                driver_name="Carlos",
                dependencies=self._dependencies(),
            )

        self.assertEqual(result, [{"start": "00:00", "end": "00:04", "text": "Operador: teste"}])
        self.assertIn("prompt", fake_session.posts[-1][1]["data"])
        self.assertIn("CEAGESP", fake_session.posts[-1][1]["data"]["prompt"])

    def test_transcribe_audio_gpt4o_diarize_retries_without_prompt_when_unsupported(self):
        success_payload = {
            "segments": [
                {"speaker": "speaker_1", "start": 0.0, "end": 2.0, "text": "Bom dia, aqui e a central."},
                {"speaker": "speaker_2", "start": 2.1, "end": 4.0, "text": "Estou no cliente aguardando."},
            ]
        }
        fake_session = _FakeSession(
            [
                _FakeResponse(ok=False, status_code=400, text="Unrecognized request argument: prompt"),
                _FakeResponse(ok=True, payload=success_payload),
            ]
        )

        with (
            patch(
                "transcription_providers.openai_diarize.create_requests_session",
                return_value=fake_session,
            ),
            patch(
                "transcription_providers.openai_diarize.finalize_speaker_segments",
                return_value=[{"start": "00:00", "end": "00:04", "text": "Operador: teste"}],
            ),
        ):
            result = transcribe_audio_gpt4o_diarize(
                b"audio",
                "audio/wav",
                "Operador",
                "Motorista",
                endpoint="https://example.test/openai/deployments/gpt/audio/transcriptions",
                api_key="secret",
                dependencies=self._dependencies(),
            )

        self.assertEqual(result, [{"start": "00:00", "end": "00:04", "text": "Operador: teste"}])
        self.assertIn("prompt", fake_session.posts[0][1]["data"])
        self.assertNotIn("prompt", fake_session.posts[1][1]["data"])


if __name__ == "__main__":
    unittest.main()
