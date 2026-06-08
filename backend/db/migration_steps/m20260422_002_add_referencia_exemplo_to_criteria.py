from typing import Any
from db.schema_tools import ensure_column, get_existing_columns

MIGRATION_NAME = "20260422_002_add_referencia_exemplo_to_criteria"

def apply(cursor: Any) -> None:
    columns = get_existing_columns(cursor, "audit_criteria")
    ensure_column(cursor, "audit_criteria", "referencia", "TEXT", columns)
    ensure_column(cursor, "audit_criteria", "exemplo", "TEXT", columns)
