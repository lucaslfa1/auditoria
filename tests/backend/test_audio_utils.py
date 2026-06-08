import io
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from audio.audio_utils import convert_audio_to_mp3, convert_audio_to_wav


class _FakeAudioSegment:
    def __init__(self):
        self.channels = None
        self.frame_rate = None
        self.export_args = None

    def set_channels(self, channels):
        self.channels = channels
        return self

    def set_frame_rate(self, frame_rate):
        self.frame_rate = frame_rate
        return self

    def export(self, out_buffer, **kwargs):
        self.export_args = kwargs
        out_buffer.write(b"mp3")


class TestAudioUtils(unittest.TestCase):
    def _silent_wav(self, *, channels: int = 1) -> bytes:
        from pydub import AudioSegment

        audio = AudioSegment.silent(duration=250, frame_rate=8000).set_channels(channels)
        out_buffer = io.BytesIO()
        audio.export(out_buffer, format="wav")
        return out_buffer.getvalue()

    def test_convert_audio_to_wav_uses_in_memory_payload(self):
        converted = convert_audio_to_wav(self._silent_wav(channels=2))

        self.assertTrue(converted.startswith(b"RIFF"))
        self.assertIn(b"WAVE", converted[:16])

    def test_convert_audio_to_mp3_uses_in_memory_payload(self):
        from pydub.utils import which

        if not which("ffmpeg"):
            self.skipTest("ffmpeg not available")

        converted = convert_audio_to_mp3(self._silent_wav(), source_mime_type="audio/wav")

        self.assertGreater(len(converted), 0)
        self.assertTrue(converted.startswith(b"ID3") or converted[:1] == b"\xff")

    def test_convert_audio_to_mp3_uses_speech_quality_bitrate(self):
        segment = _FakeAudioSegment()
        fake_pydub = types.SimpleNamespace(
            AudioSegment=types.SimpleNamespace(from_file=lambda _payload: segment)
        )

        with patch.dict(sys.modules, {"pydub": fake_pydub}):
            converted = convert_audio_to_mp3(b"wav")

        self.assertEqual(converted, b"mp3")
        self.assertEqual(segment.channels, 1)
        self.assertEqual(segment.frame_rate, 16000)
        self.assertEqual(segment.export_args["format"], "mp3")
        self.assertEqual(segment.export_args["codec"], "libmp3lame")
        self.assertEqual(segment.export_args["bitrate"], "128k")


if __name__ == "__main__":
    unittest.main()
