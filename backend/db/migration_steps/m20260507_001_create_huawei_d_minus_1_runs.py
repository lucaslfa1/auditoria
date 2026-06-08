from typing import Any

from db.schema_tools import ensure_column, get_existing_columns


MIGRATION_NAME = "m20260507_001_create_huawei_d_minus_1_runs"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS huawei_d_minus_1_runs (
            date_str TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            first_attempt_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_attempt_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            manifest_csv_count INTEGER,
            manifest_rows_count INTEGER,
            candidates_count INTEGER,
            downloaded_count INTEGER,
            skipped_quota_count INTEGER,
            last_error TEXT,
            last_result_json JSONB,
            exhausted_alerted_at TIMESTAMPTZ
        )
        """
    )

    columns = get_existing_columns(cursor, "huawei_d_minus_1_runs")
    ensure_column(cursor, "huawei_d_minus_1_runs", "status", "TEXT NOT NULL DEFAULT 'pending'", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "attempts", "INTEGER NOT NULL DEFAULT 0", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "first_attempt_at", "TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "last_attempt_at", "TIMESTAMPTZ", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "completed_at", "TIMESTAMPTZ", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "manifest_csv_count", "INTEGER", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "manifest_rows_count", "INTEGER", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "candidates_count", "INTEGER", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "downloaded_count", "INTEGER", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "skipped_quota_count", "INTEGER", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "last_error", "TEXT", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "last_result_json", "JSONB", columns)
    ensure_column(cursor, "huawei_d_minus_1_runs", "exhausted_alerted_at", "TIMESTAMPTZ", columns)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hd1_status ON huawei_d_minus_1_runs(status)")
