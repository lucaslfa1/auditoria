import logging
from typing import Callable, Optional, Any

from db.runtime_schema import ensure_gestor_feedbacks_table

logger = logging.getLogger(__name__)

ConnectionFactory = Callable[[], Any]


def save_gestor_feedback(
    get_connection: ConnectionFactory,
    audit_id: int,
    gestor_nome: str,
    feedback_texto: str,
    pontos_melhoria: str,
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_gestor_feedbacks_table(cursor)

        cursor.execute("SELECT id FROM gestor_feedbacks WHERE audit_id = %s", (audit_id,))
        row = cursor.fetchone()

        if row:
            cursor.execute(
                """
                UPDATE gestor_feedbacks
                SET gestor_nome = %s, feedback_texto = %s, pontos_melhoria = %s, criado_em = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (gestor_nome, feedback_texto, pontos_melhoria, row[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO gestor_feedbacks (audit_id, gestor_nome, feedback_texto, pontos_melhoria)
                VALUES (%s, %s, %s, %s)
                """,
                (audit_id, gestor_nome, feedback_texto, pontos_melhoria),
            )

        conn.commit()
        return True
    except Exception as exc:
        logger.warning("Erro ao salvar feedback do gestor: %s", exc)
        return False
    finally:
        conn.close()


def get_gestor_feedback(get_connection: ConnectionFactory, audit_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        ensure_gestor_feedbacks_table(cursor)
        cursor.execute("SELECT * FROM gestor_feedbacks WHERE audit_id = %s", (audit_id,))
        row = cursor.fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "audit_id": row["audit_id"],
            "gestor_nome": row["gestor_nome"],
            "feedback_texto": row["feedback_texto"],
            "pontos_melhoria": row["pontos_melhoria"],
            "criado_em": row["criado_em"],
        }
    except Exception as exc:
        logger.warning("Erro ao buscar feedback do gestor: %s", exc)
        return None
    finally:
        conn.close()
