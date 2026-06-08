import sys
import os
sys.path.append(os.path.abspath('backend'))
import dotenv
dotenv.load_dotenv(os.path.abspath('.env'))
from fastapi.testclient import TestClient
from main import app
from routers.auth import require_supervisor_or_admin
from db.connection import get_connection

app.dependency_overrides[require_supervisor_or_admin] = lambda: {"username": "admin", "role": "admin"}

def seed_audit():
    conn = get_connection()
    c = conn.cursor()
    # Limpar tabela para teste limpo
    c.execute("DELETE FROM audits")
    # Score None, Status approved
    c.execute("""
        INSERT INTO audits (
            timestamp, operator_name, score, max_score, summary,
            details_json, transcription_json, source_type, audit_scope, status, audio_quality
        ) VALUES (
            CURRENT_TIMESTAMP, 'Operador Teste', NULL, 10, 'Resumo',
            '[]', '[]', 'audio', 'call_quality', 'approved', '{}'
        ) RETURNING id
    """)
    audit_id = c.fetchone()[0]
    conn.commit()
    conn.close()
    return audit_id

seed_audit()
client = TestClient(app)
res_list = client.get("/api/gestores/auditorias?limit=50")
print("List Status:", res_list.status_code)
try:
    print(res_list.json())
except:
    print(res_list.text)

res_detail = client.get("/api/gestores/auditorias/1")
print("Detail Status:", res_detail.status_code)
