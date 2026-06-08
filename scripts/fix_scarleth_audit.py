from db.database import get_connection
import json

def update_audit():
    conn = get_connection()
    cur = conn.cursor()
    
    # ID já identificado anteriormente
    audit_id = 24
    print(f"Atualizando auditoria ID {audit_id}")

    motivo = "Auditoria ZERADA: Falha grave de segurança. A operadora solicitou o CPF logo após pedir a senha, sem aguardar a resposta ou negativa do motorista (regra Sentinel - Senha ou CPF). Isso invalida o procedimento de validação de segurança."
    
    # Atualizar score e status. Removido updated_at para evitar erro de schema.
    cur.execute("""
        UPDATE audits 
        SET score = 0, 
            status = 'discarded',
            summary = %s || '\n\n' || COALESCE(summary, ''),
            ai_feedback = %s || '\n\n' || COALESCE(ai_feedback, '')
        WHERE id = %s
    """, (motivo, motivo, audit_id))
    
    conn.commit()
    print(f"Auditoria {audit_id} zerada e descartada com sucesso.")

if __name__ == "__main__":
    update_audit()
