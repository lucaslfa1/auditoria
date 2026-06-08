import os

import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cursor = conn.cursor()
cursor.execute("UPDATE configuracoes SET valor = 'false' WHERE chave = 'sync_lock'")
conn.commit()
print("Lock limpo!")