import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from db.connection import get_connection


def check_db():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, timestamp, operator_name, score FROM audits ORDER BY id DESC LIMIT 5")
        rows = c.fetchall()
        print(f"Total rows found: {len(rows)}")
        for row in rows:
            print(f"ID: {row['id']}, Time: {row['timestamp']}, Op: {row['operator_name']}, Score: {row['score']}")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    check_db()
