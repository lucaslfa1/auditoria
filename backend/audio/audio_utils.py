from __future__ import annotations
"""
Audio Utilities Module

Audio format conversion (WAV, MP3) with ffmpeg/pydub and timestamp formatting.
"""


import io
import logging

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:06.3f}"


def convert_audio_to_wav(audio_file: bytes, force_mono: bool = False) -> bytes:
    from pydub import AudioSegment
    from pydub.effects import normalize
    import io

    try:
        audio = AudioSegment.from_file(io.BytesIO(audio_file))
    except Exception as e:
        logger.warning("Pydub falhou na abertura automatica, tentando forcar alaw: %s", e)
        try:
            # Fallback para Huawei A-law (G.711)
            audio = AudioSegment.from_file(io.BytesIO(audio_file), format="wav", codec="pcm_alaw")
        except Exception as e2:
            logger.error("Falha total ao abrir audio para conversao: %s", e2)
            raise e2

    target_channels = 1 if (force_mono or audio.channels == 1) else min(audio.channels, 2)
    audio = normalize(audio.set_channels(target_channels).set_frame_rate(16000), headroom=0.5)

    out_buffer = io.BytesIO()
    audio.export(out_buffer, format="wav", parameters=["-threads", "1"])
    return out_buffer.getvalue()


def convert_audio_to_mp3(audio_file: bytes, source_mime_type: str = "audio/wav") -> bytes:
    """Transcodifica audio para MP3 preservando inteligibilidade para Azure STT."""
    from pydub import AudioSegment

    audio = AudioSegment.from_file(io.BytesIO(audio_file))
    audio = audio.set_channels(1).set_frame_rate(16000)

    out_buffer = io.BytesIO()
    audio.export(
        out_buffer,
        format="mp3",
        codec="libmp3lame",
        bitrate="128k",
        parameters=["-threads", "1"],
    )
    return out_buffer.getvalue()
