import os
import sys
import argparse
from datetime import datetime, timezone, timedelta

# Adiciona a raiz do projeto (D:\auditoria) ao path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))

sys.path.insert(0, project_root)

import database

def main():
    parser = argparse.ArgumentParser(description="Reconcilia ciclos de automacao com heartbeat expirado.")
    parser.add_argument("--apply", action="store_true", help="Aplica as alteracoes no banco (default: dry-run)")
    args = parser.parse_args()

    print(f"Modo: {'APPLY' if args.apply else 'DRY-RUN'}")

    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Contar totais antes
        cursor.execute("SELECT status, COUNT(*) FROM automation_cycle_runs GROUP BY status")
        counts_before = dict(cursor.fetchall())
        print(f"Contagens de ciclos ANTES: {counts_before}")
        
        # 2. Encontrar stale runs
        # Margem de 15 minutos adicionais em relacao ao now() para lidar com atrasos com margem
        # status = 'running' e last_heartbeat_at (ou started_at) < now() - 15 min
        cursor.execute("""
            SELECT id, last_heartbeat_at, started_at 
            FROM automation_cycle_runs 
            WHERE status = 'running'
            AND COALESCE(last_heartbeat_at, started_at) < CURRENT_TIMESTAMP - interval '15 minutes'
        """)
        stale_runs = cursor.fetchall()
        
        print(f"Encontrados {len(stale_runs)} ciclos estagnados.")
        
        if args.apply and stale_runs:
            ids = tuple([r[0] for r in stale_runs])
            cursor.execute("""
                UPDATE automation_cycle_runs 
                SET status = 'stale', 
                    stage = 'stale',
                    finished_at = CURRENT_TIMESTAMP, 
                    error_message = 'Reconciliado retroativamente por script',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id IN %s
            """, (ids,))
            
            updated = cursor.rowcount
            print(f"Atualizados {updated} registros para 'stale'.")
            conn.commit()
            
            # Contagens depois
            cursor.execute("SELECT status, COUNT(*) FROM automation_cycle_runs GROUP BY status")
            counts_after = dict(cursor.fetchall())
            print(f"Contagens de ciclos DEPOIS: {counts_after}")
        elif not args.apply:
            print("Execute com --apply para persistir as alteracoes.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()
