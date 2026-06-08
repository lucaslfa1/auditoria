import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import db.database as database

def release():
    conn = database.get_connection()
    c = conn.cursor()
    c.execute("UPDATE configuracoes SET valor = 'false' WHERE chave = 'sync_lock'")
    conn.commit()
    print("Lock removido")

if __name__ == "__main__":
    release()
