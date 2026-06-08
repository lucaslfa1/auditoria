from typing import Any

from db.schema_tools import get_existing_columns


MIGRATION_NAME = "20260312_010_backfill_huawei_id_from_telefonia"


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='colaboradores'"
    )
    if cursor.fetchone() is None:
        return

    columns = get_existing_columns(cursor, "colaboradores")
    if "id_huawei" not in columns or "id_telefonia" not in columns:
        return

    cursor.execute(
        """
        UPDATE colaboradores
        SET id_huawei = id_telefonia
        WHERE COALESCE(TRIM(id_huawei), '') = ''
          AND COALESCE(TRIM(id_telefonia), '') != ''
        """
    )
