import sys
import os
sys.path.append(os.path.abspath('backend'))
import database

def check_config():
    conn = database.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes WHERE chave LIKE 'huawei_%%'")
    rows = cur.fetchall()
    for row in rows:
        print(f"{row[0]}: {row[1]}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    check_config()
