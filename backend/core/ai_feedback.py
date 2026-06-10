"""AI Feedback — prompt calibration via human corrections.

Stores auditor feedback and injects it into AI prompts as few-shot examples.
Supports RAG via pgvector semantic search when embeddings are available.
"""

import logging
from typing import Optional

from repositories.common import extract_returning_id

logger = logging.getLogger(__name__)

MAX_FEEDBACK_PER_PROMPT = 10
MAX_RAG_EXAMPLES = 3

VALID_TIPOS = {"classificacao", "avaliacao", "fatal_flag", "regra_geral"}

PUBLIC_FEEDBACK_COLUMNS = """
    id, tipo, setor, criterio_id, situacao, correcao, justificativa,
    exemplo_transcricao, criado_por, ativo, criado_em, atualizado_em
"""


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _get_connection():
    from db.database import get_connection
    return get_connection()


def _feedback_embedding_column_available(cursor) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ai_feedback'
          AND column_name = 'transcricao_embedding'
        LIMIT 1
        """
    )
    return cursor.fetchone() is not None


def list_feedback(
    tipo: Optional[str] = None,
    setor: Optional[str] = None,
    ativo_only: bool = False,
) -> list[dict]:
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        query = f"SELECT {PUBLIC_FEEDBACK_COLUMNS} FROM ai_feedback WHERE 1=1"
        params: list = []

        if tipo:
            query += " AND tipo = %s"
            params.append(tipo)
        if setor:
            query += " AND (setor = %s OR setor IS NULL)"
            params.append(setor)
        if ativo_only:
            query += " AND ativo = 1"

        query += " ORDER BY criado_em DESC"
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def get_feedback_by_id(feedback_id: int) -> Optional[dict]:
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {PUBLIC_FEEDBACK_COLUMNS} FROM ai_feedback WHERE id = %s",
            (feedback_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_feedback(
    tipo: str,
    situacao: str,
    correcao: str,
    justificativa: str,
    criado_por: str,
    setor: Optional[str] = None,
    criterio_id: Optional[str] = None,
    exemplo_transcricao: Optional[str] = None,
    transcricao_embedding: Optional[list[float]] = None,
) -> dict:
    if tipo not in VALID_TIPOS:
        raise ValueError(f"Tipo inválido: {tipo}. Válidos: {VALID_TIPOS}")

    if not transcricao_embedding and exemplo_transcricao:
        try:
            from core.rag_triagem import gerar_embedding
            transcricao_embedding = gerar_embedding(exemplo_transcricao)
        except Exception as exc:
            logger.warning("Falha ao gerar embedding para novo feedback: %s", exc)

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        has_embedding_column = _feedback_embedding_column_available(cursor)
        if has_embedding_column:
            cursor.execute(
                """
                INSERT INTO ai_feedback (
                    tipo, setor, criterio_id, situacao, correcao,
                    justificativa, exemplo_transcricao, transcricao_embedding, criado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s)
                RETURNING id
                """,
                (
                    tipo, setor, criterio_id, situacao, correcao,
                    justificativa, exemplo_transcricao,
                    str(transcricao_embedding) if transcricao_embedding else None,
                    criado_por,
                ),
            )
        else:
            if transcricao_embedding:
                logger.info("AI feedback embedding ignored because pgvector column is unavailable.")
            cursor.execute(
                """
                INSERT INTO ai_feedback (
                    tipo, setor, criterio_id, situacao, correcao,
                    justificativa, exemplo_transcricao, criado_por
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    tipo, setor, criterio_id, situacao, correcao,
                    justificativa, exemplo_transcricao, criado_por,
                ),
            )
        new_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        logger.info("AI feedback #%d created by %s (tipo=%s, setor=%s)", new_id, criado_por, tipo, setor)
        return {"id": new_id, "created": True}
    finally:
        conn.close()


def update_feedback(
    feedback_id: int,
    situacao: Optional[str] = None,
    correcao: Optional[str] = None,
    justificativa: Optional[str] = None,
    setor: Optional[str] = None,
    criterio_id: Optional[str] = None,
    exemplo_transcricao: Optional[str] = None,
) -> bool:
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ai_feedback WHERE id = %s", (feedback_id,))
        row = cursor.fetchone()
        if not row:
            return False

        new_situacao = situacao if situacao is not None else row["situacao"]
        new_correcao = correcao if correcao is not None else row["correcao"]
        new_justificativa = justificativa if justificativa is not None else row["justificativa"]
        new_setor = setor if setor is not None else row["setor"]
        new_criterio_id = criterio_id if criterio_id is not None else row["criterio_id"]
        new_exemplo_transcricao = exemplo_transcricao if exemplo_transcricao is not None else row["exemplo_transcricao"]

        has_embedding_column = _feedback_embedding_column_available(cursor)
        new_embedding = None

        if has_embedding_column and new_exemplo_transcricao and new_exemplo_transcricao != row.get("exemplo_transcricao"):
            try:
                from core.rag_triagem import gerar_embedding
                new_embedding = gerar_embedding(new_exemplo_transcricao)
            except Exception as exc:
                logger.warning("Falha ao gerar novo embedding na atualizacao: %s", exc)

        if new_embedding:
            cursor.execute(
                """
                UPDATE ai_feedback
                SET situacao = %s, correcao = %s, justificativa = %s,
                    setor = %s, criterio_id = %s, exemplo_transcricao = %s,
                    transcricao_embedding = %s::vector,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    new_situacao, new_correcao, new_justificativa,
                    new_setor, new_criterio_id, new_exemplo_transcricao,
                    str(new_embedding),
                    feedback_id,
                ),
            )
        else:
            cursor.execute(
                """
                UPDATE ai_feedback
                SET situacao = %s, correcao = %s, justificativa = %s,
                    setor = %s, criterio_id = %s, exemplo_transcricao = %s,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    new_situacao, new_correcao, new_justificativa,
                    new_setor, new_criterio_id, new_exemplo_transcricao,
                    feedback_id,
                ),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def toggle_feedback(feedback_id: int) -> Optional[bool]:
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT ativo FROM ai_feedback WHERE id = %s", (feedback_id,))
        row = cursor.fetchone()
        if not row:
            return None

        new_state = 0 if row[0] else 1
        cursor.execute(
            "UPDATE ai_feedback SET ativo = %s, atualizado_em = CURRENT_TIMESTAMP WHERE id = %s",
            (new_state, feedback_id),
        )
        conn.commit()
        return bool(new_state)
    finally:
        conn.close()


def delete_feedback(feedback_id: int) -> bool:
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_feedback WHERE id = %s", (feedback_id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

_TIPO_LABELS = {
    "classificacao": "Classificação",
    "avaliacao": "Avaliação",
    "fatal_flag": "Zerar Ligação",
    "regra_geral": "Regra Geral",
}


def get_feedback_for_prompt(
    setor: Optional[str] = None,
    tipos: Optional[set[str]] = None,
    query_embedding: Optional[list[float]] = None,
) -> str:
    """Build a calibration block to inject into the AI prompt.

    When query_embedding is provided, uses pgvector semantic search (RAG)
    to find the most relevant feedback instead of chronological ordering.
    Returns empty string if no relevant feedback exists.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        use_semantic_search = bool(query_embedding) and _feedback_embedding_column_available(cursor)

        def _build_query(*, semantic: bool) -> tuple[str, list]:
            query = """
                SELECT tipo, setor, criterio_id, situacao, correcao, justificativa, exemplo_transcricao
                FROM ai_feedback
                WHERE ativo = 1
            """
            params: list = []

            if setor:
                query += " AND (setor = %s OR setor IS NULL)"
                params.append(setor)

            if tipos:
                placeholders = ",".join("%s" for _ in tipos)
                query += f" AND tipo IN ({placeholders})"
                params.extend(tipos)

            if semantic:
                query += " AND transcricao_embedding IS NOT NULL"
                query += " ORDER BY transcricao_embedding <-> %s::vector LIMIT %s"
                params.append(str(query_embedding))
                params.append(MAX_RAG_EXAMPLES)
            else:
                query += " ORDER BY criado_em DESC LIMIT %s"
                params.append(MAX_FEEDBACK_PER_PROMPT)
            return query, params

        if use_semantic_search:
            # RAG: semantic search only considers records with embeddings.
            query, params = _build_query(semantic=True)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            if not rows:
                logger.warning("AI feedback semantic search returned no rows; falling back to chronological calibration.")
                query, params = _build_query(semantic=False)
                cursor.execute(query, params)
                rows = cursor.fetchall()
                use_semantic_search = False
        else:
            if query_embedding:
                logger.warning("AI feedback embedding column unavailable; falling back to chronological calibration.")
            # Fallback: chronological search (original behavior).
            query, params = _build_query(semantic=False)
            cursor.execute(query, params)
            rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return ""

    if use_semantic_search:
        header = "EXEMPLOS HISTORICOS DE CORRECOES HUMANAS (encontrados por similaridade semantica — use como referencia FORTE):\n"
    else:
        header = "CALIBRACOES DOS AUDITORES (use como referencia OBRIGATORIA — estes sao erros corrigidos por auditores humanos):\n"

    lines = [header]

    for i, row in enumerate(rows, 1):
        tipo_label = _TIPO_LABELS.get(row["tipo"], row["tipo"])
        parts = [f"{i}. [{tipo_label}]"]
        if row["setor"]:
            parts.append(f"Setor: {row['setor']}")
        if row["criterio_id"]:
            parts.append(f"Criterio: {row['criterio_id']}")
        lines.append(" | ".join(parts))
        lines.append(f"   Situacao: {row['situacao']}")
        lines.append(f"   Correcao: {row['correcao']}")
        lines.append(f"   Motivo: {row['justificativa']}")
        if row["exemplo_transcricao"]:
            lines.append(f"   Exemplo: {row['exemplo_transcricao']}")
        lines.append("")

    return "\n".join(lines)
