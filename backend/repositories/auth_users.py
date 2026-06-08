from typing import Callable, Optional, Any

import bcrypt
import psycopg2

from repositories.common import normalize_user_role


ConnectionFactory = Callable[[], Any]


def get_user_by_username(get_connection: ConnectionFactory, username: str) -> Optional[dict]:
    normalized_username = str(username or "").strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE LOWER(username) = %s", (normalized_username,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_user(
    get_connection: ConnectionFactory,
    username: str,
    password_clear: str,
    role: str = "admin",
    supervisor_name: str = "",
    sector_id: str = "",
    escala: str = "",
) -> bool:
    normalized_role = normalize_user_role(role, default="admin")
    original_username = str(username or "").strip()
    if not original_username:
        return False
    password_hash = bcrypt.hashpw(password_clear.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, supervisor_name, sector_id, escala) VALUES (%s, %s, %s, %s, %s, %s)",
            (original_username, password_hash, normalized_role, supervisor_name, sector_id, escala),
        )
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        return False
    finally:
        if conn is not None:
            conn.close()


def list_users(get_connection: ConnectionFactory) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, username, role, supervisor_name, sector_id, escala FROM users ORDER BY LOWER(username) ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_user(get_connection: ConnectionFactory, username: str) -> bool:
    normalized_username = str(username or "").strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE LOWER(username) = %s", (normalized_username,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def update_user_password(get_connection: ConnectionFactory, username: str, new_password: str) -> bool:
    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    normalized_username = str(username or "").strip().lower()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE LOWER(username) = %s",
            (password_hash, normalized_username),
        )
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def update_user(
    get_connection: ConnectionFactory,
    username: str,
    *,
    new_password: Optional[str] = None,
    role: Optional[str] = None,
    supervisor_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    escala: Optional[str] = None,
) -> bool:
    normalized_username = str(username or "").strip().lower()
    sets = []
    params = []
    if new_password is not None and new_password.strip():
        password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        sets.append("password_hash = %s")
        params.append(password_hash)
    if role is not None:
        normalized_role = normalize_user_role(role, default=None)
        if normalized_role is None:
            return False
        sets.append("role = %s")
        params.append(normalized_role)
    if supervisor_name is not None:
        sets.append("supervisor_name = %s")
        params.append(supervisor_name)
    if sector_id is not None:
        sets.append("sector_id = %s")
        params.append(sector_id)
    if escala is not None:
        sets.append("escala = %s")
        params.append(escala)
    if not sets:
        return False
    params.append(normalized_username)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE LOWER(username) = %s",
            params,
        )
        updated = cursor.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()
