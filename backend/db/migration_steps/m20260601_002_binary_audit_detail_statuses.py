MIGRATION_NAME = "m20260601_002_binary_audit_detail_statuses"


def _as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_detail(detail):
    if not isinstance(detail, dict):
        return None, 0.0, 0.0

    item = dict(detail)
    status = str(item.get("status") or "").strip().lower()
    weight = _as_float(item.get("weight"), 0.0)
    deflator = abs(_as_float(item.get("deflator"), 0.0))

    if status in {"pass", "na", "n/a", "pending_manual"}:
        item["status"] = "pass"
        item["obtainedScore"] = round(weight, 2)
        return item, weight, weight

    if status in {"fail", "partial"}:
        item["status"] = "fail"
        item["obtainedScore"] = round(-deflator, 2)
        return item, -deflator, weight

    item["status"] = "fail"
    item["obtainedScore"] = round(-deflator, 2)
    return item, -deflator, weight


def apply(c):
    # GEMINI.md: detalhes de auditoria sao binarios. Este backfill remove
    # estados legados de criterios ja salvos, preservando evidencia/comentarios.
    c.execute(
        """
        SELECT id, details_json, score
        FROM audits
        WHERE EXISTS (
            SELECT 1
            FROM jsonb_array_elements(details_json::jsonb) detail
            WHERE LOWER(detail->>'status') IN ('pending_manual', 'na', 'n/a', 'partial')
        )
        """
    )
    rows = c.fetchall()

    import json

    for row in rows:
        audit_id = row["id"] if hasattr(row, "keys") and "id" in row.keys() else row[0]
        raw_details = row["details_json"] if hasattr(row, "keys") and "details_json" in row.keys() else row[1]
        old_score = row["score"] if hasattr(row, "keys") and "score" in row.keys() else row[2]
        try:
            details = json.loads(raw_details) if isinstance(raw_details, str) else raw_details
        except (TypeError, ValueError):
            continue
        if not isinstance(details, list):
            continue

        normalized_details = []
        new_score = 0.0
        new_max_score = 0.0
        old_positive = False
        changed = False

        for detail in details:
            if isinstance(detail, dict) and _as_float(detail.get("obtainedScore"), 0.0) > 0:
                old_positive = True
            original_status = str(detail.get("status") or "").strip().lower() if isinstance(detail, dict) else ""
            normalized, score_delta, max_delta = _normalize_detail(detail)
            if normalized is None:
                continue
            if normalized.get("status") != original_status:
                changed = True
            normalized_details.append(normalized)
            new_score += score_delta
            new_max_score += max_delta

        if not changed:
            continue

        # Auditoria fatal zerada historicamente deve continuar zerada.
        if _as_float(old_score, 0.0) == 0.0 and old_positive:
            new_score = 0.0

        c.execute(
            """
            UPDATE audits
            SET details_json = %s,
                score = %s,
                max_score = %s
            WHERE id = %s
            """,
            (
                json.dumps(normalized_details, ensure_ascii=False),
                round(new_score, 2),
                round(new_max_score, 2),
                audit_id,
            ),
        )
