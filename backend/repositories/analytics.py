import json
from typing import Callable, Any

from db.domain_constants import AUDIT_PASS_THRESHOLD, AUDIT_STATUS_APPROVED, DEFAULT_SOURCE_TYPE

ConnectionFactory = Callable[[], Any]
PASS_THRESHOLD = AUDIT_PASS_THRESHOLD


def get_stats(get_connection: ConnectionFactory) -> dict:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute("SELECT score, max_score FROM audits WHERE status = %s", (AUDIT_STATUS_APPROVED,))
        rows = cursor.fetchall()

        total_audits = len(rows)
        passed_count = 0

        for row in rows:
            score = row["score"] or 0.0
            max_score = row["max_score"] or 0.0
            if max_score > 0 and score >= (max_score * PASS_THRESHOLD):
                passed_count += 1

        avg_score = sum((row["score"] or 0.0) for row in rows) / total_audits if total_audits else 0.0
        percentage_scores = [
            ((row["score"] or 0.0) / row["max_score"]) * 100
            for row in rows
            if (row["max_score"] or 0.0) > 0
        ]
        avg_score_percentage = sum(percentage_scores) / len(percentage_scores) if percentage_scores else 0.0

        return {
            "total_audits": total_audits,
            "valid_audits": total_audits,
            "invalid_audits": 0,
            "telephony_audits": 0,
            "average_score": round(avg_score or 0, 2),
            "average_score_percentage": round(avg_score_percentage or 0, 1),
            "pass_rate": round((passed_count / total_audits * 100) if total_audits else 0, 1),
        }
    finally:
        conn.close()


def get_history(get_connection: ConnectionFactory, limit: int = 10) -> list[dict]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM audits WHERE status = %s ORDER BY id DESC LIMIT %s",
            (AUDIT_STATUS_APPROVED, limit),
        )
        rows = cursor.fetchall()

        history: list[dict] = []
        for row in rows:
            history.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "operator": row["operator_name"],
                "score": row["score"],
                "max_score": row["max_score"],
                "summary": row["summary"],
                "source_type": row["source_type"] or DEFAULT_SOURCE_TYPE,
                "sector_id": row["sector_id"] if "sector_id" in row.keys() else None,
            })

        return history
    finally:
        conn.close()


def get_analytics(get_connection: ConnectionFactory, sector_id: str | None = None) -> dict:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()

        if sector_id:
            cursor.execute(
                "SELECT * FROM audits WHERE sector_id = %s AND status = %s",
                (sector_id, AUDIT_STATUS_APPROVED),
            )
        else:
            cursor.execute("SELECT * FROM audits WHERE status = %s", (AUDIT_STATUS_APPROVED,))

        rows = cursor.fetchall()

        total = len(rows)
        if total == 0:
            return {
                "total_audits": 0,
                "valid_audits": 0,
                "invalid_audits": 0,
                "telephony_audits": 0,
                "average_score": 0.0,
                "average_score_percentage": 0.0,
                "pass_rate": 0.0,
                "by_alert": {},
                "criteria_stats": [],
                "top_failed_criteria": [],
                "sector_id": sector_id,
            }

        total_score = 0.0
        total_score_percentage = 0.0
        passed_count = 0
        valid_audits = 0
        scored_audits = 0
        by_alert: dict[str, dict] = {}
        criteria_stats: dict[str, dict] = {}

        for row in rows:
            valid_audits += 1
            score = row["score"] or 0.0
            max_score = row["max_score"] or 0.0
            total_score += score
            if max_score > 0:
                total_score_percentage += (score / max_score) * 100
                scored_audits += 1
            if max_score > 0 and score >= (max_score * PASS_THRESHOLD):
                passed_count += 1

            alert_id = row["alert_id"] or "unknown"
            alert_label = row["alert_label"] or "Desconhecido"
            if alert_id not in by_alert:
                by_alert[alert_id] = {
                    "label": alert_label,
                    "count": 0,
                    "avg_score": 0.0,
                    "avg_score_percentage": 0.0,
                    "pass_rate": 0.0,
                    "_score_sum": 0.0,
                    "_score_percentage_sum": 0.0,
                    "_passed": 0,
                }
            by_alert[alert_id]["count"] += 1
            by_alert[alert_id]["_score_sum"] += score
            if max_score > 0:
                by_alert[alert_id]["_score_percentage_sum"] += (score / max_score) * 100
            if max_score > 0 and score >= (max_score * PASS_THRESHOLD):
                by_alert[alert_id]["_passed"] += 1

            details = json.loads(row["details_json"]) if row["details_json"] else []
            for item in details:
                criterion_id = item.get("criterionId", "unknown")
                if criterion_id not in criteria_stats:
                    criteria_stats[criterion_id] = {
                        "criterionId": criterion_id,
                        "label": item.get("label", ""),
                        "pass": 0,
                        "fail": 0,
                        "total": 0,
                    }
                raw_status = str(item.get("status") or "").strip().lower()
                status = "pass" if raw_status in {"pass", "na", "n/a", "pending_manual"} else "fail"
                criteria_stats[criterion_id][status] += 1
                criteria_stats[criterion_id]["total"] += 1

        for alert_id, data in by_alert.items():
            count = data["count"]
            data["avg_score"] = round(data["_score_sum"] / count, 2) if count else 0.0
            data["avg_score_percentage"] = round(data["_score_percentage_sum"] / count, 1) if count else 0.0
            data["pass_rate"] = round((data["_passed"] / count) * 100, 1) if count else 0.0
            data.pop("_score_sum", None)
            data.pop("_score_percentage_sum", None)
            data.pop("_passed", None)

        criteria_list = list(criteria_stats.values())
        for item in criteria_list:
            total_items = item["total"] or 1
            item["fail_rate"] = round((item["fail"] / total_items) * 100, 1)

        top_failed_criteria = sorted(
            criteria_list,
            key=lambda item: item["fail"],
            reverse=True,
        )[:10]

        return {
            "total_audits": total,
            "valid_audits": valid_audits,
            "invalid_audits": 0,
            "telephony_audits": 0,
            "average_score": round(total_score / valid_audits, 2) if valid_audits > 0 else 0.0,
            "average_score_percentage": round(total_score_percentage / scored_audits, 1) if scored_audits > 0 else 0.0,
            "pass_rate": round((passed_count / valid_audits) * 100, 1) if valid_audits > 0 else 0.0,
            "by_alert": by_alert,
            "criteria_stats": criteria_list,
            "top_failed_criteria": top_failed_criteria,
            "sector_id": sector_id,
        }
    finally:
        conn.close()


def get_sectors(get_connection: ConnectionFactory) -> list[str]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT sector_id FROM audits WHERE sector_id IS NOT NULL AND sector_id != ''")
        rows = cursor.fetchall()
        return [row["sector_id"] for row in rows]
    finally:
        conn.close()


def get_technical_incidents(limit: int = 50, sector_id: str | None = None) -> list[dict]:
    # Technical incidents tracking remains disabled.
    return []
