"""Utilitarios de manipulacao de schema PostgreSQL (introspeccao + metadados).

Primitivas reutilizadas pelo bootstrap de schema (`runtime_schema`) e pelas
migracoes (`migrations`): descobrir colunas existentes, adicionar coluna de forma
idempotente e ler/gravar pares chave-valor de metadados de schema
(tabela `schema_metadata`, ex.: ultima migracao aplicada).

Todas as funcoes recebem um `cursor` ja aberto pelo chamador (nao abrem nem
fecham conexao). Sem custo de API (apenas DDL/DML no PostgreSQL).
"""


def get_existing_columns(cursor, table_name: str) -> set[str]:
    """Retorna o conjunto de nomes de coluna existentes em `table_name`.

    Consulta `information_schema.columns`. Tolera cursores que retornam tupla
    ou dict (RealDictCursor). Read-only.
    """
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
    """Adiciona `column_name` a `table_name` se ainda nao existir (idempotente).

    `column_definition` e o tipo/clausula da coluna (ex.: "TEXT DEFAULT 'x'").
    `existing_columns`, se passado, evita uma consulta extra ao information_schema
    e e atualizado in-place com a nova coluna. Efeito colateral: executa
    `ALTER TABLE ... ADD COLUMN` no DB quando a coluna nao existe. Retorna True se
    adicionou, False se ja existia.
    """
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
    """Cria a tabela `schema_metadata` (chave/valor) se ainda nao existir.

    Idempotente (CREATE TABLE IF NOT EXISTS). Efeito colateral: DDL no DB.
    """
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
    """Le o valor de metadado de schema associado a `key`.

    Retorna `default` se a chave nao existir. Read-only. Tolera cursor que
    retorna tupla ou dict.
    """
    cursor.execute(
        "SELECT value FROM schema_metadata WHERE key = %s",
        (key,),
    )
    row = cursor.fetchone()
    if row is None:
        return default
    return row[0] if isinstance(row, (tuple, list)) else row["value"]


def set_schema_metadata(cursor, key: str, value: str) -> None:
    """Grava (upsert) o par chave/valor de metadado de schema, atualizando o timestamp.

    Usa INSERT ... ON CONFLICT (key) DO UPDATE. Efeito colateral: escreve em
    `schema_metadata` no DB (sem commit — quem chama controla a transacao).
    """
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

