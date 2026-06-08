from importlib import import_module
from pkgutil import iter_modules
from typing import Callable

from . import migration_steps
from .schema_tools import set_schema_metadata


def ensure_schema_migrations_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_applied_migration_names(cursor) -> set[str]:
    ensure_schema_migrations_table(cursor)
    cursor.execute("SELECT name FROM schema_migrations")
    return {str(row[0]) for row in cursor.fetchall()}


def _mark_migration_applied(cursor, name: str) -> None:
    if True:
        cursor.execute(
            "INSERT INTO schema_migrations (name) VALUES (%s) ON CONFLICT DO NOTHING",
            (name,),
        )
    else:
        cursor.execute(
            "INSERT INTO schema_migrations (name) VALUES (%s)",
            (name,),
        )


def _discover_migrations() -> list[tuple[str, Callable]]:
    discovered: list[tuple[str, Callable]] = []
    package_prefix = f"{migration_steps.__name__}."

    for module_info in sorted(iter_modules(migration_steps.__path__), key=lambda item: item.name):
        if module_info.ispkg or not module_info.name.startswith("m"):
            continue

        module = import_module(f"{package_prefix}{module_info.name}")
        migration_name = getattr(module, "MIGRATION_NAME", "")
        apply_fn = getattr(module, "apply", None)
        if not migration_name or not callable(apply_fn):
            raise RuntimeError(f"Migracao invalida em {module_info.name}: MIGRATION_NAME/apply ausentes")
        discovered.append((str(migration_name), apply_fn))

    migration_names = [name for name, _ in discovered]
    if len(migration_names) != len(set(migration_names)):
        raise RuntimeError("Ha nomes de migracao duplicados em backend/db/migration_steps")

    discovered.sort(key=lambda item: item[0])
    return discovered


MIGRATIONS = _discover_migrations()


def run_pending_migrations(cursor) -> list[str]:
    ensure_schema_migrations_table(cursor)
    applied = get_applied_migration_names(cursor)
    executed: list[str] = []

    for name, migration_fn in MIGRATIONS:
        if name in applied:
            continue
        migration_fn(cursor)
        _mark_migration_applied(cursor, name)
        executed.append(name)

    if MIGRATIONS:
        set_schema_metadata(cursor, "migration.latest_known", MIGRATIONS[-1][0])
    if executed:
        set_schema_metadata(cursor, "migration.last_applied", executed[-1])

    return executed
