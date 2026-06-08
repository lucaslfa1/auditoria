import os
import psycopg2
from dotenv import load_dotenv

load_dotenv('c:/Users/lucas.afonso/projetos/auditoria/.env')
DB_URL = os.getenv('DATABASE_URL')

def check_josiane():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT supervisor FROM colaboradores WHERE supervisor ILIKE '%josiane%';")
    print("Josiane supervisor name in db:", cur.fetchall())
    

    cur.execute("SELECT * FROM users;")
    print("Users dump:", cur.fetchall())
    cur.close()
    conn.close()

if __name__ == '__main__':
    check_josiane()
