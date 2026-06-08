"""Fase 1.1 do plano de migracao DB-first (docs/database/dynamic-config-migration.md).

Cria a infraestrutura de auditoria para o catalogo de criterios:
- `pop_ref TEXT` em `audit_alerts` (hoje so existe no YAML; sera populado por backfill).
- `audit_sectors_audit_log`, `audit_alerts_audit_log`, `audit_criteria_audit_log`:
  trilha unificada de quem mudou o que (acao + payload JSONB antes/depois).

Padrao escolhido (diferente do `configuracoes_audit_log` chave/valor): como sector/alert/
criterion tem varios campos (label, weight, context, etc.), usar JSONB para o snapshot
antes/depois evita inflar a tabela com uma linha por campo. `acao` distingue
create/update/delete.

Tudo idempotente. NAO faz backfill de `pop_ref` aqui — o backfill vem em script Python
separado (`backend/scripts/backfill_pop_ref_from_yaml.py`) executado uma vez e versionado
junto com esta fase.
"""

MIGRATION_NAME = "m20260515_002_audit_criteria_audit_log"


def _create_audit_log_table(c, table_name: str) -> None:
    """Cria uma tabela *_audit_log padronizada e seus indexes (idempotente)."""
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
    c.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_entity_em
            ON {table_name} (entity_id, alterado_em DESC)
        """
    )
    c.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_em
            ON {table_name} (alterado_em DESC)
        """
    )


def apply(c):
    # 1. pop_ref em audit_alerts (aditivo, nullable — backfill vem em script)
    c.execute(
        "ALTER TABLE audit_alerts ADD COLUMN IF NOT EXISTS pop_ref TEXT"
    )
    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_alerts_pop_ref
            ON audit_alerts (pop_ref) WHERE pop_ref IS NOT NULL
        """
    )

    # 2. Tres audit_log tables (mesma estrutura, padronizadas)
    for tbl in ("audit_sectors_audit_log", "audit_alerts_audit_log", "audit_criteria_audit_log"):
        _create_audit_log_table(c, tbl)
