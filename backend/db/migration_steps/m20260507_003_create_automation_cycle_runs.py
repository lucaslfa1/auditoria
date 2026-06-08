from typing import Any


MIGRATION_NAME = "m20260507_003_create_automation_cycle_runs"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_cycle_runs (
            id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            stage TEXT NOT NULL DEFAULT 'starting',
            message TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ,
            last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            baixadas INTEGER NOT NULL DEFAULT 0,
            auditadas INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            sync_result JSONB,
            audit_result JSONB,
            result JSONB
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_cycle_runs_started_at "
        "ON automation_cycle_runs(started_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_cycle_runs_status "
        "ON automation_cycle_runs(status)"
    )
