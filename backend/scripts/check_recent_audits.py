import json
import logging
from db.connection import create_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_recent_audits():
    conn = create_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, timestamp, audit_date, operator_name, status, score, summary 
            FROM audits 
            WHERE (audit_date >= '2026-05-20' OR timestamp >= '2026-05-20T00:00:00')
            ORDER BY timestamp DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        logger.info(f"Encontradas {len(rows)} auditorias recentes.")
        for row in rows:
            logger.info(f"ID: {row[0]} | Data: {row[2] or row[1]} | Operador: {row[3]} | Status: {row[4]} | Score: {row[5]}")
            
    finally:
        conn.close()

if __name__ == "__main__":
    check_recent_audits()
