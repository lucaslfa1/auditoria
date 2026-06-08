"""Add media_files table to abstract physical storage paths."""
from __future__ import annotations

MIGRATION_NAME = "20260522_001_media_files"

def apply(c) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS media_files (
            id SERIAL PRIMARY KEY,
            file_hash TEXT UNIQUE NOT NULL,
            storage_backend TEXT NOT NULL,
            storage_key TEXT NOT NULL,
            content_type TEXT,
            size_bytes BIGINT,
            original_filename TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_files_backend ON media_files(storage_backend)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_files_backend_key ON media_files(storage_backend, storage_key)")
