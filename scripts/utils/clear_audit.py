import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
import database

def clear():
    conn = database.get_connection()
    c = conn.cursor()
    # Decrement audit count to 0 for a specific user this month to trigger download
    c.execute("SELECT id FROM audits WHERE operator_name = 'Caio das Virgens Melo' ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    if row:
        c.execute("UPDATE audits SET operator_name = 'Caio das Virgens Melo (Test)' WHERE id = %s", (row[0],))
        conn.commit()
        print("OK: Removed one audit from Caio to trigger new download")
    else:
        print("No audit found")

clear()
