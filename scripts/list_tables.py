import os
import psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cursor = conn.cursor()
cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
print([r[0] for r in cursor.fetchall()])
conn.close()
