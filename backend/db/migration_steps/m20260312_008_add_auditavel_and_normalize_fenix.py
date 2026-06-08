from typing import Any
import re
import unicodedata

from db.schema_tools import get_existing_columns


MIGRATION_NAME = "20260312_008_add_auditavel_and_normalize_fenix"


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", "", normalized)


def apply(cursor: Any) -> None:
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='colaboradores'"
    )
    if cursor.fetchone() is None:
        return

    columns = get_existing_columns(cursor, "colaboradores")
    added_auditavel = False
    if "auditavel" not in columns:
        cursor.execute("ALTER TABLE colaboradores ADD COLUMN auditavel INTEGER DEFAULT 1")
        columns.add("auditavel")
        added_auditavel = True

    has_tipo_escala = "tipo_escala" in columns
    has_escala = "escala" in columns
    if not has_tipo_escala and not has_escala and not added_auditavel:
        return

    selected_columns = ["id", "status", "setor"]
    if has_escala:
        selected_columns.append("escala")
    if has_tipo_escala:
        selected_columns.append("tipo_escala")
    if "auditavel" in columns:
        selected_columns.append("auditavel")

    cursor.execute(
        "SELECT {} FROM colaboradores".format(", ".join(selected_columns))
    )
    rows = cursor.fetchall()

    for row in rows:
        row_data = dict(zip(selected_columns, row))
        updates: list[str] = []
        params: list[object] = []

        normalized_status = _normalize_text(row_data.get("status", ""))
        if added_auditavel:
            auditavel_value = 1 if normalized_status in {"", "ativo", "active", "normal"} else 0
            updates.append("auditavel = %s")
            params.append(auditavel_value)

        operation_hint = _normalize_text(
            "{} {}".format(row_data.get("escala", ""), row_data.get("tipo_escala", ""))
        )
        if "fenix" in operation_hint:
            current_sector = _normalize_text(row_data.get("setor", ""))
            if current_sector != "fenix":
                updates.append("setor = %s")
                params.append("FENIX")

        if not updates:
            continue

        params.append(row_data["id"])
        cursor.execute(
            "UPDATE colaboradores SET {} WHERE id = %s".format(", ".join(updates)),
            params,
        )
