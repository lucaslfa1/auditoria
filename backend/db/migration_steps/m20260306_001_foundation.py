from typing import Any

from db.schema_tools import ensure_schema_metadata_table, set_schema_metadata


MIGRATION_NAME = "20260306_001_foundation"


def apply(cursor: Any) -> None:
    ensure_schema_metadata_table(cursor)
    set_schema_metadata(cursor, "migration.system", "enabled")
    set_schema_metadata(cursor, "migration.baseline", MIGRATION_NAME)
