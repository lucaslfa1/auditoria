import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription_quality import (
    assess_transcription_quality,
    attach_transcription_quality_gate,
)


class TestTranscriptionQualityGate(unittest.TestCase):
    def test_ready_transcription_keeps_review_off(self):
        segments = [
            {"start": "00:00", "end": "00:04", "text": "Operador: Bom dia, aqui e Ana da Opentech."},
            {"start": "00:05", "end": "00:08", "text": "Motorista: Bom dia, pode falar."},
            {"start": "00:09", "end": "00:14", "text": "Operador: O senhor pode confirmar a senha de seguranca?"},
            {"start": "00:15", "end": "00:18", "text": "Motorista: Oito cinco tres dois."},
            {"start": "00:19", "end": "00:25", "text": "Operador: Estou ligando sobre uma parada indevida no roteiro."},
            {"start": "00:26", "end": "00:32", "text": "Motorista: Parei para verificar um problema mecanico no caminhao."},
        ]
        audio_quality = {
            "diarization": {
                "score": 0.91,
                "swap_risk": "low",
            },
            "transcription_provider": {
                "selected_reason": "accepted",
                "attempts": [{"status": "accepted"}],
            },
        }

        result = assess_transcription_quality(segments, audio_quality)

        self.assertEqual(result["audit_readiness"], "ready")
        self.assertFalse(result["review_recommended"])
        self.assertGreaterEqual(result["score"], 0.74)

    def test_short_single_speaker_transcription_is_blocked(self):
        segments = [
            {"start": "00:00", "end": "00:02", "text": "Operador: Alo."},
        ]

        result = attach_transcription_quality_gate({}, segments)

        self.assertTrue(result["review_recommended"])
        self.assertEqual(result["review_priority"], "high")
        self.assertEqual(result["transcription_quality"]["audit_readiness"], "blocked")
        self.assertIn("transcricao:conteudo_transcrito_insuficiente", result["review_reasons"])

    def test_best_candidate_with_high_swap_risk_requires_review(self):
        segments = [
            {"start": "00:00", "end": "00:05", "text": "Operador: Bom dia, aqui e a central Opentech."},
            {"start": "00:06", "end": "00:12", "text": "Motorista: Estou parado no patio aguardando descarga."},
            {"start": "00:13", "end": "00:18", "text": "Operador: Vou verificar o alerta no sistema."},
            {"start": "00:19", "end": "00:24", "text": "Motorista: Tudo bem, fico no aguardo."},
        ]
        audio_quality = {
            "diarization": {"score": 0.38, "swap_risk": "high"},
            "transcription_provider": {"selected_reason": "best_candidate"},
        }

        result = attach_transcription_quality_gate(audio_quality, segments)

        self.assertTrue(result["review_recommended"])
        self.assertEqual(result["review_priority"], "high")
        self.assertEqual(result["transcription_quality"]["audit_readiness"], "review_required")
        self.assertIn("transcricao:risco_alto_de_troca_de_falante", result["review_reasons"])

    def test_hybrid_dual_insufficient_fallback_requires_review(self):
        segments = [
            {"start": "00:00", "end": "00:04", "text": "Operador: Bom dia, aqui e Ana da Opentech."},
            {"start": "00:05", "end": "00:08", "text": "Motorista: Bom dia, pode falar."},
            {"start": "00:09", "end": "00:14", "text": "Operador: O senhor pode confirmar a senha de seguranca?"},
            {"start": "00:15", "end": "00:18", "text": "Motorista: Oito cinco tres dois."},
            {"start": "00:19", "end": "00:25", "text": "Operador: Estou ligando sobre um botao de panico."},
            {"start": "00:26", "end": "00:32", "text": "Motorista: Foi acionado sem querer no posto."},
        ]
        audio_quality = {
            "diarization": {"score": 0.94, "swap_risk": "low"},
            "transcription_provider": {
                "selected_strategy": "gpt4o_diarize",
                "selected_reason": "accepted",
                "attempts": [
                    {
                        "strategy": "hybrid_dual",
                        "effective_strategy": "hybrid_dual",
                        "status": "insufficient",
                    },
                    {
                        "strategy": "gpt4o_diarize",
                        "effective_strategy": "gpt4o_diarize",
                        "status": "accepted",
                    },
                ],
            },
        }

        result = attach_transcription_quality_gate(audio_quality, segments)

        self.assertTrue(result["review_recommended"])
        self.assertEqual(result["review_priority"], "high")
        self.assertEqual(result["transcription_quality"]["audit_readiness"], "review_required")
        self.assertIn(
            "transcricao:fallback_de_transcricao_sem_consenso",
            result["review_reasons"],
        )

    def test_hybrid_dual_accepted_fast_fallback_requires_review(self):
        segments = [
            {"start": "00:00", "end": "00:04", "text": "Operador: Bom dia, aqui e Ana da Opentech."},
            {"start": "00:05", "end": "00:08", "text": "Motorista: Bom dia, pode falar."},
            {"start": "00:09", "end": "00:14", "text": "Operador: O senhor pode confirmar a senha de seguranca?"},
            {"start": "00:15", "end": "00:18", "text": "Motorista: Oito cinco tres dois."},
            {"start": "00:19", "end": "00:25", "text": "Operador: Estou ligando sobre um botao de panico."},
            {"start": "00:26", "end": "00:32", "text": "Motorista: Foi acionado sem querer no posto."},
        ]
        audio_quality = {
            "diarization": {"score": 0.94, "swap_risk": "low"},
            "transcription_provider": {
                "selected_strategy": "fast",
                "selected_reason": "accepted",
                "attempts": [
                    {
                        "strategy": "hybrid_dual",
                        "effective_strategy": "fast",
                        "status": "accepted",
                    },
                ],
            },
        }

        result = attach_transcription_quality_gate(audio_quality, segments)

        self.assertTrue(result["review_recommended"])
        self.assertEqual(result["review_priority"], "high")
        self.assertIn(
            "transcricao:fallback_de_transcricao_sem_consenso",
            result["review_reasons"],
        )


if __name__ == "__main__":
    unittest.main()
