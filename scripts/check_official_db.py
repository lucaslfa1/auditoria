
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ["DATABASE_URL"]

def check_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Verificar se o sync está habilitado na tabela configuracoes
            cursor.execute("SELECT chave, valor FROM configuracoes WHERE chave IN ('huawei_ak', 'huawei_vdn', 'enable_huawei_sync')")
            configs = cursor.fetchall()
            print("--- CONFIGURACOES NO BANCO ---")
            for c in configs:
                print(f"{c['chave']}: {c['valor']}")
            
            # 2. Verificar o log de sincronismo da Huawei (ultimos 10)
            cursor.execute("SELECT call_id, sincronizado_em FROM huawei_sync_log ORDER BY sincronizado_em DESC LIMIT 10")
            logs = cursor.fetchall()
            print("\n--- ULTIMOS LOGS HUAWEI SYNC ---")
            for l in logs:
                print(f"CallID: {l['call_id']} | Data: {l['sincronizado_em']}")
                
            # 3. Verificar se há itens na fila de revisão vindos do Huawei
            cursor.execute("SELECT id, nome_arquivo, criado_em FROM fila_revisao_classificacao WHERE metadata->>'origem' = 'huawei_sync' ORDER BY criado_em DESC LIMIT 5")
            fila = cursor.fetchall()
            print("\n--- FILA DE REVISAO (HUAWEI) ---")
            for f in fila:
                print(f"ID: {f['id']} | Arquivo: {f['nome_arquivo']} | Criado: {f['criado_em']}")

    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
