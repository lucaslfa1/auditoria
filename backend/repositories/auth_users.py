"""Repositório de usuários de login (tabela `users` no Postgres/Neon).

Responsável por CRUD dos usuários que autenticam no sistema (admin/supervisor),
incluindo hash de senha com bcrypt. É a fonte canônica de credenciais — o antigo
`backend/auth_users.json` foi descontinuado.

Todas as funções recebem `get_connection` (factory de conexão psycopg2) por
injeção; o lookup é case-insensitive por `LOWER(username)`. O `role` é normalizado
via `normalize_user_role` para garantir um valor válido.

Sem custo de API (apenas acesso a banco + hashing bcrypt em CPU).
"""

from typing import Callable, Optional, Any

import bcrypt
import psycopg2

from repositories.common import normalize_user_role


ConnectionFactory = Callable[[], Any]


def get_user_by_username(get_connection: ConnectionFactory, username: str) -> Optional[dict]:
    """Busca um usuário por `username` (case-insensitive) e retorna a linha completa.

    `username` é normalizado (trim + lowercase) antes do `WHERE LOWER(username)`.
    Retorna o dict da linha (inclui `password_hash`) ou None se não existir.
    Efeito colateral: abre e fecha conexão de leitura ao banco.
    """
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
    """Cria um usuário com senha em texto claro convertida para hash bcrypt.

    Params relevantes: `password_clear` é a senha em texto puro (será hasheada com
    bcrypt antes de gravar); `role` é normalizado (default "admin"); demais campos
    (`supervisor_name`, `sector_id`, `escala`) são gravados como vieram.

    Retorna True em sucesso; False se `username` ficar vazio após trim ou se houver
    violação de unicidade (`psycopg2.IntegrityError`, ex.: username duplicado).
    Efeito colateral: INSERT em `users` + commit.
    """
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
    """Lista todos os usuários ordenados por username (case-insensitive).

    Retorna apenas campos não-sensíveis (id, username, role, supervisor_name,
    sector_id, escala) — NÃO inclui `password_hash`. Efeito colateral: leitura no
    banco.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute("SELECT id, username, role, supervisor_name, sector_id, escala FROM users ORDER BY LOWER(username) ASC")
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def delete_user(get_connection: ConnectionFactory, username: str) -> bool:
    """Remove o usuário com `username` correspondente (case-insensitive).

    Retorna True se alguma linha foi deletada, False caso contrário.
    Efeito colateral: DELETE em `users` + commit.
    """
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
    """Atualiza a senha do usuário (`new_password` em texto claro, hasheada com bcrypt).

    Retorna True se a linha foi atualizada, False se o usuário não existir.
    Efeito colateral: UPDATE em `users` + commit.
    """
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
    """Atualiza campos selecionados de um usuário (UPDATE parcial dinâmico).

    Só campos passados como não-None entram no SET; os demais ficam intactos.
    Regras de cada campo opcional (keyword-only):
    - `new_password`: ignorado se vazio/só espaços; senão hasheado com bcrypt.
    - `role`: normalizado; se virar None (role inválido), retorna False sem gravar.
    - `supervisor_name`, `sector_id`, `escala`: gravados como vieram.

    Retorna False se nenhum campo for fornecido (nada a atualizar) ou se nenhuma
    linha casar. Retorna True quando alguma linha é atualizada.
    Efeito colateral: UPDATE em `users` + commit.
    """
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
