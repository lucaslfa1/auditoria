import sys
import os
import json

sys.path.insert(0, os.path.abspath('backend'))
import database

def check_db():
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        print("--- Esquema transcript_candidates ---")
        cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'transcript_candidates'")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]}")
            
        print("\n--- Últimas Tentativas Rejeitadas (huawei_telemetry_events) ---")
        cur.execute("SELECT call_id, event_type, context, timestamp FROM huawei_telemetry_events ORDER BY timestamp DESC LIMIT 10")
        for row in cur.fetchall():
            context = json.loads(row[2]) if row[2] else {}
            print(f"  {row[3].strftime('%H:%M:%S')} | {row[1]:<20} | {row[0]} | {context}")

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    check_db()
