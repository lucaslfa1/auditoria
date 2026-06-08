import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any, max_length: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def summarize_transcription_metadata(metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    attempts_summary: list[dict[str, Any]] = []
    raw_attempts = metadata.get("attempts")
    if isinstance(raw_attempts, list):
        for item in raw_attempts:
            if not isinstance(item, dict):
                continue
            attempts_summary.append(
                {
                    "strategy": _safe_text(item.get("strategy"), 80),
                    "provider": _safe_text(item.get("provider"), 80),
                    "status": _safe_text(item.get("status"), 40),
                    "score": _safe_float(item.get("score")),
                    "reason": _safe_text(item.get("reason"), 160),
                    "error": _safe_text(item.get("error"), 200),
                }
            )

    return {
        "selected_strategy": _safe_text(metadata.get("selected_strategy"), 80),
        "selected_provider": _safe_text(metadata.get("selected_provider"), 80),
        "selected_reason": _safe_text(metadata.get("selected_reason"), 160),
        "attempt_count": len(attempts_summary),
        "attempts": attempts_summary,
    }


def summarize_audio_quality(audio_quality: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(audio_quality, dict):
        return {}

    diarization = audio_quality.get("diarization")
    diarization_summary: dict[str, Any] = {}
    if isinstance(diarization, dict):
        diarization_summary = {
            "score": _safe_float(diarization.get("score")),
            "swap_risk": _safe_text(diarization.get("swap_risk"), 40),
            "raw_speaker_count": _safe_int(diarization.get("raw_speaker_count")),
            "human_segment_count": _safe_int(diarization.get("human_segment_count")),
            "telephony_segment_count": _safe_int(diarization.get("telephony_segment_count")),
        }

    transcription_quality = audio_quality.get("transcription_quality")
    transcription_quality_summary: dict[str, Any] = {}
    if isinstance(transcription_quality, dict):
        transcription_quality_summary = {
            "score": _safe_float(transcription_quality.get("score")),
            "audit_readiness": _safe_text(transcription_quality.get("audit_readiness"), 40),
            "review_recommended": bool(transcription_quality.get("review_recommended")),
            "reasons": [
                _safe_text(reason, 120)
                for reason in (transcription_quality.get("reasons") or [])
                if str(reason).strip()
            ][:12],
        }

    evidence_quality = audio_quality.get("evidence_quality")
    evidence_quality_summary: dict[str, Any] = {}
    if isinstance(evidence_quality, dict):
        evidence_quality_summary = {
            "quality": _safe_text(evidence_quality.get("quality"), 40),
            "review_recommended": bool(evidence_quality.get("review_recommended")),
            "matched_ratio": _safe_float(evidence_quality.get("matched_ratio")),
            "matched_evidence": _safe_int(evidence_quality.get("matched_evidence")),
            "evaluable_details": _safe_int(evidence_quality.get("evaluable_details")),
            "missing_evidence": _safe_int(evidence_quality.get("missing_evidence")),
            "missing_criteria_count": _safe_int(evidence_quality.get("missing_criteria_count")),
        }

    return {
        "review_recommended": bool(audio_quality.get("review_recommended")),
        "review_priority": _safe_text(audio_quality.get("review_priority"), 40),
        "diarization": diarization_summary,
        "transcription_quality": transcription_quality_summary,
        "evidence_quality": evidence_quality_summary,
        "transcription_provider": summarize_transcription_metadata(audio_quality.get("transcription_provider")),
    }


def summarize_result(result: Any) -> dict[str, Any]:
    details = getattr(result, "details", []) or []
    detail_status_counts = {"pass": 0, "fail": 0}
    for detail in details:
        status = _safe_text(getattr(detail, "status", None), 20).lower()
        if status in {"pass", "na", "n/a", "pending_manual"}:
            detail_status_counts["pass"] += 1
        else:
            detail_status_counts["fail"] += 1

    max_score = _safe_float(getattr(result, "maxPossibleScore", None))
    score = _safe_float(getattr(result, "score", None))
    score_ratio = None
    if score is not None and max_score not in (None, 0):
        score_ratio = round(score / max_score, 4)

    fatal_flags = getattr(result, "fatal_flags", None) or []
    if not isinstance(fatal_flags, list):
        fatal_flags = []

    summary_text = _safe_text(getattr(result, "summary", ""), 600)
    return {
        "score": score,
        "max_possible_score": max_score,
        "score_ratio": score_ratio,
        "detail_status_counts": detail_status_counts,
        "fatal_flags": [_safe_text(flag, 80) for flag in fatal_flags if str(flag).strip()],
        "zeroed": bool(score == 0 and max_score not in (None, 0)),
        "summary_excerpt": summary_text,
    }


def summarize_evaluation(evaluation: Optional[dict[str, Any]], criteria_list: Optional[list[Any]]) -> dict[str, Any]:
    if not isinstance(evaluation, dict):
        return {}

    criteria_ids = {str(getattr(item, "id", "")).strip() for item in (criteria_list or []) if str(getattr(item, "id", "")).strip()}
    raw_details = evaluation.get("details")
    present_ids: set[str] = set()
    if isinstance(raw_details, list):
        for item in raw_details:
            if isinstance(item, dict):
                crit_id = str(item.get("criterionId", "")).strip()
                if crit_id:
                    present_ids.add(crit_id)

    missing_criteria = sorted(criteria_ids - present_ids)
    return {
        "raw_detail_count": len(raw_details) if isinstance(raw_details, list) else 0,
        "missing_criteria_count": len(missing_criteria),
        "missing_criteria_ids": missing_criteria[:20],
        "fatal_flags": [
            _safe_text(flag, 80)
            for flag in (evaluation.get("fatal_flags", []) if isinstance(evaluation.get("fatal_flags"), list) else [])
            if str(flag).strip()
        ],
        "has_ai_feedback": bool(evaluation.get("ai_feedback")),
    }


def build_internal_quality_trace(
    *,
    source_type: str,
    alert: Optional[Any] = None,
    sector_id: Optional[str] = None,
    input_hash: Optional[str] = None,
    transcription_metadata: Optional[dict[str, Any]] = None,
    audio_quality: Optional[dict[str, Any]] = None,
    evaluation: Optional[dict[str, Any]] = None,
    criteria_list: Optional[list[Any]] = None,
    result: Optional[Any] = None,
    from_cache: bool = False,
    stage: str = "audit_pipeline",
) -> dict[str, Any]:
    alert_id = _safe_text(getattr(alert, "id", None), 80)
    alert_label = _safe_text(getattr(alert, "label", None), 160)

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "stage": _safe_text(stage, 80),
        "from_cache": bool(from_cache),
        "input_hash": _safe_text(input_hash, 96),
        "source_type": _safe_text(source_type, 32),
        "sector_id": _safe_text(sector_id, 80),
        "alert_id": alert_id,
        "alert_label": alert_label,
        "criteria_count": len(criteria_list or []),
        "transcription": summarize_transcription_metadata(transcription_metadata),
        "audio_quality": summarize_audio_quality(audio_quality),
        "evaluation": summarize_evaluation(evaluation, criteria_list),
        "result": summarize_result(result),
    }


def emit_internal_quality_trace(logger: Optional[logging.Logger], trace: dict[str, Any]) -> dict[str, Any]:
    if not _env_flag("AUDIT_INTERNAL_OBSERVABILITY_ENABLED", True):
        return trace

    target_logger = logger or logging.getLogger("audit.internal_quality")
    target_logger.info(
        "[audit-internal-quality] %s",
        json.dumps(trace, ensure_ascii=False, sort_keys=True),
    )
    return trace
