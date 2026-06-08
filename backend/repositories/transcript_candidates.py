from __future__ import annotations

import json
from typing import Any, Callable, Optional


ConnectionFactory = Callable[[], Any]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _candidate_rows_from_audio_quality(audio_quality: Optional[dict[str, Any]]) -> tuple[list[dict[str, Any]], Optional[str], Optional[str], dict[str, Any]]:
    provider_meta = (
        audio_quality.get("transcription_provider")
        if isinstance(audio_quality, dict) and isinstance(audio_quality.get("transcription_provider"), dict)
        else {}
    )
    candidates = provider_meta.get("candidates") if isinstance(provider_meta.get("candidates"), list) else []
    selected_candidate_id = provider_meta.get("selected_candidate_id")
    selection_reason = provider_meta.get("selection_reason") or provider_meta.get("selected_reason")
    selection_gates = provider_meta.get("selection_gates") if isinstance(provider_meta.get("selection_gates"), dict) else {}
    rows = [dict(candidate) for candidate in candidates if isinstance(candidate, dict)]
    return rows, str(selected_candidate_id or "") or None, str(selection_reason or "") or None, selection_gates


def persist_for_audit(
    get_connection: ConnectionFactory,
    *,
    audit_id: int,
    input_hash: Optional[str],
    audio_quality: Optional[dict[str, Any]],
) -> Optional[int]:
    """Persist immutable transcription candidates and update selected audit FK.

    The application still stores the selected transcription in audits.transcription_json
    for compatibility. This table is the trace/benchmark source of truth for all
    provider artifacts seen by the selector.
    """

    rows, selected_candidate_id, selection_reason, selection_gates = _candidate_rows_from_audio_quality(audio_quality)
    if not rows:
        return None

    conn = get_connection()
    inserted_by_candidate_id: dict[str, int] = {}
    try:
        cursor = conn.cursor()
        for row in rows:
            candidate_id = str(row.get("candidate_id") or row.get("provider") or "").strip()
            provider = str(row.get("provider") or "unknown").strip().lower() or "unknown"
            status = str(row.get("status") or ("selected" if candidate_id == selected_candidate_id else "candidate")).strip().lower()
            cursor.execute(
                """
                INSERT INTO transcript_candidates (
                    audit_id, input_hash, candidate_id, provider, purpose,
                    segments, raw_response, provider_metadata, quality_flags,
                    deterministic_score, judge_score, judge_reason, cross_signals,
                    status, error, elapsed_seconds
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s, %s)
                RETURNING id
                """,
                (
                    audit_id,
                    input_hash,
                    candidate_id or provider,
                    provider,
                    str(row.get("purpose") or "audit"),
                    _json_dumps(row.get("segments") or []),
                    _json_dumps(row.get("raw_response")) if row.get("raw_response") is not None else None,
                    _json_dumps(row.get("provider_metadata") or {}),
                    _json_dumps(row.get("quality_flags") or {}),
                    row.get("deterministic_score"),
                    row.get("judge_score"),
                    row.get("judge_reason"),
                    _json_dumps(row.get("cross_signals") or {}),
                    status,
                    row.get("error"),
                    row.get("elapsed_seconds"),
                ),
            )
            inserted_id = cursor.fetchone()[0]
            if candidate_id:
                inserted_by_candidate_id[candidate_id] = int(inserted_id)

        selected_db_id = inserted_by_candidate_id.get(selected_candidate_id or "")
        if selected_db_id:
            cursor.execute(
                """
                UPDATE audits
                SET selected_candidate_id = %s,
                    selection_reason = %s,
                    selection_gates = %s::jsonb
                WHERE id = %s
                """,
                (
                    selected_db_id,
                    selection_reason,
                    _json_dumps(selection_gates or {}),
                    audit_id,
                ),
            )
            cursor.execute(
                "UPDATE transcript_candidates SET status = 'selected' WHERE id = %s",
                (selected_db_id,),
            )

        conn.commit()
        return selected_db_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


__all__ = ["persist_for_audit"]
