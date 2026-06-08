from typing import Any


MIGRATION_NAME = "20260428_001_m1_m4_features"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_drafts (
            input_hash TEXT NOT NULL,
            user_id TEXT NOT NULL,
            details_json TEXT,
            transcription_json TEXT,
            updated_at TEXT,
            PRIMARY KEY (input_hash, user_id)
        )
        """
    )
