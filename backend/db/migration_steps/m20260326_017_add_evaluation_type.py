from typing import Any
from db.schema_tools import ensure_column, get_existing_columns

MIGRATION_NAME = "20260326_017_add_evaluation_type"


def apply(cursor: Any) -> None:
    """Add evaluation_type column to audit_criteria.

    Values: 'auto' (default, evaluated by AI) or 'manual' (reserved for human auditor).
    Criteria marked as 'manual' will return 'pending_manual' status from the AI
    and must be filled in by the auditor after automated processing.
    """
    columns = get_existing_columns(cursor, "audit_criteria")
    ensure_column(cursor, "audit_criteria", "evaluation_type", "TEXT DEFAULT 'auto'", columns)
