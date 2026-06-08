import sys
from typing import Optional

def append_to_file(filepath, content):
    with open(filepath, 'a', encoding='utf-8') as f:
        f.write(content)

repo_content = '''
def list_pending_dispatch_audits(get_connection, older_than_hours: Optional[int] = None) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT
                a.*,
                c.nome AS colaborador_nome,
                c.supervisor,
                c.setor,
                c.escala,
                c.matricula
            FROM audits a
            LEFT JOIN colaboradores c ON a.colaborador_id = c.id
            WHERE a.status = 'awaiting_pair'
        """
        
        if older_than_hours is not None:
            query += f" AND (a.timestamp::timestamp <= NOW() - INTERVAL '{older_than_hours} hours')"
            
        query += " ORDER BY a.timestamp DESC"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()

def upsert_audit_draft(get_connection, input_hash: str, user_id: str, details_json: str, transcription_json: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_drafts (input_hash, user_id, details_json, transcription_json, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (input_hash, user_id) 
            DO UPDATE SET 
                details_json = EXCLUDED.details_json,
                transcription_json = EXCLUDED.transcription_json,
                updated_at = EXCLUDED.updated_at
            """,
            (input_hash, user_id, details_json, transcription_json)
        )
        conn.commit()
    finally:
        conn.close()

def get_audit_draft(get_connection, input_hash: str, user_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM audit_drafts WHERE input_hash = %s AND user_id = %s",
            (input_hash, user_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
'''

append_to_file('backend/repositories/audits.py', repo_content)
