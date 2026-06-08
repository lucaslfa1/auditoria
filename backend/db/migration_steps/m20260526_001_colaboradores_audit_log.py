"""Cria colaboradores_audit_log para rastrear mudancas em operadores.

Sugestao 1 da revisao de arquitetura whitelist: hoje qualquer mudanca em
`auditavel`, `id_huawei`, `status` etc nao deixa rastro. Quando um operador
some da fila de auditoria, ninguem sabe quem desativou nem quando.

Replica o padrao de `ai_prompts_audit_log` / `audit_alerts_audit_log`:
mesma estrutura JSONB (acao, entity_id, payload_antes/depois, alterado_por,
motivo, origem). Permite rollback de 1-clique e trilha de compliance.

Idempotente. Nao mexe na tabela `colaboradores` existente.
"""

MIGRATION_NAME = "m20260526_001_colaboradores_audit_log"


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
    c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_alterado_em ON {table_name}(alterado_em DESC)")


def apply(c):
    _create_audit_log_table(c, "colaboradores_audit_log")


def down(c):
    c.execute("DROP TABLE IF EXISTS colaboradores_audit_log")
