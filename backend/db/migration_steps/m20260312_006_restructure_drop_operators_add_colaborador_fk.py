from typing import Any

from db.schema_tools import get_existing_columns

MIGRATION_NAME = "20260312_006_restructure_drop_operators_add_colaborador_fk"


def apply(cursor: Any) -> None:
    # ── 1. Drop legacy `operators` table (always empty, replaced by colaboradores) ──
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='operators'"
    )
    if cursor.fetchone() is not None:
        cursor.execute("DROP INDEX IF EXISTS idx_operators_name")
        cursor.execute("DROP TABLE operators")

    # ── 2. Add colaborador_id FK column to audits ──
    audit_cols = get_existing_columns(cursor, "audits")
    if "colaborador_id" not in audit_cols:
        cursor.execute(
            "ALTER TABLE audits ADD COLUMN colaborador_id INTEGER REFERENCES colaboradores(id)"
        )

    # ── 3. Backfill colaborador_id from operator_name (fuzzy match) ──
    cursor.execute(
        """
        UPDATE audits
        SET colaborador_id = (
            SELECT c.id FROM colaboradores c
            WHERE LOWER(TRIM(audits.operator_name)) = LOWER(TRIM(c.nome))
            LIMIT 1
        )
        WHERE operator_name IS NOT NULL
          AND operator_name != ''
          AND colaborador_id IS NULL
        """
    )

    # ── 4. Create index on the new FK ──
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audits_colaborador_id ON audits(colaborador_id)"
    )

    # ── 5. Create convenience view: audits joined with colaborador data ──
    cursor.execute("DROP VIEW IF EXISTS audits_com_colaborador")
    cursor.execute(
        """
        CREATE VIEW audits_com_colaborador AS
        SELECT
            a.id,
            a.timestamp,
            a.operator_name,
            a.score,
            a.max_score,
            a.summary,
            a.sector_id,
            a.alert_id,
            a.alert_label,
            a.source_type,
            a.status,
            a.ai_feedback,
            a.colaborador_id,
            c.nome          AS colaborador_nome,
            c.matricula,
            c.id_huawei,
            c.supervisor,
            c.setor,
            c.escala,
            c.status        AS colaborador_status
        FROM audits a
        LEFT JOIN colaboradores c ON a.colaborador_id = c.id
        """
    )

    # ── 6. Composite indexes for common query patterns ──
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audits_sector_timestamp ON audits(sector_id, timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audits_colaborador_timestamp ON audits(colaborador_id, timestamp)"
    )
