import os
import psycopg2
import json

DATABASE_URL = os.environ["DATABASE_URL"]
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()
cur.execute("SELECT call_id, data_json FROM ligacoes ORDER BY data_chamada DESC LIMIT 2")
for row in cur.fetchall():
    print(f"Call ID: {row[0]}")
    print(json.dumps(row[1], indent=2))
conn.close()
