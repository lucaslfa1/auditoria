import os
import sys
import psycopg2
from urllib.parse import urlparse

DATABASE_URL = os.environ["DATABASE_URL"]

def check_supervisors():
    parsed = urlparse(DATABASE_URL)
    conn = psycopg2.connect(
        dbname=parsed.path[1:],
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port,
        sslmode='require'
    )
    cur = conn.cursor()
    cur.execute("SELECT username, role, supervisor_name FROM users WHERE role = 'supervisor';")
    users = cur.fetchall()
    print("Supervisors in USERS table:")
    for u in users:
        print(f" - {u[0]} (Role: {u[1]}, Map: {u[2]})")
        
    cur.execute("SELECT DISTINCT supervisor FROM colaboradores WHERE supervisor IS NOT NULL AND supervisor != '';")
    colabs_supervisors = cur.fetchall()
    print("\nSupervisors assigned to operators in COLABORADORES table:")
    for cs in colabs_supervisors:
        print(f" - {cs[0]}")
    
    cur.close()
    conn.close()

if __name__ == '__main__':
    check_supervisors()
