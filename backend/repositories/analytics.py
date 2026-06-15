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
