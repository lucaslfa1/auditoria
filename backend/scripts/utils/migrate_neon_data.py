import os
import psycopg2

old_dsn = os.environ["OLD_DATABASE_URL"]
new_dsn = os.environ["NEW_DATABASE_URL"]

print('Connecting to databases...')
conn_old = psycopg2.connect(old_dsn)
conn_new = psycopg2.connect(new_dsn)

cur_old = conn_old.cursor()
cur_new = conn_new.cursor()

cur_old.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
tables = [r[0] for r in cur_old.fetchall()]

cur_new.execute('SET session_replication_role = replica;')

print('Truncating tables in new database...')
for table in tables:
    cur_new.execute(f'TRUNCATE TABLE "{table}" CASCADE')

print('Copying data...')
for table in tables:
    cur_old.execute(f'SELECT * FROM "{table}"')
    rows = cur_old.fetchall()
    if rows:
        colnames = [desc[0] for desc in cur_old.description]
        col_list = ', '.join(f'"{c}"' for c in colnames)
        val_list = ', '.join(['%s'] * len(colnames))
        
        insert_query = f'INSERT INTO "{table}" ({col_list}) VALUES ({val_list})'
        cur_new.executemany(insert_query, rows)
        print(f'Copied {len(rows)} rows to {table}')

cur_new.execute('SET session_replication_role = DEFAULT;')
conn_new.commit()

# Reset sequences based on the max value in the table
cur_old.execute("SELECT table_name, column_name FROM information_schema.columns WHERE column_default LIKE 'nextval(%'")
seq_cols = cur_old.fetchall()

for table_name, column_name in seq_cols:
    cur_new.execute(f'SELECT MAX("{column_name}") FROM "{table_name}"')
    max_val = cur_new.fetchone()[0]
    if max_val:
        # Extract sequence name from column_default
        cur_old.execute(f"SELECT column_default FROM information_schema.columns WHERE table_name='{table_name}' AND column_name='{column_name}'")
        col_def = cur_old.fetchone()[0]
        # nextval('sequence_name'::regclass)
        seq_name = col_def.split("'")[1]
        
        cur_new.execute(f"SELECT setval('{seq_name}', {max_val + 1}, false)")
        print(f"Updated sequence {seq_name} to {max_val + 1}")

conn_new.commit()

conn_old.close()
conn_new.close()
print('Migration completed successfully.')
