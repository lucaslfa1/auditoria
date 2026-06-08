import os
import asyncio
import sys
import unittest
from pathlib import Path

# Add backend to path (3 levels up: tests/backend/file.py -> repo root -> backend/)
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))

import services


class TestSpeechSTT(unittest.TestCase):
    def test_speech_stt(self):
        if os.getenv("RUN_SPEECH_STT_INTEGRATION", "").strip().lower() not in {"1", "true", "yes", "on"}:
            self.skipTest("RUN_SPEECH_STT_INTEGRATION nao habilitado.")
        asyncio.run(self._run_speech_stt())

    async def _run_speech_stt(self):
        print("Testing speech-to-text provider...")

        audio_path = Path(__file__).resolve().parent / "fixtures" / "20260217114030490_Fabiula_de_Espindola_BAS_Voz.wav"

        if not audio_path.exists():
            self.skipTest(f"Sample audio not found at {audio_path}")

        with open(audio_path, "rb") as f:
            audio_content = f.read()

        original_ai_provider_priority = os.environ.get("AI_PROVIDER_PRIORITY")
        try:
            os.environ["AI_PROVIDER_PRIORITY"] = "primary"

            print(f"Transcribing {audio_path.name}...")
            transcription = await services.transcribe_audio(
                audio_file=audio_content,
                mime_type="audio/wav",
                operator_name="Teste",
                driver_name="Motorista"
            )

            print("\nTranscription Result:")
            for segment in transcription:
                print(f"[{segment['start']} - {segment['end']}] {segment['text']}")
            self.assertIsInstance(transcription, list)
            self.assertGreater(len(transcription), 0)

        except Exception as e:
            self.fail(f"Error during transcription: {e}")
        finally:
            if original_ai_provider_priority is None:
                os.environ.pop("AI_PROVIDER_PRIORITY", None)
            else:
                os.environ["AI_PROVIDER_PRIORITY"] = original_ai_provider_priority


if __name__ == "__main__":
    unittest.main()
