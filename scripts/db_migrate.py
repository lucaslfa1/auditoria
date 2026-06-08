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
