import sys
sys.path.append('backend')
import database

conn = database.get_connection()
try:
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes WHERE chave LIKE 'huawei_%'")
    for row in cur.fetchall():
        print(dict(row))
finally:
    conn.close()
