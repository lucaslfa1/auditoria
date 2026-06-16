"""Repositório do feedback do gestor sobre auditorias.

Persiste e lê a tabela ``gestor_feedbacks`` — uma observação textual que o
gestor/supervisor anexa a uma auditoria já avaliada (texto livre + pontos de
melhoria). É uma relação 1:1 com a auditoria (``audit_id``), por isso o save faz
upsert manual (UPDATE se já existir, INSERT caso contrário).

Sem custo de API: só acesso a banco (PostgreSQL via psycopg2). Todas as funções
recebem uma fábrica de conexão (``get_connection``) por injeção de dependência e
fecham a conexão no ``finally``.
"""

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
    """Grava (upsert) o feedback do gestor para uma auditoria.

    Se já existir uma row para ``audit_id``, faz UPDATE (e atualiza ``criado_em``
    para CURRENT_TIMESTAMP); caso contrário faz INSERT. Garante a existência da
    tabela via ``ensure_gestor_feedbacks_table`` antes de operar.

    Efeitos colaterais: escreve no banco e faz commit. Em caso de erro, loga um
    warning e retorna False (não propaga a exceção). A conexão é sempre fechada.

    Retorna True em sucesso, False em falha.
    """
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
    """Lê o feedback do gestor de uma auditoria.

    Garante a tabela e busca a row por ``audit_id``. Retorna um dict com as
    chaves ``id``, ``audit_id``, ``gestor_nome``, ``feedback_texto``,
    ``pontos_melhoria`` e ``criado_em``, ou None se não houver feedback (ou em
    caso de erro, que é logado como warning, não propagado). A conexão é sempre
    fechada.
    """
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
