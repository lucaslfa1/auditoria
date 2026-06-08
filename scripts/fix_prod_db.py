import os
import psycopg2
from psycopg2.extras import RealDictCursor
from backend.db.runtime_schema import ensure_runtime_schema

DATABASE_URL = os.environ["DATABASE_URL"]

def fix_prod_db():
    print("--- ATUALIZANDO ESQUEMA E CONFIGS NO NEON ---")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        # Usar RealDictCursor porque o runtime_schema.py acessa por nome da coluna (ex: row["id"])
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # 1. Garantir tabelas de runtime (huawei_sync_logs, etc)
            print("Executando ensure_runtime_schema...")
            ensure_runtime_schema(cursor)
            
            # 2. Corrigir VDN e habilitar sync
            print("Atualizando configuracoes (VDN=25, ENABLE=true)...")
            cursor.execute("UPDATE configuracoes SET valor = '25' WHERE chave = 'huawei_vdn'")
            cursor.execute("UPDATE configuracoes SET valor = 'true' WHERE chave = 'enable_huawei_sync'")
            
            conn.commit()
            print("Sucesso!")
    except Exception as e:
        print(f"Erro: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_prod_db()
