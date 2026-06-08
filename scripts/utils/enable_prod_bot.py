import os
import psycopg2
import sys

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE configuracoes SET valor = 'true' WHERE chave = 'automacao_hibrida_ativa'")
    conn.commit()
    print("Bot de automacao habilitado com sucesso no banco de producao.")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
