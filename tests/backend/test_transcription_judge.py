import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.transcription_candidates import build_candidate
from core.transcription_judge import JudgeOutcome, judge_tie_break


_FAKE_TEMPLATES = {
    "system": "test system",
    "user": (
        "alert={alert_id}/{alert_label} sector={sector_id} "
        "op={operator_label} drv={driver_label}\n"
        "A: provider={provider_a} id={candidate_id_a} score={score_a}\n{text_a}\n"
        "B: provider={provider_b} id={candidate_id_b} score={score_b}\n{text_b}"
    ),
}


def _make_response(content: str):
    """Constroi um mock da resposta do AzureOpenAI.chat.completions.create."""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


def _fake_client(json_payload: str):
    client = MagicMock()
    client.chat.completions.create.return_value = _make_response(json_payload)
    return client


def _segments(text: str, *, speaker: str = "Operador") -> list[dict]:
    return [
        {"start": "00:00", "end": "00:05", "text": f"{speaker}: {text}"},
    ]


def _fast_candidate() -> "object":
    return build_candidate(
        "fast",
        _segments("Bom dia, Jaqueline da Opentech, falando do gerenciamento."),
        candidate_id="fast_1",
        deterministic_score=14085,
        status="accepted",
    )


def _diarize_candidate_with_hallucination() -> "object":
    return build_candidate(
        "gpt4o_diarize",
        _segments(
            "Bom dia, Bruno, ja queria me dar o PINTEC aqui. Tem um Huawei Mate 2X11 P20 e P23."
        ),
        candidate_id="gpt4o_diarize_2",
        deterministic_score=14151,
        status="accepted",
    )


class TestTranscriptionJudge(unittest.TestCase):
    def setUp(self):
        self._patcher = patch(
            "core.transcription_judge._load_prompt_templates",
            return_value=_FAKE_TEMPLATES,
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_judge_picks_fast_when_diarize_hallucinates(self):
        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        client = _fake_client(
            '{"winner": "A", "winner_candidate_id": "fast_1", "confidence": 0.92, '
            '"reason": "B inventa modelos de celular Huawei Mate 2X11/P20/P23", '
            '"scores": {"fast_1": 0.95, "gpt4o_diarize_2": 0.3}, '
            '"hallucinations_a": [], '
            '"hallucinations_b": ["Huawei Mate 2X11", "P20", "P23", "PINTEC"]}'
        )

        outcome = judge_tie_break(
            fast,
            diarize,
            alert_id="UTI-PRIORITARIO-MOT",
            alert_label="Prioritario Motorista",
            sector_id="uti",
            client=client,
        )

        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.resolved)
        self.assertEqual(outcome.winner_label, "A")
        self.assertEqual(outcome.winner_candidate_id, "fast_1")
        self.assertAlmostEqual(outcome.confidence, 0.92, places=2)
        self.assertIn("Huawei", outcome.hallucinations["gpt4o_diarize_2"][0])
        client.chat.completions.create.assert_called_once()

    def test_judge_returns_none_when_response_is_malformed(self):
        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        client = _fake_client("not a valid json")

        outcome = judge_tie_break(fast, diarize, client=client)

        self.assertIsNone(outcome)

    def test_judge_returns_none_on_api_exception(self):
        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("timeout")

        outcome = judge_tie_break(fast, diarize, client=client)

        self.assertIsNone(outcome)

    def test_judge_returns_none_when_templates_missing(self):
        # Sobrescreve o patch ativo para devolver None
        with patch("core.transcription_judge._load_prompt_templates", return_value=None):
            outcome = judge_tie_break(
                _fast_candidate(),
                _diarize_candidate_with_hallucination(),
                client=_fake_client('{"winner": "A"}'),
            )
        self.assertIsNone(outcome)

    def test_judge_tie_result_marks_unresolved(self):
        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        client = _fake_client(
            '{"winner": "tie", "winner_candidate_id": "", "confidence": 0.5, '
            '"reason": "equivalent", "scores": {"fast_1": 0.5, "gpt4o_diarize_2": 0.5}}'
        )

        outcome = judge_tie_break(fast, diarize, client=client)

        self.assertIsNotNone(outcome)
        self.assertFalse(outcome.resolved)
        self.assertEqual(outcome.winner_label, "tie")
        self.assertIsNone(outcome.winner_candidate_id)

    def test_judge_skips_when_candidate_empty(self):
        empty = build_candidate(
            "fast",
            [],
            candidate_id="empty_1",
            deterministic_score=0,
            status="insufficient",
        )
        diarize = _diarize_candidate_with_hallucination()
        outcome = judge_tie_break(empty, diarize, client=_fake_client('{"winner":"B"}'))
        self.assertIsNone(outcome)

    def test_judge_picks_b_and_resolves_candidate_id_from_label(self):
        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        # Resposta sem winner_candidate_id explicito — deve derivar de winner=B
        client = _fake_client(
            '{"winner": "B", "winner_candidate_id": "", "confidence": 0.7, '
            '"reason": "B mais detalhado"}'
        )

        outcome = judge_tie_break(fast, diarize, client=client)

        self.assertIsNotNone(outcome)
        self.assertTrue(outcome.resolved)
        self.assertEqual(outcome.winner_candidate_id, "gpt4o_diarize_2")


class TestCandidateMetadataJudgeFields(unittest.TestCase):
    def test_judge_score_and_reason_injected_per_candidate(self):
        from core.transcription import _candidate_to_metadata

        fast = _fast_candidate()
        diarize = _diarize_candidate_with_hallucination()
        judge_results = {
            "fast_1": {"score": 0.95, "reason": "fiel ao audio"},
            "gpt4o_diarize_2": {"score": 0.3, "reason": ""},
        }

        fast_meta = _candidate_to_metadata(fast, cross_signals={}, judge_results=judge_results)
        diarize_meta = _candidate_to_metadata(diarize, cross_signals={}, judge_results=judge_results)

        self.assertEqual(fast_meta["judge_score"], 0.95)
        self.assertEqual(fast_meta["judge_reason"], "fiel ao audio")
        self.assertEqual(diarize_meta["judge_score"], 0.3)
        self.assertEqual(diarize_meta["judge_reason"], "")

    def test_judge_fields_absent_when_no_results(self):
        from core.transcription import _candidate_to_metadata

        fast = _fast_candidate()
        meta = _candidate_to_metadata(fast, cross_signals={})
        self.assertNotIn("judge_score", meta)
        self.assertNotIn("judge_reason", meta)


if __name__ == "__main__":
    unittest.main()
