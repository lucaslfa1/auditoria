"""Migration: add curated POP chunks table for RAG."""

from typing import Any


MIGRATION_NAME = "20260416_021_add_procedimento_chunks"


def _column_exists(cursor: Any, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    return cursor.fetchone() is not None


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS procedimento_chunks (
            id SERIAL PRIMARY KEY,
            source_path TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            setor TEXT,
            alert_id TEXT,
            alert_label TEXT,
            section_title TEXT NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_path, section_title, chunk_index)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_procedimento_chunks_setor ON procedimento_chunks (setor)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_procedimento_chunks_alert_id ON procedimento_chunks (alert_id)"
    )

    pgvector_available = False
    try:
        cursor.execute("SAVEPOINT _procedimento_chunks_vector")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("RELEASE SAVEPOINT _procedimento_chunks_vector")
        pgvector_available = True
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT _procedimento_chunks_vector")
        cursor.execute("RELEASE SAVEPOINT _procedimento_chunks_vector")

    if pgvector_available and not _column_exists(cursor, "procedimento_chunks", "embedding"):
        cursor.execute("ALTER TABLE procedimento_chunks ADD COLUMN embedding vector(1536)")
        try:
            cursor.execute("SAVEPOINT _procedimento_chunks_vector_index")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_procedimento_chunks_embedding
                ON procedimento_chunks
                USING ivfflat (embedding vector_l2_ops)
                WITH (lists = 100)
                """
            )
            cursor.execute("RELEASE SAVEPOINT _procedimento_chunks_vector_index")
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT _procedimento_chunks_vector_index")
            cursor.execute("RELEASE SAVEPOINT _procedimento_chunks_vector_index")
            # The table remains usable without the ANN index; exact vector scans
            # still work and small corpora do not need ivfflat.
            pass
