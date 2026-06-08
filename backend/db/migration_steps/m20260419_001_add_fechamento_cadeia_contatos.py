from typing import Any


MIGRATION_NAME = "20260419_001_add_fechamento_cadeia_contatos"


def apply(cursor: Any) -> None:
    """
    Descreva aqui a alteracao de schema/dados.
    Use %s para placeholders (PostgreSQL/psycopg2).
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fechamento_cadeia_contatos (
            id SERIAL PRIMARY KEY,
            colaborador_id INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            nota_mot REAL DEFAULT 0,
            nota_pa REAL DEFAULT 0,
            nota_cli REAL DEFAULT 0,
            nota_policia REAL DEFAULT 0,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(colaborador_id, mes, ano)
        )
        """
    )
