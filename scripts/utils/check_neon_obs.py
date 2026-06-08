import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes WHERE chave IN ('huawei_obs_ak', 'huawei_obs_sk')")
    for row in cur.fetchall():
        print(row)
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
