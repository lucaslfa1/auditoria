import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes WHERE chave LIKE 'huawei_%' OR chave LIKE 'automacao_%'")
    for row in cur.fetchall():
        print(f"{row[0]}: {row[1]}")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
