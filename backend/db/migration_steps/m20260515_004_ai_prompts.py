"""Fase 3 do plano de migracao DB-first.

Migra os prompts e regras da IA, originalmente no `backend/config/prompts.json`, para o
banco de dados, utilizando JSONB para suportar dados complexos nativamente.
Os itens sao mapeados por 'dot-path' (ex: 'audit_system.regra_senha').

Cria duas tabelas:
- `ai_prompts`: regras de match (chave -> valor_jsonb).
- `ai_prompts_audit_log`: trail JSONB padrao para possibilitar rollback de 1-clique.

Idempotente. O seed inicial copia os dados do arquivo `prompts.json` local.
"""

MIGRATION_NAME = "m20260515_004_ai_prompts"


def _create_audit_log_table(c, table_name: str) -> None:
    c.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id             BIGSERIAL PRIMARY KEY,
            acao           TEXT NOT NULL
                           CHECK (acao IN ('create','update','delete')),
            entity_id      TEXT NOT NULL,
            payload_antes  JSONB,
            payload_depois JSONB,
            alterado_por   TEXT NOT NULL,
            alterado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            motivo         TEXT,
            origem         TEXT NOT NULL DEFAULT 'ui'
                           CHECK (origem IN ('ui','api','seed','script','system','migration'))
        )
        """
    )
    c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_entity_id ON {table_name}(entity_id)")


def apply(c):
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_prompts (
            chave TEXT PRIMARY KEY,
            valor JSONB NOT NULL,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    _create_audit_log_table(c, "ai_prompts_audit_log")


def down(c):
    c.execute("DROP TABLE IF EXISTS ai_prompts_audit_log")
    c.execute("DROP TABLE IF EXISTS ai_prompts")
