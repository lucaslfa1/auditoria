from __future__ import annotations
"""Index curated POP markdown sections into procedimento_chunks.

This script is intentionally safe to run repeatedly. It upserts chunks by
source path, section title and chunk index, and deletes stale rows for sources
that no longer exist in ``rag/sources/procedimentos_operacionais``.
"""


import json
import logging
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR.parent / ".env", override=False)
load_dotenv(_BACKEND_DIR / ".env", override=True)

from core.procedimentos_rag import build_procedimento_chunks
from core.rag_triagem import gerar_embedding
from db.database import get_connection, init_db


logger = logging.getLogger(__name__)


def _has_embedding_column(cursor) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'procedimento_chunks'
          AND column_name = 'embedding'
        """
    )
    return cursor.fetchone() is not None


def _rollback_and_release_savepoint(cursor, name: str) -> None:
    try:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {name}")
    except Exception:
        return
    try:
        cursor.execute(f"RELEASE SAVEPOINT {name}")
    except Exception:
        pass


def _ensure_embedding_column(cursor) -> bool:
    if _has_embedding_column(cursor):
        return True

    savepoint = "_procedimento_chunks_vector_sync"
    try:
        cursor.execute(f"SAVEPOINT {savepoint}")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("ALTER TABLE procedimento_chunks ADD COLUMN IF NOT EXISTS embedding vector(1536)")
        cursor.execute(f"RELEASE SAVEPOINT {savepoint}")
    except Exception as exc:
        _rollback_and_release_savepoint(cursor, savepoint)
        logger.warning("procedimento_chunks: pgvector indisponivel, sync sem embeddings: %s", exc)
        return False

    index_savepoint = "_procedimento_chunks_vector_index_sync"
    try:
        cursor.execute(f"SAVEPOINT {index_savepoint}")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_procedimento_chunks_embedding
            ON procedimento_chunks
            USING ivfflat (embedding vector_l2_ops)
            WITH (lists = 100)
            """
        )
        cursor.execute(f"RELEASE SAVEPOINT {index_savepoint}")
    except Exception as exc:
        _rollback_and_release_savepoint(cursor, index_savepoint)
        logger.warning("procedimento_chunks: indice vetorial nao criado: %s", exc)

    return _has_embedding_column(cursor)


def sync_procedimento_chunks(*, generate_embeddings: bool = True) -> dict:
    init_db()
    chunks = build_procedimento_chunks()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        has_embedding = _ensure_embedding_column(cursor)
        current_sources = sorted({chunk.source_path for chunk in chunks})
        if current_sources:
            cursor.execute(
                "DELETE FROM procedimento_chunks WHERE NOT (source_path = ANY(%s))",
                (current_sources,),
            )
        else:
            cursor.execute("DELETE FROM procedimento_chunks")

        for chunk in chunks:
            metadata = {
                "alert_ids": list(chunk.alert_ids),
                "source_hash": chunk.source_hash,
            }
            alert_id = chunk.alert_ids[0] if chunk.alert_ids else None
            alert_label = chunk.section_title
            embedding = None
            if generate_embeddings and has_embedding:
                embedding = gerar_embedding(chunk.content)

            if has_embedding and embedding is not None:
                cursor.execute(
                    """
                    INSERT INTO procedimento_chunks (
                        source_path, source_hash, setor, alert_id, alert_label,
                        section_title, chunk_index, content, metadata_json, embedding,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, CURRENT_TIMESTAMP)
                    ON CONFLICT (source_path, section_title, chunk_index) DO UPDATE SET
                        source_hash = EXCLUDED.source_hash,
                        setor = EXCLUDED.setor,
                        alert_id = EXCLUDED.alert_id,
                        alert_label = EXCLUDED.alert_label,
                        content = EXCLUDED.content,
                        metadata_json = EXCLUDED.metadata_json,
                        embedding = EXCLUDED.embedding,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        chunk.source_path,
                        chunk.source_hash,
                        chunk.setor,
                        alert_id,
                        alert_label,
                        chunk.section_title,
                        chunk.chunk_index,
                        chunk.content,
                        json.dumps(metadata, ensure_ascii=False),
                        str(embedding) if embedding else None,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO procedimento_chunks (
                        source_path, source_hash, setor, alert_id, alert_label,
                        section_title, chunk_index, content, metadata_json,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (source_path, section_title, chunk_index) DO UPDATE SET
                        source_hash = EXCLUDED.source_hash,
                        setor = EXCLUDED.setor,
                        alert_id = EXCLUDED.alert_id,
                        alert_label = EXCLUDED.alert_label,
                        content = EXCLUDED.content,
                        metadata_json = EXCLUDED.metadata_json,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        chunk.source_path,
                        chunk.source_hash,
                        chunk.setor,
                        alert_id,
                        alert_label,
                        chunk.section_title,
                        chunk.chunk_index,
                        chunk.content,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
        conn.commit()
        return {
            "chunks": len(chunks),
            "sources": len(current_sources),
            "embedding_column": has_embedding,
            "embeddings_requested": generate_embeddings,
        }
    finally:
        conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    no_embeddings = os.getenv("RAG_SKIP_EMBEDDINGS", "").lower() in {"1", "true", "yes"}
    result = sync_procedimento_chunks(generate_embeddings=not no_embeddings)
    logger.info("procedimento_chunks synced: %s", result)


if __name__ == "__main__":
    main()
