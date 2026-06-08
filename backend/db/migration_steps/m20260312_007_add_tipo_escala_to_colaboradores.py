from typing import Any

from db.schema_tools import get_existing_columns


MIGRATION_NAME = "20260312_007_add_tipo_escala_to_colaboradores"


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='colaboradores'"
    )
    if cursor.fetchone() is None:
        return

    columns = get_existing_columns(cursor, "colaboradores")
    if "tipo_escala" not in columns:
        cursor.execute("ALTER TABLE colaboradores ADD COLUMN tipo_escala TEXT")
