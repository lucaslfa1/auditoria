from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any


_UNVERIFIED_EVIDENCE_NOTE = (
    "Evidencia informada pela IA nao foi localizada na transcricao; "
    "revise o trecho antes de usar como prova."
)


def _normalize_evidence_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _transcription_text(transcription: Any) -> str:
    if isinstance(transcription, dict):
        transcription = transcription.get("transcription", [])
    if not isinstance(transcription, list):
        return ""

    parts: list[str] = []
    for segment in transcription:
        if isinstance(segment, dict):
            text = str(segment.get("text") or "").strip()
        else:
            text = str(getattr(segment, "text", "") or "").strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def _has_fuzzy_match(evidence_norm: str, transcription_norm: str) -> bool:
    evidence_tokens = evidence_norm.split()
    transcription_tokens = transcription_norm.split()
    if len(evidence_tokens) < 4 or len(transcription_tokens) < len(evidence_tokens):
        return False

    expected_len = len(evidence_tokens)
    min_window = max(4, expected_len - 2)
    max_window = min(len(transcription_tokens), expected_len + 2)
    for window_len in range(min_window, max_window + 1):
        for start in range(0, len(transcription_tokens) - window_len + 1):
            candidate = " ".join(transcription_tokens[start : start + window_len])
            if SequenceMatcher(None, evidence_norm, candidate).ratio() >= 0.86:
                return True
    return False


def _validate_single_evidence(evidence_text: Any, transcription_text: str) -> dict[str, Any]:
    evidence = str(evidence_text or "").strip()
    if not evidence:
        return {"status": "missing", "matched": False, "method": "empty"}

    if evidence in transcription_text:
        return {"status": "matched", "matched": True, "method": "literal"}

    evidence_norm = _normalize_evidence_text(evidence)
    transcription_norm = _normalize_evidence_text(transcription_text)
    if evidence_norm and transcription_norm and evidence_norm in transcription_norm:
        return {"status": "matched", "matched": True, "method": "normalized"}

    if evidence_norm and transcription_norm and _has_fuzzy_match(evidence_norm, transcription_norm):
        return {"status": "matched", "matched": True, "method": "fuzzy"}

    return {"status": "not_found", "matched": False, "method": "none"}


def validate_evidence_against_transcription(payload: Any, transcription: Any) -> Any:
    """Annotate AI audit evidence with a deterministic transcription check."""
    if not isinstance(payload, dict):
        return payload

    details = payload.get("details")
    if not isinstance(details, list):
        return dict(payload)

    full_transcription = _transcription_text(transcription)
    normalized_details: list[Any] = []
    for item in details:
        if not isinstance(item, dict):
            normalized_details.append(item)
            continue

        detail = dict(item)
        validation = _validate_single_evidence(detail.get("evidence_text"), full_transcription)
        detail["evidence_validation"] = validation

        if detail.get("evidence_text") and not validation.get("matched"):
            comment = str(detail.get("comment") or "").strip()
            if _UNVERIFIED_EVIDENCE_NOTE not in comment:
                detail["comment"] = (
                    f"{comment} [{_UNVERIFIED_EVIDENCE_NOTE}]"
                    if comment
                    else _UNVERIFIED_EVIDENCE_NOTE
                )

        normalized_details.append(detail)

    normalized_payload = dict(payload)
    normalized_payload["details"] = normalized_details
    return normalized_payload


def summarize_evidence_coverage(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "quality": "indefinida",
            "review_recommended": True,
            "reason": "payload_invalido",
            "total_details": 0,
            "evaluable_details": 0,
            "with_evidence": 0,
            "matched_evidence": 0,
            "missing_evidence": 0,
            "unverified_evidence": 0,
            "matched_ratio": 0.0,
        }

    details = payload.get("details")
    if not isinstance(details, list):
        details = []

    evaluable = 0
    with_evidence = 0
    matched = 0
    missing = 0
    unverified = 0

    for item in details:
        if not isinstance(item, dict):
            continue
        evaluable += 1
        evidence = str(item.get("evidence_text") or "").strip()
        validation = item.get("evidence_validation") if isinstance(item.get("evidence_validation"), dict) else {}
        if evidence:
            with_evidence += 1
        else:
            missing += 1
        if validation.get("matched"):
            matched += 1
        elif evidence:
            unverified += 1

    matched_ratio = (matched / evaluable) if evaluable else 1.0
    evidence_ratio = (with_evidence / evaluable) if evaluable else 1.0

    if evaluable == 0:
        quality = "sem_criterios_avaliaveis"
        review = False
        reason = ""
    elif matched_ratio >= 0.80 and missing == 0:
        quality = "boa"
        review = False
        reason = ""
    elif matched_ratio >= 0.55:
        quality = "regular"
        review = True
        reason = "cobertura_de_evidencia_regular"
    elif with_evidence > 0:
        quality = "baixa"
        review = True
        reason = "evidencias_nao_localizadas_na_transcricao"
    else:
        quality = "muito_baixa"
        review = True
        reason = "criterios_sem_evidencia"

    return {
        "quality": quality,
        "review_recommended": review,
        "reason": reason,
        "total_details": len([item for item in details if isinstance(item, dict)]),
        "evaluable_details": evaluable,
        "with_evidence": with_evidence,
        "matched_evidence": matched,
        "missing_evidence": missing,
        "unverified_evidence": unverified,
        "evidence_ratio": round(evidence_ratio, 3),
        "matched_ratio": round(matched_ratio, 3),
    }
