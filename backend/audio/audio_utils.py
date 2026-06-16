"""
Audio Utilities Module

Utilitários de áudio do pipeline de transcrição: conversão de formato (WAV/MP3)
via pydub/ffmpeg e formatação de timestamp.

Sem custo de API (só CPU/processo ffmpeg local; nada de Azure). A transcrição
paga acontece downstream, consumindo o áudio normalizado produzido aqui.
"""
from __future__ import annotations


import io
import logging

logger = logging.getLogger(__name__)


def format_timestamp(seconds: float) -> str:
    """Formata segundos como "MM:SS.mmm" (minutos zero-padded, segundos com 3 casas).

    Ex.: 75.5 -> "01:15.500". Sem efeitos colaterais.
    """
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:06.3f}"


def convert_audio_to_wav(audio_file: bytes, force_mono: bool = False) -> bytes:
    """Converte bytes de áudio para WAV PCM 16 kHz normalizado.

    Abre o áudio com pydub (detecção automática de formato); em falha, tenta
    forçar o codec A-law (G.711), comum em áudio Huawei. Reamostra para 16 kHz,
    ajusta canais (mono se `force_mono` ou se já era mono; senão até 2 canais) e
    normaliza o volume (headroom=0.5).

    Params:
        audio_file: conteúdo binário do áudio de origem.
        force_mono: força saída mono mesmo se a origem for estéreo.

    Retorna os bytes do WAV resultante. Levanta exceção se nem a abertura
    automática nem o fallback A-law conseguirem decodificar o áudio.
    Efeito colateral: invoca ffmpeg via pydub (subprocesso local); sem rede.
    """
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
    """Transcodifica audio para MP3 preservando inteligibilidade para Azure STT.

    Reamostra para mono 16 kHz e exporta em MP3 (libmp3lame, 128 kbps). O
    parâmetro `source_mime_type` é informativo e não altera a decodificação
    (pydub detecta o formato pelos bytes). Retorna os bytes do MP3.
    Efeito colateral: invoca ffmpeg via pydub (subprocesso local); sem rede.
    """
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
