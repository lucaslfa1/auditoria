import json
import logging
from db.connection import create_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_queue():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, status, metadata_json, criado_em 
            FROM fila_revisao_classificacao 
            WHERE status NOT IN ('audited', 'reviewed', 'auto_resolved')
            ORDER BY criado_em DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        logger.info(f"Fila de triagem: {len(rows)} itens ativos.")
        for row in rows:
            meta = row[2] if isinstance(row[2], dict) else json.loads(row[2])
            logger.info(f"ID: {row[0]} | Status: {row[1]} | Data Áudio: {meta.get('audio_date')} | Criado em: {row[3]}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    check_queue()
