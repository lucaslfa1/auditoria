import os
import sys
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes WHERE chave IN ('automacao_intervalo_segundos', 'huawei_horas_retroativas', 'max_auditorias_por_operador')")
    for row in cur.fetchall():
        print(f"{row[0]}: {row[1]}")
    conn.close()
except Exception as e:
    print(f"Erro: {e}")
