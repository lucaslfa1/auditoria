"""Runner de migracoes de schema (estilo Alembic, descoberta automatica).

Descobre cada modulo de migracao em `backend/db/migration_steps` (modulos cujo
nome comeca com "m"), exige `MIGRATION_NAME` + funcao `apply(cursor)` em cada um,
ordena por `MIGRATION_NAME` e aplica em sequencia apenas as ainda nao registradas
na tabela de controle `schema_migrations`. Cada migracao e commitada
individualmente (atomica por step). Chamado no bootstrap do banco.

Sem custo de API (apenas DDL/DML no PostgreSQL).
"""
from importlib import import_module
from pkgutil import iter_modules
from typing import Callable

from . import migration_steps
from .schema_tools import set_schema_metadata


def ensure_schema_migrations_table(cursor) -> None:
    """Cria a tabela de controle `schema_migrations` se ainda nao existir.

    Idempotente. Guarda o nome de cada migracao ja aplicada (PK) e o instante.
    Efeito colateral: DDL no DB.
    """
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_applied_migration_names(cursor) -> set[str]:
    """Retorna o conjunto de nomes de migracoes ja aplicadas.

    Garante a tabela de controle antes de consultar. Read-only sobre os dados
    (mas pode executar o DDL idempotente de criacao da tabela).
    """
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
    """Varre `migration_steps` e devolve [(MIGRATION_NAME, apply), ...] ordenado.

    Importa cada modulo cujo nome comeca com "m" (ignora subpacotes), exige que
    exponha `MIGRATION_NAME` (str) e `apply` (callable) — levanta RuntimeError se
    faltar — e tambem se houver nomes de migracao duplicados. Ordena por
    MIGRATION_NAME para garantir aplicacao deterministica. Executado uma vez no
    import do modulo (popula a constante `MIGRATIONS`).
    """
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


def _commit_migration_step(cursor) -> None:
    """Commita a conexao do cursor ao final de cada migration aplicada.

    Necessario porque algumas migrations (ex.: m20260518_004) escrevem via
    repositories.*, que abrem conexao PROPRIA do pool: sem commit por step,
    um banco limpo falha no bootstrap — a tabela criada por uma migration
    anterior ainda nao esta visivel para a conexao nova da migration seguinte.
    Tambem torna cada migration atomica (padrao Alembic), preservando o
    progresso ja aplicado quando uma migration posterior falha.
    """
    conn = getattr(cursor, "connection", None)
    if conn is not None and hasattr(conn, "commit"):
        conn.commit()


def run_pending_migrations(cursor) -> list[str]:
    """Aplica, em ordem, todas as migracoes ainda nao registradas e retorna seus nomes.

    Para cada migracao pendente: roda `apply(cursor)`, marca como aplicada em
    `schema_migrations` e commita o step (ver `_commit_migration_step`). Ao final,
    grava em `schema_metadata` os metadados `migration.latest_known` (ultima
    conhecida) e, se algo foi aplicado, `migration.last_applied`.

    Efeitos colaterais: DDL/DML e commits no DB. Retorna a lista de nomes
    efetivamente executados nesta chamada (vazia se o banco ja estava em dia).
    """
    ensure_schema_migrations_table(cursor)
    applied = get_applied_migration_names(cursor)
    executed: list[str] = []

    for name, migration_fn in MIGRATIONS:
        if name in applied:
            continue
        migration_fn(cursor)
        _mark_migration_applied(cursor, name)
        _commit_migration_step(cursor)
        executed.append(name)

    if MIGRATIONS:
        set_schema_metadata(cursor, "migration.latest_known", MIGRATIONS[-1][0])
    if executed:
        set_schema_metadata(cursor, "migration.last_applied", executed[-1])

    return executed
