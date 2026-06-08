import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from db.connection import get_connection

conn = get_connection()
c = conn.cursor()

print("--- Buscando Denise ---")
c.execute("SELECT username, role, supervisor_name FROM users WHERE username LIKE %s", ('%denise%',))
rows = c.fetchall()

if rows:
    for row in rows:
        print(f"Usuário: {row['username']}, Role: {row['role']}, Supervisor: {row['supervisor_name']}")
else:
    print("Nenhum usuário 'denise' encontrado.")

conn.close()
