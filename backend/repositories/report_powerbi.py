"""Relatórios para PowerBI e ferramentas externas.

Focado em retornar tabelas planas (denormalizadas) para facilitar o consumo
por ferramentas de BI sem necessidade de lógica complexa no DAX.
"""

import json
from datetime import datetime
from db.domain_constants import AUDIT_STATUS_APPROVED
import db.database as database


def _normalize_binary_detail_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "na", "n/a", "pending_manual"}:
        return "Atende"
    return "Não atende"

def get_powerbi_flat_audits(get_connection) -> list[dict]:
    """Retorna uma lista de todas as auditorias aprovadas com detalhes de colaborador e setor."""
    conn = get_connection()
    try:
        
        c = conn.cursor()

        sql = """
            SELECT
                a.id AS audit_id,
                a.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Sao_Paulo' AS data_hora,
                TO_CHAR(a.timestamp, 'YYYY-MM-DD') AS data,
                TO_CHAR(a.timestamp, 'HH24:MI') AS hora,
                a.operator_name AS operador,
                c.matricula,
                c.supervisor,
                c.escala,
                s.label AS setor,
                a.score AS nota_bruta,
                a.max_score AS nota_maxima,
                CASE 
                    WHEN a.max_score > 0 THEN ROUND(((a.score * 1.0 / a.max_score) * 100)::numeric, 2)
                    ELSE 0 
                END AS nota_percentual,
                a.sentiment_overall AS sentimento,
                a.audit_type AS tipo_auditoria
            FROM audits a
            LEFT JOIN colaboradores c ON c.nome = a.operator_name
            LEFT JOIN audit_sectors s ON s.id = a.sector_id
            WHERE a.status = %s
            ORDER BY a.timestamp DESC
        """
        c.execute(sql, [AUDIT_STATUS_APPROVED])

        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_powerbi_detailed_failures(get_connection) -> list[dict]:
    """Retorna uma tabela plana de cada critério avaliado (um critério por linha).
    
    Útil para o PowerBI fazer drill-down de quais perguntas estão sendo mais erradas.
    """
    conn = get_connection()
    try:
        
        c = conn.cursor()
        
        # Pegamos os dados brutos e expandimos o JSON no Python para manter compatibilidade total
        sql = "SELECT id, timestamp, operator_name, sector_id, details_json FROM audits WHERE status = %s"
            
        c.execute(sql, [AUDIT_STATUS_APPROVED])
        rows = c.fetchall()
        
        flat_results = []
        for row in rows:
            if not row["details_json"]:
                continue
                
            try:
                details = json.loads(row["details_json"])
                for d in details:
                    flat_results.append({
                        "audit_id": row["id"],
                        "timestamp": row["timestamp"],
                        "operador": row["operator_name"],
                        "setor_id": row["sector_id"],
                        "criterio": d.get("label", "?"),
                        "status": _normalize_binary_detail_status(d.get("status")),
                        "peso": d.get("weight", 0),
                        "valor_obtido": d.get("score", 0),
                        "justificativa": d.get("justification", "")
                    })
            except Exception:
                continue
                
        return flat_results
    finally:
        conn.close()
