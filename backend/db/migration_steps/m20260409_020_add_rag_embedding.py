"""Migration: Adiciona coluna de embedding vetorial à tabela ai_feedback.

Habilita pgvector e adiciona suporte a busca semântica (RAG) para
injetar exemplos historicamente relevantes no prompt de classificação.
"""
from typing import Any


MIGRATION_NAME = "20260409_020_add_rag_embedding"


def apply(cursor: Any) -> None:
    # 1. Garantir extensão pgvector (usando SAVEPOINT para não abortar a
    #    transação caso a extensão não esteja disponível ou exija superuser).
    pgvector_available = False
    try:
        cursor.execute("SAVEPOINT _pgvector_check")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("RELEASE SAVEPOINT _pgvector_check")
        pgvector_available = True
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT _pgvector_check")

    if not pgvector_available:
        # Sem pgvector não é possível criar a coluna vector(1536).
        # A migração é registrada como aplicada para não retentar em cada
        # init_db; quando pgvector for instalado, um re-seed pode adicioná-la.
        return

    # 2. Adicionar coluna de embedding se não existir
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'ai_feedback'
          AND column_name = 'transcricao_embedding'
        """
    )
    if cursor.fetchone() is None:
        cursor.execute(
            "ALTER TABLE ai_feedback ADD COLUMN transcricao_embedding vector(1536)"
        )
