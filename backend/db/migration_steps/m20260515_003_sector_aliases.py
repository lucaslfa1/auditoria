"""Fase 2 do plano de migracao DB-first (docs/database/dynamic-config-migration.md).

Consolida em DB os 3 dicionarios hardcoded de mapeamento setor-cru -> canonico:
- `sector_alias_map` em `backend/classification.py:_resolve_db_sector_alias`
- `_SECTOR_ALIASES` em `backend/repositories/operators.py`
- ladder if/elif em `repositories/operators.py:map_db_sector_to_classification_sector`
- ladder em `repositories/operators.py:_map_organizacao_telefonia_to_sector`

Cria duas tabelas:
- `sector_aliases`: regras de match (pattern_type + pattern_value -> canonical_sector_id +
  priority). `canonical_sector_id` e TEXT (sem FK para audit_sectors) porque ha
  divergencia historica entre codigo e DB que sera saneada em fase futura
  (ex: codigo mapeia "receptivo" -> "celula_atendimento", mas `audit_sectors`
  so tem o id `receptivo` — preservamos o comportamento atual nesta fase).
- `sector_aliases_audit_log`: trail JSONB padrao da Fase 1.

Idempotente. Seed dos rows iniciais fica em `database.py:_seed_sector_aliases` para
manter consistencia com o padrao Fase 1.2 (aborto se ja populado).
"""

MIGRATION_NAME = "m20260515_003_sector_aliases"


_PATTERN_TYPES = (
    "setor_exact",
    "setor_startswith",
    "setor_contains",
    "escala_contains",
    "supervisor_contains",
    "organizacao_contains",
    "organizacao_startswith",
)


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
    # 1. Tabela principal de regras
    pattern_check = ", ".join(f"'{p}'" for p in _PATTERN_TYPES)
    c.execute(
        f"""
        CREATE TABLE IF NOT EXISTS sector_aliases (
            id                  BIGSERIAL PRIMARY KEY,
            pattern_type        TEXT NOT NULL,
            pattern_value       TEXT NOT NULL,
            canonical_sector_id TEXT NOT NULL,
            priority            INTEGER NOT NULL DEFAULT 100,
            descricao           TEXT,
            ativo               BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    # CHECK separado para ser idempotente (DROP IF EXISTS antes do ADD)
    c.execute("ALTER TABLE sector_aliases DROP CONSTRAINT IF EXISTS sector_aliases_pattern_type_check")
    c.execute(
        f"""
        ALTER TABLE sector_aliases
            ADD CONSTRAINT sector_aliases_pattern_type_check
            CHECK (pattern_type IN ({pattern_check}))
        """
    )
    c.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sector_aliases_unique
            ON sector_aliases (pattern_type, LOWER(pattern_value))
        """
    )
    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sector_aliases_priority
            ON sector_aliases (priority DESC, id ASC)
            WHERE ativo
        """
    )

    # 2. Audit log padronizado
    _create_audit_log_table(c, "sector_aliases_audit_log")
