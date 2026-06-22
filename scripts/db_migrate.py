"""Aplica as migrations de schema no banco configurado e imprime o runtime info.

COMO RODAR: `python scripts/db_migrate.py` (ou `npm run db:migrate`). Lê o
`DATABASE_URL` de `.env` (raiz) e `backend/.env` (este sobrescreve). Chama
`database.init_db()`, que roda de forma idempotente os passos pendentes de
`backend/db/migration_steps/`, e em seguida imprime `get_database_runtime_info()`
(host, versão, etc.) como JSON. Use após criar uma migration nova (ver
`create_db_migration.py`) ou ao preparar um ambiente do zero. Aponta para o
banco do `DATABASE_URL` ativo — confira que NÃO é produção antes de rodar.
"""
import json
import os
import sys


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_DIR, ".env"), override=False)
load_dotenv(os.path.join(BACKEND_DIR, ".env"), override=True)

import db.database as database  # noqa: E402


def main() -> int:
    database.init_db()
    runtime_info = database.get_database_runtime_info()
    print(json.dumps(runtime_info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
