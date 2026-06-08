from typing import Any

from db.schema_tools import ensure_column, get_existing_columns


MIGRATION_NAME = "20260312_011_add_audit_audio_storage"


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='audits'"
    )
    if cursor.fetchone() is None:
        return

    audit_columns = get_existing_columns(cursor, "audits")
    ensure_column(cursor, "audits", "audio_storage_path", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_original_filename", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_mime_type", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_size_bytes", "INTEGER", audit_columns)
