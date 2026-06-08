from typing import Any

from db.domain_constants import (
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    LEGACY_AUDIT_STATUS_CONTESTED,
)
from db.migration_steps.m20260308_004_domain_invariants import _create_audits_triggers
from db.schema_tools import ensure_column, get_existing_columns


MIGRATION_NAME = "20260312_013_add_review_module_statuses_and_fields"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'audits'
        LIMIT 1
        """
    )
    if cursor.fetchone() is None:
        return

    audit_columns = get_existing_columns(cursor, "audits")
    ensure_column(cursor, "audits", "contestation_verdict", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "review_defense", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "reviewed_by", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "reviewed_at", "TEXT", audit_columns)

    cursor.execute(
        """
        UPDATE audits
        SET status = %s
        WHERE LOWER(TRIM(COALESCE(status, ''))) = %s
        """,
        (AUDIT_STATUS_CONTESTATION_PENDING_REVIEW, LEGACY_AUDIT_STATUS_CONTESTED),
    )

    if False:
        _create_audits_triggers(cursor)
