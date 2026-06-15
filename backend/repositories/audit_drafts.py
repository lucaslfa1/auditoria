"""Repository de rascunhos de auditoria (tabela `audit_drafts`).

Rascunho da edicao manual de uma auditoria, 1 por (`input_hash`, `user_id`),
salvo antes de o auditor gravar o resultado final. Extraido de
`repositories.audits` (que reexporta estes nomes p/ compat).

Convencao: cada funcao recebe `get_connection` por injecao e abre/fecha a
propria conexao (igual ao resto da camada repositories).
"""
from typing import Optional


def upsert_audit_draft(get_connection, input_hash: str, user_id: str, details_json: str, transcription_json: str) -> None:
    """Salva/atualiza o rascunho de auditoria manual do usuário (1 por input_hash+user)."""
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
    """Recupera o rascunho de auditoria do usuário para a gravação, se existir."""
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
