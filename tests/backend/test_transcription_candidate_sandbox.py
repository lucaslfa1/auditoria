import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription_candidates import build_candidate
from core.transcription_cross_signals import compute_cross_signals, compute_numeric_overlap
from core.transcription_selector import (
    DECISION_ACCEPTED,
    DECISION_MANUAL_REVIEW,
    DECISION_NEEDS_REVIEW,
    DECISION_REJECTED,
    select_transcription_candidate,
)


def _segments(number: str = "123456", *, prefix: str = "") -> list[dict]:
    return [
        {
            "start": "00:00",
            "end": "00:08",
            "text": f"Operador: Bom dia, aqui e a central Opentech {prefix}".strip(),
        },
        {
            "start": "00:09",
            "end": "00:18",
            "text": f"Motorista: Estou parado no cliente aguardando descarga e a senha e {number}.",
        },
        {
            "start": "00:19",
            "end": "00:28",
            "text": "Operador: Perfeito, vou registrar a tratativa e retorno em duas horas.",
        },
    ]


class TestTranscriptionCandidateSandbox(unittest.TestCase):
    def test_numeric_overlap_reports_shared_and_missing_values(self):
        result = compute_numeric_overlap(
            "A senha informada foi 123456 e a placa ABC1234.",
            "A senha informada foi 123456 e a placa ABC9999.",
        )

        self.assertTrue(result["has_numeric_evidence"])
        self.assertIn("123456", result["shared"])
        self.assertIn("1234", result["first_only"])
        self.assertIn("9999", result["second_only"])
        self.assertLess(result["min_recall"], 1.0)

    def test_selector_accepts_fast_when_it_is_top_consistent_candidate(self):
        fast = build_candidate("fast", _segments(), deterministic_score=900)
        whisper = build_candidate("whisper", _segments(), deterministic_score=780)
        signals = compute_cross_signals([fast, whisper])

        decision = select_transcription_candidate([fast, whisper], cross_signals=signals)

        self.assertEqual(decision.status, DECISION_ACCEPTED)
        self.assertEqual(decision.reason, "accept_fast")
        self.assertEqual(decision.selected_candidate_id, "fast")
        self.assertIs(decision.selected_candidate, fast)
        self.assertEqual(decision.selected_candidate.segments, fast.segments)

    def test_selector_accepts_top_when_numeric_conflict_resolved_by_global_ranking(self):
        # v1.3.87: em vez de mandar pra manual review, o selector aceita o top
        # quando ha conflito numerico — o deterministic_score combina sinais
        # globais entao o top eh quem "transcreveu o resto melhor". O gate
        # humano em audits.status=awaiting_pair continua valendo.
        fast = build_candidate("fast", _segments("123456"), deterministic_score=900)
        whisper = build_candidate("whisper", _segments("999999"), deterministic_score=820)
        signals = compute_cross_signals([fast, whisper])

        decision = select_transcription_candidate([fast, whisper], cross_signals=signals)

        self.assertEqual(decision.status, DECISION_ACCEPTED)
        self.assertEqual(decision.reason, "divergencia_numerica_resolvida_pelo_ranking_global")
        self.assertIs(decision.selected_candidate, fast)
        self.assertEqual(decision.selected_candidate_id, "fast")
        self.assertIn("numeric_conflict_resolved_via_top_quality", decision.review_reasons)
        self.assertTrue(decision.gates.get("numeric_conflict_present"))
        self.assertTrue(decision.gates.get("numeric_conflict_resolved_via_global_ranking"))

    def test_selector_keeps_tied_candidates_out_of_automatic_audit(self):
        fast = build_candidate("fast", _segments(), deterministic_score=1000)
        diarize = build_candidate("gpt4o_diarize", _segments(), deterministic_score=950)
        signals = compute_cross_signals([fast, diarize])

        decision = select_transcription_candidate([fast, diarize], cross_signals=signals)

        self.assertEqual(decision.status, DECISION_NEEDS_REVIEW)
        self.assertEqual(decision.reason, "empate_requer_judge")
        self.assertEqual(decision.selected_candidate_id, "fast")
        self.assertIn("selector_tie_requires_judge", decision.review_reasons)

    def test_selector_rejects_when_no_usable_candidate_exists(self):
        errored = build_candidate(
            "fast",
            [],
            deterministic_score=0,
            status="errored",
            error="provider timeout",
        )

        decision = select_transcription_candidate([errored])

        self.assertEqual(decision.status, DECISION_REJECTED)
        self.assertEqual(decision.reason, "todos_candidatos_vazios")
        self.assertIsNone(decision.selected_candidate)

    def test_selector_requires_review_for_critical_alert_with_single_candidate(self):
        fast = build_candidate("fast", _segments(), deterministic_score=900)

        decision = select_transcription_candidate([fast], critical_alert=True)

        self.assertEqual(decision.status, DECISION_NEEDS_REVIEW)
        self.assertEqual(decision.reason, "alerta_critico_sem_confirmacao")
        self.assertEqual(decision.selected_candidate_id, "fast")

    def test_selector_rejects_when_audio_quality_below_threshold(self):
        fast = build_candidate("fast", _segments(), deterministic_score=900)

        decision = select_transcription_candidate([fast], audio_quality_score=0.20)

        self.assertEqual(decision.status, DECISION_REJECTED)
        self.assertEqual(decision.reason, "audio_inviavel")
        self.assertIn("audio_quality_below_minimum", decision.review_reasons)
        self.assertTrue(decision.gates.get("reject_audio_quality"))

    def test_selector_passes_when_audio_quality_above_threshold(self):
        fast = build_candidate("fast", _segments(), deterministic_score=900)

        decision = select_transcription_candidate([fast], audio_quality_score=0.50)

        self.assertEqual(decision.status, DECISION_ACCEPTED)
        self.assertEqual(decision.reason, "accept_fast")
        self.assertEqual(decision.gates.get("audio_quality_score"), 0.50)

    def test_selector_skips_gate_when_audio_quality_score_is_none(self):
        # Antes do v1.3.81 o gate era SEMPRE ignorado porque audit.py nunca passava o score.
        # Esse comportamento ainda existe quando o caller nao popula (graceful skip).
        fast = build_candidate("fast", _segments(), deterministic_score=900)

        decision = select_transcription_candidate([fast], audio_quality_score=None)

        self.assertEqual(decision.status, DECISION_ACCEPTED)
        self.assertNotIn("reject_audio_quality", decision.gates)


if __name__ == "__main__":
    unittest.main()
