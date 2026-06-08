from typing import Any


MIGRATION_NAME = "20260312_014_sync_colaborador_auditavel_with_status"


def apply(cursor: Any) -> None:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'colaboradores'
        LIMIT 1
        """
    )
    if cursor.fetchone() is None:
        return

    cursor.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='colaboradores'"
    )
    columns = {row[0] for row in cursor.fetchall()}
    if "status" not in columns or "auditavel" not in columns:
        return

    cursor.execute(
        """
        UPDATE colaboradores
        SET auditavel = CASE
            WHEN UPPER(TRIM(COALESCE(status, ''))) = 'ATIVO' THEN 1
            ELSE 0
        END
        WHERE COALESCE(auditavel, -1) != CASE
            WHEN UPPER(TRIM(COALESCE(status, ''))) = 'ATIVO' THEN 1
            ELSE 0
        END
        """
    )
