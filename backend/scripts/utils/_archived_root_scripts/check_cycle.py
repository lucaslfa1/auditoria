import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath('backend'))
import database

def check_cycle():
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        
        print(f"\n--- Status em {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        
        # Últimos Ciclos de Automação
        print("\n[Últimos Ciclos - automation_cycle_runs]")
        cur.execute("SELECT id, source, status, stage, started_at, finished_at, baixadas, auditadas FROM automation_cycle_runs ORDER BY started_at DESC LIMIT 5")
        rows = cur.fetchall()
        print("  ID  | Source          | Status   | Stage          | Início (UTC)        | Fim (UTC)           | Baixadas | Auditadas")
        print("  ----|-----------------|----------|----------------|---------------------|---------------------|----------|----------")
        for row in rows:
            inicio = row[4].strftime('%H:%M:%S') if row[4] else "N/A"
            fim = row[5].strftime('%H:%M:%S') if row[5] else "N/A"
            print(f"  {row[0]:<4}| {row[1]:<16}| {row[2]:<9}| {row[3]:<15}| {inicio:<20}| {fim:<20}| {row[6]:<9}| {row[7]}")

        # Status Huawei D-1
        print("\n[Status Huawei D-1 - huawei_d_minus_1_runs]")
        cur.execute("SELECT date_str, status, attempts, last_attempt_at, last_error, downloaded_count FROM huawei_d_minus_1_runs ORDER BY date_str DESC LIMIT 5")
        rows = cur.fetchall()
        print("  Data     | Status      | Tent. | Última Tent. (UTC)  | Erro                 | Baixadas")
        print("  ---------|-------------|-------|---------------------|----------------------|---------")
        for row in rows:
            ultima = row[3].strftime('%H:%M:%S') if row[3] else "N/A"
            erro = (row[4][:20] + '..') if row[4] and len(row[4]) > 20 else (row[4] or "")
            print(f"  {row[0]:<9}| {row[1]:<12}| {row[2]:<6}| {ultima:<20}| {erro:<21}| {row[5]}")

    except Exception as e:
        print(f"Erro ao consultar banco: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    check_cycle()