from typing import Any


MIGRATION_NAME = "20260320_015_add_ai_feedback_table"


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ai_feedback'"
    )
    if cursor.fetchone() is not None:
        return

    cursor.execute("""
        CREATE TABLE ai_feedback (
            id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL CHECK(tipo IN ('classificacao','avaliacao','fatal_flag','regra_geral')),
            setor TEXT,
            criterio_id TEXT,
            situacao TEXT NOT NULL,
            correcao TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            exemplo_transcricao TEXT,
            criado_por TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX idx_ai_feedback_tipo_setor
        ON ai_feedback(tipo, setor)
        WHERE ativo = 1
    """)
