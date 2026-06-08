import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.quality_observability import (
    build_internal_quality_trace,
    summarize_transcription_metadata,
)


class _Criterion:
    def __init__(self, criterion_id: str):
        self.id = criterion_id


class _Detail:
    def __init__(self, status: str):
        self.status = status


class _Result:
    def __init__(self):
        self.details = [_Detail("pass"), _Detail("fail"), _Detail("partial")]
        self.score = 7.5
        self.maxPossibleScore = 10.0
        self.summary = "Resumo interno"
        self.fatal_flags = ["abandono_ligacao"]


class TestQualityObservability(unittest.TestCase):
    def test_summarize_transcription_metadata_counts_attempts(self):
        payload = summarize_transcription_metadata(
            {
                "selected_strategy": "gpt4o_diarize",
                "selected_provider": "Azure GPT-4o diarize",
                "selected_reason": "best_score",
                "attempts": [
                    {"strategy": "fast", "provider": "Azure Fast", "status": "rejected", "score": 10},
                    {"strategy": "gpt4o_diarize", "provider": "Azure GPT-4o diarize", "status": "accepted", "score": 22},
                ],
            }
        )
        self.assertEqual(payload["attempt_count"], 2)
        self.assertEqual(payload["selected_strategy"], "gpt4o_diarize")
        self.assertEqual(payload["attempts"][1]["status"], "accepted")

    def test_build_internal_quality_trace_includes_missing_criteria(self):
        trace = build_internal_quality_trace(
            input_hash="abc123",
            source_type="audio",
            sector_id="mondelez",
            criteria_list=[_Criterion("c1"), _Criterion("c2")],
            transcription_metadata={"selected_provider": "Azure Fast"},
            evaluation={"details": [{"criterionId": "c1", "status": "pass", "comment": "ok"}]},
            result=_Result(),
            stage="process_audit_with_ai",
        )
        self.assertEqual(trace["evaluation"]["missing_criteria_count"], 1)
        self.assertEqual(trace["result"]["detail_status_counts"]["fail"], 2)
        self.assertEqual(trace["transcription"]["selected_provider"], "Azure Fast")



    def test_summarize_audio_quality_invalid_input(self):
        from core.quality_observability import summarize_audio_quality
        self.assertEqual(summarize_audio_quality(None), {})
        self.assertEqual(summarize_audio_quality([]), {})
        self.assertEqual(summarize_audio_quality("test"), {})
        self.assertEqual(summarize_audio_quality(123), {})
    def test_summarize_audio_quality_empty_dict(self):
        from core.quality_observability import summarize_audio_quality
        result = summarize_audio_quality({})
        self.assertEqual(result["review_recommended"], False)
        self.assertEqual(result["review_priority"], "")
        self.assertEqual(result["diarization"], {})
        self.assertEqual(result["transcription_provider"], {})
    def test_summarize_audio_quality_with_diarization(self):
        from core.quality_observability import summarize_audio_quality
        payload = {
            "diarization": {
                "score": "8.5",
                "swap_risk": "low",
                "raw_speaker_count": 2,
                "human_segment_count": "5",
                "telephony_segment_count": 3
            }
        }
        result = summarize_audio_quality(payload)
        self.assertEqual(result["diarization"]["score"], 8.5)
        self.assertEqual(result["diarization"]["swap_risk"], "low")
        self.assertEqual(result["diarization"]["raw_speaker_count"], 2)
        self.assertEqual(result["diarization"]["human_segment_count"], 5)
        self.assertEqual(result["diarization"]["telephony_segment_count"], 3)
    def test_summarize_audio_quality_with_transcription_provider(self):
        from core.quality_observability import summarize_audio_quality
        payload = {
            "transcription_provider": {
                "selected_strategy": "fast",
                "selected_provider": "Azure Fast",
                "selected_reason": "default"
            }
        }
        result = summarize_audio_quality(payload)
        self.assertEqual(result["transcription_provider"]["selected_strategy"], "fast")
        self.assertEqual(result["transcription_provider"]["selected_provider"], "Azure Fast")
        self.assertEqual(result["transcription_provider"]["selected_reason"], "default")
    def test_summarize_audio_quality_full(self):
        from core.quality_observability import summarize_audio_quality
        payload = {
            "review_recommended": True,
            "review_priority": "high",
            "diarization": {
                "score": 9.0,
                "swap_risk": "none",
                "raw_speaker_count": 1,
                "human_segment_count": 10,
                "telephony_segment_count": 0
            },
            "transcription_provider": {
                "selected_strategy": "accurate",
                "selected_provider": "OpenAI",
                "selected_reason": "best",
                "attempts": [
                    {"strategy": "accurate", "provider": "OpenAI", "status": "accepted", "score": 10}
                ]
            }
        }
        result = summarize_audio_quality(payload)
        self.assertEqual(result["review_recommended"], True)
        self.assertEqual(result["review_priority"], "high")
        self.assertEqual(result["diarization"]["score"], 9.0)
        self.assertEqual(result["diarization"]["swap_risk"], "none")
        self.assertEqual(result["diarization"]["raw_speaker_count"], 1)
        self.assertEqual(result["diarization"]["human_segment_count"], 10)
        self.assertEqual(result["diarization"]["telephony_segment_count"], 0)
        self.assertEqual(result["transcription_provider"]["selected_strategy"], "accurate")
        self.assertEqual(result["transcription_provider"]["selected_provider"], "OpenAI")
        self.assertEqual(result["transcription_provider"]["attempt_count"], 1)

if __name__ == "__main__":
    unittest.main()
