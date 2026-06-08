import sys
import os
sys.path.append(os.path.abspath('backend'))
import database

def check_ops():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id_huawei, nome FROM colaboradores WHERE id_huawei IS NOT NULL AND id_huawei != ''")
    rows = cur.fetchall()
    print(f"Encontrados {len(rows)} operadores com ID Huawei")
    for row in rows:
        print(f"- {row[1]} (ID: {row[0]})")
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_ops()
