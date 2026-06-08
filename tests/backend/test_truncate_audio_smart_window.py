"""Smart windowing na triagem: truncate_audio deve pular o silencio/URA inicial
antes de pegar a janela, pra transcrever fala real (nao silencio de ringing/URA).

Regressao do bug onde chamadas com lead-in silencioso longo caiam em
alerta='desconhecido' porque a janela pegava so o silencio inicial.
"""
import array
import io
import math
import os
import unittest
from unittest.mock import patch
import wave

from core.classification import truncate_audio

SAMPLE_RATE = 16000


def _make_wav(silence_seconds: float, tone_seconds: float, freq: int = 440, amplitude: int = 8000) -> bytes:
    n_sil = int(silence_seconds * SAMPLE_RATE)
    n_tone = int(tone_seconds * SAMPLE_RATE)
    samples = array.array("h", [0] * n_sil)
    samples.extend(
        int(amplitude * math.sin(2 * math.pi * freq * n / SAMPLE_RATE)) for n in range(n_tone)
    )
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


def _rms(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        raw = w.readframes(w.getnframes())
    if not raw:
        return 0.0
    samples = array.array("h")
    samples.frombytes(raw)
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _duration_seconds(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getnframes() / float(w.getframerate())


class TestTruncateAudioSmartWindow(unittest.TestCase):
    def test_trims_leading_silence_so_window_captures_speech(self):
        # 8s de silencio (URA/ringing) + 6s de fala; janela de 4s.
        audio = _make_wav(silence_seconds=8, tone_seconds=6)
        out = truncate_audio(audio, max_duration_seconds=4, trim_leading_silence=True)
        # Sanity: realmente truncou (nao devolveu o audio inteiro por erro de ffmpeg).
        self.assertLessEqual(_duration_seconds(out), 5.0)
        # O fix: a janela captura a FALA, nao o silencio inicial.
        self.assertGreater(
            _rms(out), 1000.0,
            "janela de 4s deveria capturar a fala apos pular o silencio inicial",
        )

    def test_no_leading_silence_keeps_speech_from_start(self):
        # Regressao: chamada que comeca direto na fala nao pode ser prejudicada
        # (silenceremove nao deve cortar fala quando nao ha silencio inicial).
        audio = _make_wav(silence_seconds=0, tone_seconds=6)
        out = truncate_audio(audio, max_duration_seconds=4, trim_leading_silence=True)
        self.assertLessEqual(_duration_seconds(out), 5.0)
        self.assertGreater(_rms(out), 1000.0)

    def test_all_silence_does_not_crash(self):
        # Audio so silencio: o trim remove tudo -> saida curta/vazia, sem crashar.
        # O guard de transcricao curta a jusante trata isso como 'desconhecido'.
        audio = _make_wav(silence_seconds=6, tone_seconds=0)
        out = truncate_audio(audio, max_duration_seconds=4, trim_leading_silence=True)
        self.assertIsInstance(out, bytes)
        self.assertLess(_rms(out), 100.0)

    def test_canary_flag_off_by_default_does_not_trim(self):
        # Rollout seguro: sem a env CLASSIFICATION_TRIM_LEADING_SILENCE, o default
        # e NAO cortar -> a janela pega o silencio inicial (comportamento legado).
        env = dict(os.environ)
        env.pop("CLASSIFICATION_TRIM_LEADING_SILENCE", None)
        with patch.dict(os.environ, env, clear=True):
            audio = _make_wav(silence_seconds=8, tone_seconds=6)
            out = truncate_audio(audio, max_duration_seconds=4)
            self.assertLess(_rms(out), 100.0, "default OFF nao deveria cortar o silencio")

    def test_canary_flag_env_enables_trim(self):
        # Com a env ligada, corta o silencio inicial (sem precisar passar o param).
        with patch.dict(os.environ, {"CLASSIFICATION_TRIM_LEADING_SILENCE": "true"}, clear=False):
            audio = _make_wav(silence_seconds=8, tone_seconds=6)
            out = truncate_audio(audio, max_duration_seconds=4)
            self.assertGreater(_rms(out), 1000.0, "env=true deveria cortar o silencio")


if __name__ == "__main__":
    unittest.main()
