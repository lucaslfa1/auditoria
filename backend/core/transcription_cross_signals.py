from __future__ import annotations

import re
from typing import Any

from audio.diarization_quality import (
    extract_segment_speaker,
    normalize_lookup_text,
    parse_timestamp_seconds,
)

from core.transcription_candidates import TranscriptionCandidate, segments_to_text


_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
_NUMERIC_RE = re.compile(r"(?:\d[\s.\-:/]*){3,}", flags=re.UNICODE)


def _tokens(text: str) -> set[str]:
    normalized = normalize_lookup_text(text)
    return {token for token in _TOKEN_RE.findall(normalized) if token}


def _numeric_tokens(text: str) -> set[str]:
    numbers: set[str] = set()
    for match in _NUMERIC_RE.finditer(text or ""):
        digits = re.sub(r"\D+", "", match.group(0))
        if len(digits) >= 3:
            numbers.add(digits)
    return numbers


def compute_token_jaccard(first_text: str, second_text: str) -> float:
    first = _tokens(first_text)
    second = _tokens(second_text)
    if not first and not second:
        return 1.0
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def compute_numeric_overlap(first_text: str, second_text: str) -> dict[str, Any]:
    first = _numeric_tokens(first_text)
    second = _numeric_tokens(second_text)
    if not first and not second:
        return {
            "overlap_ratio": 1.0,
            "min_recall": 1.0,
            "first_only": [],
            "second_only": [],
            "shared": [],
            "has_numeric_evidence": False,
        }
    shared = first & second
    first_recall = len(shared) / len(first) if first else 1.0
    second_recall = len(shared) / len(second) if second else 1.0
    union = first | second
    return {
        "overlap_ratio": len(shared) / len(union) if union else 1.0,
        "min_recall": min(first_recall, second_recall),
        "first_only": sorted(first - second),
        "second_only": sorted(second - first),
        "shared": sorted(shared),
        "has_numeric_evidence": True,
    }


def _speaker_sequence(candidate: TranscriptionCandidate) -> list[str]:
    speakers: list[str] = []
    for segment in candidate.segments:
        if not isinstance(segment, dict):
            continue
        speaker = str(segment.get("speaker") or "").strip()
        if not speaker:
            speaker = extract_segment_speaker(str(segment.get("text") or ""))
        speakers.append(normalize_lookup_text(speaker))
    return speakers


def compute_speaker_agreement(first: TranscriptionCandidate, second: TranscriptionCandidate) -> float:
    first_speakers = _speaker_sequence(first)
    second_speakers = _speaker_sequence(second)
    comparable = min(len(first_speakers), len(second_speakers))
    if comparable <= 0:
        return 0.0
    matches = 0
    considered = 0
    for left, right in zip(first_speakers[:comparable], second_speakers[:comparable]):
        if not left or not right:
            continue
        considered += 1
        if left == right:
            matches += 1
    if considered <= 0:
        return 0.0
    return matches / considered


def _segment_text(segment: dict[str, Any]) -> str:
    return str(segment.get("text") or "").strip()


def compute_segment_alignment_rate(
    first: TranscriptionCandidate,
    second: TranscriptionCandidate,
    *,
    tolerance_seconds: float = 2.0,
    content_threshold: float = 0.20,
) -> float:
    first_segments = [segment for segment in first.segments if isinstance(segment, dict)]
    second_segments = [segment for segment in second.segments if isinstance(segment, dict)]
    if not first_segments or not second_segments:
        return 0.0

    matched = 0
    for first_segment in first_segments:
        first_start = parse_timestamp_seconds(first_segment.get("start"))
        first_text = _segment_text(first_segment)
        for second_segment in second_segments:
            second_start = parse_timestamp_seconds(second_segment.get("start"))
            if abs(first_start - second_start) > tolerance_seconds:
                continue
            if compute_token_jaccard(first_text, _segment_text(second_segment)) >= content_threshold:
                matched += 1
                break
    return matched / len(first_segments)


def compute_pairwise_signals(first: TranscriptionCandidate, second: TranscriptionCandidate) -> dict[str, Any]:
    first_text = segments_to_text(first.segments)
    second_text = segments_to_text(second.segments)
    numeric = compute_numeric_overlap(first_text, second_text)
    return {
        "providers": [first.provider, second.provider],
        "candidate_ids": [first.candidate_id, second.candidate_id],
        "token_jaccard": compute_token_jaccard(first_text, second_text),
        "numeric_overlap": numeric,
        "speaker_agreement": compute_speaker_agreement(first, second),
        "segment_alignment_rate": compute_segment_alignment_rate(first, second),
    }


def pair_key(first: TranscriptionCandidate, second: TranscriptionCandidate) -> str:
    return "__".join(sorted([first.candidate_id, second.candidate_id]))


def compute_cross_signals(candidates: list[TranscriptionCandidate]) -> dict[str, dict[str, Any]]:
    signals: dict[str, dict[str, Any]] = {}
    for index, first in enumerate(candidates):
        for second in candidates[index + 1 :]:
            signals[pair_key(first, second)] = compute_pairwise_signals(first, second)
    return signals


__all__ = [
    "compute_cross_signals",
    "compute_numeric_overlap",
    "compute_pairwise_signals",
    "compute_segment_alignment_rate",
    "compute_speaker_agreement",
    "compute_token_jaccard",
    "pair_key",
]
