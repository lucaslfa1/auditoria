from typing import Any

from db.schema_tools import ensure_column, get_existing_columns


MIGRATION_NAME = "m20260507_002_huawei_d1_operational_hardening"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        ALTER TABLE huawei_d_minus_1_runs
            ALTER COLUMN first_attempt_at TYPE TIMESTAMPTZ
                USING first_attempt_at AT TIME ZONE 'UTC',
            ALTER COLUMN last_attempt_at TYPE TIMESTAMPTZ
                USING last_attempt_at AT TIME ZONE 'UTC',
            ALTER COLUMN completed_at TYPE TIMESTAMPTZ
                USING completed_at AT TIME ZONE 'UTC'
        """
    )
    cursor.execute(
        """
        ALTER TABLE huawei_d_minus_1_runs
            ALTER COLUMN first_attempt_at SET DEFAULT CURRENT_TIMESTAMP
        """
    )

    columns = get_existing_columns(cursor, "huawei_d_minus_1_runs")
    ensure_column(cursor, "huawei_d_minus_1_runs", "exhausted_alerted_at", "TIMESTAMPTZ", columns)
