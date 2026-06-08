import psycopg2
import os
from dotenv import load_dotenv

load_dotenv('backend/.env', override=True)
load_dotenv('.env', override=True)

try:
    db_url = os.getenv('DATABASE_URL')
    print(f"Testando conexao usando URL: {db_url.split('@')[1] if '@' in db_url else 'Vazia'}")
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    cursor.execute('SELECT version();')
    version = cursor.fetchone()
    print(f"SUCESSO: Conectado ao PostgreSQL!\nVersao: {version[0]}")
    conn.close()
except Exception as e:
    print(f"ERRO: Falha ao conectar ao banco de dados PostgreSQL.\nDetalhes: {e}")
