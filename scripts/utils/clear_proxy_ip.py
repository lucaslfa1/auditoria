import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE configuracoes SET valor = '' WHERE chave = 'huawei_proxy_ip'")
    conn.commit()
    print("huawei_proxy_ip limpo com sucesso!")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
