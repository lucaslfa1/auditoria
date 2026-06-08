from typing import Any

from db.runtime_schema import ensure_runtime_schema


MIGRATION_NAME = "20260306_002_runtime_schema"


def apply(cursor: Any) -> None:
    ensure_runtime_schema(cursor)
