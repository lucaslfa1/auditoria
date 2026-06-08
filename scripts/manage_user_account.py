"""Cria usuario ou atualiza senha sem hardcode de credenciais.

Exemplos:
  USER_PASSWORD="senha-temporaria" python scripts/manage_user_account.py \
    --action upsert --username usuario --role supervisor --supervisor-name "Nome" \
    --confirm-production

  python scripts/manage_user_account.py --action update-password --username usuario \
    --generate-temp-password --confirm-production
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env", override=False)
load_dotenv(ROOT / "backend" / ".env", override=False)

import db.database as database  # noqa: E402
from repositories.auth_users import create_user, update_user, update_user_password  # noqa: E402


def _is_production_database() -> bool:
    url = os.getenv("DATABASE_URL", "")
    host = urlparse(url).hostname or ""
    return "neon.tech" in host or "prod" in host.lower()


def _generate_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*?"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _resolve_password(args: argparse.Namespace) -> str:
    if args.generate_temp_password:
        return _generate_password()
    env_name = args.password_env
    password = os.getenv(env_name, "").strip()
    if not password:
        raise SystemExit(f"Configure {env_name} ou use --generate-temp-password.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Gerencia usuario sem senha hardcoded.")
    parser.add_argument("--action", choices=("create", "update-password", "upsert"), required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", default=None)
    parser.add_argument("--supervisor-name", default=None)
    parser.add_argument("--sector-id", default=None)
    parser.add_argument("--escala", default=None)
    parser.add_argument("--password-env", default="USER_PASSWORD")
    parser.add_argument("--generate-temp-password", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    args = parser.parse_args()

    if _is_production_database() and not args.confirm_production:
        raise SystemExit("DATABASE_URL parece producao/Neon. Reexecute com --confirm-production.")

    password = _resolve_password(args)
    username = args.username.strip()
    if not username:
        raise SystemExit("--username e obrigatorio.")

    if args.action == "create":
        ok = create_user(
            database.get_connection,
            username,
            password,
            args.role or "supervisor",
            args.supervisor_name or "",
            args.sector_id or "",
            args.escala or "",
        )
    elif args.action == "update-password":
        ok = update_user_password(database.get_connection, username, password)
    else:
        ok = update_user(
            database.get_connection,
            username,
            new_password=password,
            role=args.role,
            supervisor_name=args.supervisor_name,
            sector_id=args.sector_id,
            escala=args.escala,
        )
        if not ok:
            ok = create_user(
                database.get_connection,
                username,
                password,
                args.role or "supervisor",
                args.supervisor_name or "",
                args.sector_id or "",
                args.escala or "",
            )

    if not ok:
        raise SystemExit("Operacao nao aplicada.")
    print(f"Operacao aplicada para usuario: {username}")
    if args.generate_temp_password:
        print(f"Senha temporaria gerada: {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
