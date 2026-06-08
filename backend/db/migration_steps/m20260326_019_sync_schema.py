from typing import Any

from db.runtime_schema import ensure_runtime_schema


MIGRATION_NAME = "20260326_019_sync_schema"


def apply(cursor: Any) -> None:
    # Chama o ensure_runtime_schema que possui CREATE TABLE IF NOT EXISTS
    # e varios chamados de ensure_column para garantir que qualquer coluna
    # adicionada via codigo no runtime_schema seja refletida no Postgres
    ensure_runtime_schema(cursor)
