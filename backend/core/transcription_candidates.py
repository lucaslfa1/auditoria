from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


Segment = dict[str, Any]


@dataclass(frozen=True)
class TranscriptionCandidate:
    """Immutable-ish transcription artifact used by the sandbox selector.

    The candidate represents text produced by a real transcription provider.
    LLM judges may rank candidates later, but must not replace these segments
    with generated text.
    """

    candidate_id: str
    provider: str
    segments: list[Segment]
    deterministic_score: float = 0.0
    status: str = "candidate"
    raw_response: Optional[Any] = None
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    quality_flags: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    elapsed_seconds: Optional[float] = None

    @property
    def segment_count(self) -> int:
        return sum(1 for segment in self.segments if isinstance(segment, dict))

    @property
    def has_error(self) -> bool:
        return bool(self.error) or self.status == "errored"

    @property
    def text(self) -> str:
        return segments_to_text(self.segments)


def clone_segments(segments: list[Segment] | None) -> list[Segment]:
    return [dict(segment) for segment in (segments or []) if isinstance(segment, dict)]


def segments_to_text(segments: list[Segment] | None) -> str:
    return " ".join(
        str(segment.get("text") or "").strip()
        for segment in (segments or [])
        if isinstance(segment, dict) and str(segment.get("text") or "").strip()
    ).strip()


def build_candidate(
    provider: str,
    segments: list[Segment] | None,
    *,
    candidate_id: Optional[str] = None,
    deterministic_score: Optional[float] = None,
    status: str = "candidate",
    raw_response: Optional[Any] = None,
    provider_metadata: Optional[dict[str, Any]] = None,
    quality_flags: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
) -> TranscriptionCandidate:
    normalized_provider = str(provider or "unknown").strip().lower() or "unknown"
    cloned_segments = clone_segments(segments)
    if deterministic_score is None:
        deterministic_score = float(sum(len(str(segment.get("text") or "")) for segment in cloned_segments))
    return TranscriptionCandidate(
        candidate_id=candidate_id or normalized_provider,
        provider=normalized_provider,
        segments=cloned_segments,
        deterministic_score=float(deterministic_score or 0.0),
        status=status,
        raw_response=raw_response,
        provider_metadata=dict(provider_metadata or {}),
        quality_flags=dict(quality_flags or {}),
        error=error,
        elapsed_seconds=elapsed_seconds,
    )


__all__ = [
    "Segment",
    "TranscriptionCandidate",
    "build_candidate",
    "clone_segments",
    "segments_to_text",
]
