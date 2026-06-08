import os
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.environ["DATABASE_URL"]

parsed = urlparse(DATABASE_URL)
try:
    conn = psycopg2.connect(
        dbname=parsed.path[1:],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
        sslmode='require'
    )
    conn.autocommit = True
    c = conn.cursor()

    print("=== RELATÓRIO DE SAÚDE NEON DB ===")

    # 1. Total Size
    c.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
    print(f"Tamanho total do BD: {c.fetchone()[0]}")

    # 3. Connections
    c.execute("SELECT sum(numbackends) FROM pg_stat_database;")
    num_conns = c.fetchone()[0]
    c.execute("SHOW max_connections;")
    max_conns = c.fetchone()[0]
    print(f"Conexões em uso agora: {num_conns} (Max configurado no pool/servidor: {max_conns})")

    # 4. Table Size
    c.execute("""
        SELECT relname as "Table", 
               pg_size_pretty(pg_total_relation_size(relid)) As "Size",
               n_live_tup as "Rows"
        FROM pg_catalog.pg_stat_user_tables 
        ORDER BY pg_total_relation_size(relid) DESC;
    """)
    print("\n--- Tabelas e Volume de Dados ---")
    rows = c.fetchall()
    for row in rows:
        print(f"{row[0].ljust(25)} | {row[1].rjust(10)} | {row[2]} linhas")

    # 5. Data integrity checks
    print("\n--- Integridade e Alertas ---")
    try:
        c.execute("SELECT count(*) FROM audits")
        total_audits = c.fetchone()[0]
        c.execute("SELECT count(*) FROM audits WHERE score IS NULL")
        null_scores = c.fetchone()[0]
        c.execute("SELECT count(*) FROM audits WHERE status = 'failed'")
        failed = c.fetchone()[0]
        print(f"Total de Auditorias: {total_audits}")
        print(f"Auditorias descartadas/em erro (score NULL): {null_scores}")
        print(f"Auditorias status 'failed': {failed}")
    except Exception as e:
        print(f"Erro ao verificar audits: {e}")

    conn.close()
except Exception as e:
    print("FATAL ERROR connecting to database:", e)
