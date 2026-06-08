import sys
import os
sys.path.insert(0, os.path.abspath('backend'))
import database

def check():
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT chave, valor FROM configuracoes WHERE chave IN ('automacao_hibrida_ativa', 'huawei_d1_enabled', 'telefonia_cron_sync_ativa')")
        for row in cur.fetchall():
            print(f"{row[0]}: {row[1]}")
    finally:
        conn.close()

if __name__ == '__main__':
    check()
