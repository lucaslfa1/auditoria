"""Utilidades de áudio da triagem (extraídas de `core.classification`).

Corte da janela de triagem via ffmpeg (`truncate_audio`), flag canário de
remoção do silêncio/URA inicial e resolução de MIME type por extensão.
Movido sem mudança de comportamento; `core.classification` reexporta tudo.
"""

import os
import subprocess
import tempfile

MAX_AUDIO_DURATION_SECONDS = 60


def get_mime_type(filename: str) -> str:
    """MIME type pela extensão do arquivo (default 'audio/wav' p/ desconhecidos)."""
    ext = os.path.splitext(filename)[1].lower()
    mime_map = {
        '.wav': 'audio/wav',
        '.mp3': 'audio/mp3',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/m4a',
        '.webm': 'audio/webm',
        '.pdf': 'application/pdf',
    }
    return mime_map.get(ext, 'audio/wav')

def _trim_leading_silence_enabled() -> bool:
    """Canary flag: pular o silencio/URA inicial na janela de triagem.

    Default OFF para rollout seguro no Cloud Run — habilitar com
    CLASSIFICATION_TRIM_LEADING_SILENCE=true e desligar na hora em caso de
    regressao, sem redeploy.
    """
    raw = os.getenv("CLASSIFICATION_TRIM_LEADING_SILENCE")
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def truncate_audio(
    audio_bytes: bytes,
    max_duration_seconds: int = MAX_AUDIO_DURATION_SECONDS,
    *,
    trim_leading_silence: bool | None = None,
) -> bytes:
    """Trunca o áudio (ffmpeg → WAV mono 16 kHz) para a janela de triagem.

    Limita o custo de transcrição: a triagem só precisa do começo da conversa.
    Com `trim_leading_silence` (canário, default OFF) remove o silêncio/URA
    inicial antes de cortar. Em qualquer falha do ffmpeg, devolve os bytes
    ORIGINAIS (nunca quebra o fluxo por causa do corte).
    """
    if trim_leading_silence is None:
        trim_leading_silence = _trim_leading_silence_enabled()
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_path = os.path.join(tmp_dir, "input.bin")
            wav_path = os.path.join(tmp_dir, "output.wav")
            with open(in_path, "wb") as f:
                f.write(audio_bytes)
            cmd = ["ffmpeg", "-y", "-threads", "1", "-i", in_path, "-ac", "1", "-ar", "16000"]
            if trim_leading_silence:
                # Pula o silencio/URA inicial antes da janela (-t): chamadas Huawei
                # com lead-in silencioso longo transcreviam so o silencio e caiam em
                # alerta='desconhecido'. silenceremove corta apenas o primeiro periodo
                # de silencio (start_periods=1), preservando a conversa.
                cmd += ["-af", "silenceremove=start_periods=1:start_threshold=-45dB"]
            cmd += ["-t", str(max_duration_seconds), "-f", "wav", wav_path]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            with open(wav_path, "rb") as f:
                return f.read()
    except Exception:
        return audio_bytes
