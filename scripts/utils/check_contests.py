import sys
sys.path.insert(0, 'backend')
from database import get_connection

def check():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT status, count(*) FROM audits GROUP BY status")
    rows = cur.fetchall()
    print("--- Status das Auditorias ---")
    for row in rows:
        print(f"{row[0]}: {row[1]}")
    
    conn.close()

if __name__ == "__main__":
    check()
