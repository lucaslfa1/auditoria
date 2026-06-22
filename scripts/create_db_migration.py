"""Cria (scaffold) o arquivo de uma nova migration de schema.

COMO RODAR: `python scripts/create_db_migration.py <slug-da-migracao>`
(ou `npm run db:new-migration <slug>`). Gera
`backend/db/migration_steps/mAAAAMMDD_NNN_<slug>.py` com a sequência do dia
auto-incrementada e um `apply(cursor)` vazio para você preencher (use `%s` como
placeholder — psycopg2/PostgreSQL). NÃO toca no banco: só escreve o arquivo.
Depois rode `scripts/db_migrate.py` para aplicar.
"""
import re
import sys
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT_DIR / "backend" / "db" / "migration_steps"
FILENAME_PATTERN = re.compile(r"^m(?P<date>\d{8})_(?P<seq>\d{3})_(?P<slug>[a-z0-9_]+)\.py$")


def _slugify(raw_value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (raw_value or "").strip().lower()).strip("_")
    return slug


def _next_sequence(date_prefix: str) -> int:
    existing_sequences: list[int] = []
    for path in MIGRATIONS_DIR.glob("m*.py"):
        match = FILENAME_PATTERN.match(path.name)
        if not match:
            continue
        if match.group("date") != date_prefix:
            continue
        existing_sequences.append(int(match.group("seq")))
    return (max(existing_sequences) + 1) if existing_sequences else 1


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python scripts/create_db_migration.py <slug-da-migracao>")
        return 1

    slug = _slugify(" ".join(argv[1:]))
    if not slug:
        print("Slug invalido. Use letras, numeros e separadores simples.")
        return 1

    date_prefix = datetime.now().strftime("%Y%m%d")
    sequence = _next_sequence(date_prefix)
    migration_name = f"{date_prefix}_{sequence:03d}_{slug}"
    filename = f"m{migration_name}.py"
    target_path = MIGRATIONS_DIR / filename

    if target_path.exists():
        print(f"Migracao ja existe: {target_path}")
        return 1

    template = f'''from typing import Any


MIGRATION_NAME = "{migration_name}"


def apply(cursor: Any) -> None:
    """
    Descreva aqui a alteracao de schema/dados.
    Use %s para placeholders (PostgreSQL/psycopg2).
    """
    pass
'''

    target_path.write_text(template, encoding="utf-8")
    print(target_path)
    print(f"Migration name: {migration_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
