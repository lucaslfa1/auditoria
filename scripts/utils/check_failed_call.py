import os
import psycopg2
import json

DATABASE_URL = os.environ["DATABASE_URL"]
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT * FROM fila_revisao_classificacao WHERE nome_arquivo LIKE '%1778000155_68508%' LIMIT 1")
row = cur.fetchone()
if row:
    colnames = [desc[0] for desc in cur.description]
    print(dict(zip(colnames, row)))
else:
    print("Not found in fila_revisao_classificacao. Checking audits...")
    cur.execute("SELECT dados_raw FROM audits WHERE call_id = '1778000155-68508' LIMIT 1")
    row = cur.fetchone()
    if row:
        print(json.dumps(row[0], indent=2))
    else:
        print("Not found.")
conn.close()
