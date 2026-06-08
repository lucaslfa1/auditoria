from typing import Any
import re
import unicodedata

from db.schema_tools import get_existing_columns


MIGRATION_NAME = "20260312_009_force_fenix_as_default_sector"


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
    selected_columns = ["id", "setor"]
    optional_columns = ("escala", "tipo_escala", "organizacao_telefonia")
    for column_name in optional_columns:
        if column_name in columns:
            selected_columns.append(column_name)

    cursor.execute("SELECT {} FROM colaboradores".format(", ".join(selected_columns)))
    rows = cursor.fetchall()

    for row in rows:
        row_data = dict(zip(selected_columns, row))
        fenix_hints = " ".join(
            _normalize_text(row_data.get(column_name, ""))
            for column_name in ("setor", "escala", "tipo_escala", "organizacao_telefonia")
        )
        if "fenix" not in fenix_hints:
            continue

        if _normalize_text(row_data.get("setor", "")) == "fenix":
            continue

        cursor.execute(
            "UPDATE colaboradores SET setor = %s WHERE id = %s",
            ("FENIX", row_data["id"]),
        )
