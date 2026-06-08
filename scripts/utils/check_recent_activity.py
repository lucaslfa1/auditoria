import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    print("--- ULTIMOS SYNC LOGS ---")
    cur.execute("SELECT call_id, agent_id, status, failure_reason, sincronizado_em FROM huawei_sync_logs ORDER BY sincronizado_em DESC LIMIT 10")
    for row in cur.fetchall():
        print(row)
        
    print("\n--- ULTIMOS ITENS NA FILA DE REVISAO ---")
    cur.execute("SELECT nome_arquivo, status, atualizado_em FROM fila_revisao_classificacao ORDER BY atualizado_em DESC LIMIT 10")
    for row in cur.fetchall():
        print(row)
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
