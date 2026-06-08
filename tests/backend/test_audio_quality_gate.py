import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from audio.diarization_quality import build_diarization_quality


_SEGMENTS = [
    {
        "start": "00:00",
        "end": "00:05",
        "text": "Operador: Bom dia, aqui e a central Opentech.",
        "speaker_source_ids": [1],
        "speaker_risk": "low",
    },
    {
        "start": "00:06",
        "end": "00:10",
        "text": "Motorista: Estou parado no cliente aguardando descarga.",
        "speaker_source_ids": [0],
        "speaker_risk": "low",
    },
]


class TestBuildDiarizationQualityNoDefaults(unittest.TestCase):
    """Garante que build_diarization_quality NAO preenche mais score/quality top-level
    com defaults enganosos (1.0 / 'desconhecida'). Score top-level deve vir do upstream
    (QualityAnalyzer em audit.py)."""

    def test_top_level_score_absent_when_audio_quality_is_none(self):
        result = build_diarization_quality(_SEGMENTS)
        self.assertNotIn("score", result)
        self.assertNotIn("quality", result)
        self.assertIn("diarization", result)
        self.assertIsNotNone(result["diarization"]["score"])

    def test_top_level_score_preserved_when_audio_quality_provides_it(self):
        result = build_diarization_quality(
            _SEGMENTS,
            {"score": 0.78, "quality": "regular", "notes": ["Volume ligeiramente baixo"]},
        )
        self.assertEqual(result["score"], 0.78)
        self.assertEqual(result["quality"], "regular")
        self.assertEqual(result["notes"], ["Volume ligeiramente baixo"])
        # Diarization continua sendo calculado e nao colide com top-level
        self.assertIn("diarization", result)
        self.assertNotEqual(result["score"], result["diarization"]["score"])

    def test_top_level_score_none_passes_through(self):
        # Quando o caller (audit.py) NAO conseguiu calcular score (QualityAnalyzer falhou),
        # passa explicitamente score=None. build_diarization_quality deve preservar None,
        # nunca substituir por 1.0.
        result = build_diarization_quality(
            _SEGMENTS,
            {"score": None, "quality": None},
        )
        self.assertIsNone(result["score"])
        self.assertIsNone(result["quality"])


class TestAuditAnalyzeRawAudioQuality(unittest.TestCase):
    """Garante que o wrapper _analyze_raw_audio_quality em core/audit.py degrade graciosamente
    quando QualityAnalyzer.analyze quebra (pydub ausente, audio corrompido, etc.)."""

    def test_returns_dict_with_score_when_analyzer_works(self):
        from core.audit import _analyze_raw_audio_quality

        fake = {"score": 0.85, "quality": "boa", "notes": [], "details": {"sample_rate": 16000}}
        with patch("core.audit.QualityAnalyzer") as mock_cls:
            mock_cls.return_value.analyze.return_value = fake
            result = _analyze_raw_audio_quality(b"any-bytes")
        self.assertEqual(result, fake)

    def test_returns_safe_fallback_when_analyzer_raises(self):
        from core.audit import _analyze_raw_audio_quality

        with patch("core.audit.QualityAnalyzer") as mock_cls:
            mock_cls.return_value.analyze.side_effect = RuntimeError("pydub corrompido")
            result = _analyze_raw_audio_quality(b"corrupt")

        self.assertIsNone(result.get("score"))
        self.assertEqual(result.get("quality"), "desconhecida")
        self.assertTrue(any("falha_quality_analyzer" in str(n) for n in result.get("notes", [])))


if __name__ == "__main__":
    unittest.main()
