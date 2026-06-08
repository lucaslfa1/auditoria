from typing import Any

from db.migration_steps.m20260308_004_domain_invariants import _create_audits_triggers


MIGRATION_NAME = "20260312_012_allow_awaiting_pair_status"


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
    if False:
        _create_audits_triggers(cursor)
