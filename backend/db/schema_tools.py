def get_existing_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
        (table_name,),
    )
    return {row[0] if isinstance(row, (tuple, list)) else row["column_name"] for row in cursor.fetchall()}

def ensure_column(
    cursor,
    table_name: str,
    column_name: str,
    column_definition: str,
    existing_columns: set[str] | None = None,
) -> bool:
    columns = existing_columns if existing_columns is not None else get_existing_columns(cursor, table_name)
    if column_name in columns:
        return False

    pg_def = column_definition
    pg_def = pg_def.replace("INTEGER", "INTEGER")
    pg_def = pg_def.replace("REAL", "DOUBLE PRECISION")
    
    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {pg_def}")
    columns.add(column_name)
    return True

def ensure_schema_metadata_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_metadata (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

def get_schema_metadata(cursor, key: str, default: str = "") -> str:
    cursor.execute(
        "SELECT value FROM schema_metadata WHERE key = %s",
        (key,),
    )
    row = cursor.fetchone()
    if row is None:
        return default
    return row[0] if isinstance(row, (tuple, list)) else row["value"]


def set_schema_metadata(cursor, key: str, value: str) -> None:
    cursor.execute(
        """
        INSERT INTO schema_metadata (key, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )

