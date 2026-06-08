"""
QualityAnalyzer - Analise de qualidade de audio antes da transcricao.

Baseado no conceito do Sentinel (sentinel-cortex/services/quality_analyzer.py),
adaptado para o contexto de auditoria de ligacoes telefonicas.

Fornece score de confianca (0.0 a 1.0) e notas explicativas para que
o auditor saiba se a transcricao sera confiavel.
"""

from pydub import AudioSegment
import io
import logging

logger = logging.getLogger(__name__)


class QualityAnalyzer:

    def analyze(self, audio_bytes: bytes) -> dict:
        """
        Analisa qualidade do audio e retorna score + notas + detalhes.

        Returns:
            {
                "score": 0.0-1.0,
                "notes": ["nota1", "nota2"],
                "details": { volume, silence_ratio, duration, ... }
            }
        """
        notes = []
        score = 1.0

        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes))

            # 1. Volume medio (dBFS)
            if audio.dBFS < -40:
                notes.append("Volume muito baixo - possivel perda de fala")
                score -= 0.25
            elif audio.dBFS < -30:
                notes.append("Volume abaixo do ideal")
                score -= 0.15
            elif audio.dBFS < -20:
                notes.append("Volume ligeiramente baixo")
                score -= 0.05

            # 2. Duracao
            duration_sec = len(audio) / 1000
            duration_min = duration_sec / 60
            if duration_sec < 15:
                notes.append("Audio muito curto - pode nao conter conteudo suficiente")
                score -= 0.15
            elif duration_min > 30:
                notes.append(f"Audio muito longo ({duration_min:.0f} min)")

            # 3. Proporcao de silencio
            silent_ratio = self._detect_silence_ratio(audio)
            if silent_ratio > 0.7:
                notes.append(f"{silent_ratio*100:.0f}% de silencio - possivel espera/URA longa")
                score -= 0.25
            elif silent_ratio > 0.5:
                notes.append(f"{silent_ratio*100:.0f}% de silencio detectado")
                score -= 0.10

            # 4. Clipping (distorcao)
            if audio.max_dBFS > -0.5:
                notes.append("Possivel distorcao por volume excessivo (clipping)")
                score -= 0.15
            elif audio.max_dBFS > -1.0:
                notes.append("Picos de volume proximos ao limite")
                score -= 0.05

            # 5. Taxa de amostragem
            if audio.frame_rate < 8000:
                notes.append("Taxa de amostragem muito baixa - qualidade comprometida")
                score -= 0.15
            elif audio.frame_rate < 16000:
                notes.append("Taxa de amostragem baixa - qualidade de transcricao pode ser afetada")
                score -= 0.05

            # 6. Codec de telefonia (estimativa por tamanho vs duracao)
            if duration_sec > 0:
                bitrate_kbps = (len(audio_bytes) * 8) / duration_sec / 1000
                if bitrate_kbps < 16:
                    notes.append(f"Codec muito comprimido (~{bitrate_kbps:.0f}kbps) - tipico de telefonia")
                    score -= 0.10

            if not notes:
                notes.append("Qualidade de audio adequada para transcricao")

            # Classificacao textual
            if score >= 0.8:
                quality_label = "boa"
            elif score >= 0.6:
                quality_label = "regular"
            elif score >= 0.4:
                quality_label = "baixa"
            else:
                quality_label = "muito_baixa"

            return {
                "score": round(max(0.0, min(1.0, score)), 2),
                "quality": quality_label,
                "notes": notes,
                "details": {
                    "duration_seconds": round(duration_sec, 2),
                    "average_dbfs": round(audio.dBFS, 2),
                    "max_dbfs": round(audio.max_dBFS, 2),
                    "sample_rate": audio.frame_rate,
                    "channels": audio.channels,
                    "silence_ratio": round(silent_ratio, 2),
                    "bitrate_kbps": round((len(audio_bytes) * 8) / max(duration_sec, 0.1) / 1000, 1)
                }
            }

        except Exception as e:
            logger.error(f"Erro ao analisar qualidade de audio: {e}")
            return {
                "score": 0.5,
                "quality": "desconhecida",
                "notes": [f"Nao foi possivel analisar qualidade: {str(e)}"],
                "details": {}
            }

    def _detect_silence_ratio(self, audio: AudioSegment) -> float:
        chunk_ms = 500
        total_chunks = len(audio) // chunk_ms
        if total_chunks == 0:
            return 0.0

        silence_threshold = -40
        silent_chunks = 0
        for i in range(total_chunks):
            chunk = audio[i * chunk_ms:(i + 1) * chunk_ms]
            if chunk.dBFS < silence_threshold:
                silent_chunks += 1

        return silent_chunks / total_chunks
