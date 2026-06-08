from typing import Any

from db.schema_tools import get_existing_columns


MIGRATION_NAME = "20260312_005_rename_operadores_rh_to_colaboradores"


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='operadores_rh'"
    )
    old_exists = cursor.fetchone() is not None

    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='colaboradores'"
    )
    new_exists = cursor.fetchone() is not None

    if old_exists and not new_exists:
        # Simple rename
        cursor.execute("ALTER TABLE operadores_rh RENAME TO colaboradores")
    elif old_exists and new_exists:
        # Both exist (runtime_schema already created colaboradores).
        # Migrate data from old table into new, then drop old.
        cursor.execute("SELECT COUNT(*) FROM colaboradores")
        new_count = cursor.fetchone()[0]

        if new_count == 0:
            # New table is empty - just copy everything from old
            old_cols = get_existing_columns(cursor, "operadores_rh")
            new_cols = get_existing_columns(cursor, "colaboradores")
            shared = [c for c in old_cols if c in new_cols and c != "id"]
            if shared:
                cols_str = ", ".join(shared)
                cursor.execute(
                    f"INSERT INTO colaboradores ({cols_str}) SELECT {cols_str} FROM operadores_rh"
                )

        cursor.execute("DROP TABLE operadores_rh")
    # else: old doesn't exist - nothing to do (fresh DB, colaboradores already created)

    # Drop old indexes (they may or may not exist)
    old_indexes = [
        "idx_operadores_rh_nome",
        "idx_operadores_rh_escala",
        "idx_operadores_rh_supervisor",
        "idx_operadores_rh_matricula",
        "idx_operadores_rh_id_weon",
        "idx_operadores_rh_id_huawei",
        "idx_operadores_rh_id_telefonia",
        "idx_operadores_rh_softphone",
        "idx_operadores_rh_status_supervisor_escala",
    ]
    for idx_name in old_indexes:
        cursor.execute(f"DROP INDEX IF EXISTS {idx_name}")

    # Recreate indexes only for columns that exist
    columns = get_existing_columns(cursor, "colaboradores")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_nome ON colaboradores(nome)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_escala ON colaboradores(escala)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_supervisor ON colaboradores(supervisor)")

    if "matricula" in columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_matricula ON colaboradores(matricula)")
    if "id_weon" in columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_weon ON colaboradores(id_weon)")
    if "id_huawei" in columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_huawei ON colaboradores(id_huawei)")
    if "id_telefonia" in columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_telefonia ON colaboradores(id_telefonia)")
    if "softphone_number" in columns:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_softphone ON colaboradores(softphone_number)")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_colaboradores_status_supervisor_escala ON colaboradores(status, supervisor, escala)"
    )
