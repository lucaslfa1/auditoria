from typing import Any
from db.schema_tools import ensure_column, get_existing_columns

MIGRATION_NAME = "20260320_016_add_chave_to_criteria"


def apply(cursor: Any) -> None:
    # We add 'chave' to audit_criteria to match the string ID from the JSON
    columns = get_existing_columns(cursor, "audit_criteria")
    ensure_column(cursor, "audit_criteria", "chave", "TEXT", columns)
    
    # We will also add 'context' and 'weight' etc if not exist, but let's check
    # Wait, audit_alerts already has 'context'. audit_criteria has 'weight'.
    
    # For now, just 'chave'
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_criteria_chave ON audit_criteria(chave)")

