import os
from dotenv import load_dotenv
import psycopg2
from pprint import pprint
load_dotenv('backend/.env')

conn = psycopg2.connect(os.getenv('DATABASE_URL'))
cursor = conn.cursor()
try:
    cursor.execute("SELECT chave, valor, descricao, atualizado_em FROM configuracoes")
    rows = cursor.fetchall()
    data = {
        row["chave"]: {
            "valor": row["valor"],
            "descricao": row["descricao"],
        }
        for row in rows
    }
    print("Success")
    pprint(data)
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    conn.close()
