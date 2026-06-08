"""RAG Triagem — Módulo de embeddings e aprendizado semântico.

Gera embeddings via Azure OpenAI (text-embedding-3-small) e executa
o loop de aprendizado RLHF de forma síncrona quando um auditor corrige
uma classificação.
"""

import logging
import os
from typing import Optional

from repositories.common import json_loads

logger = logging.getLogger(__name__)

# Azure OpenAI embedding config
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
EMBEDDING_MODEL = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
EMBEDDING_DIMENSIONS = 1536


def gerar_embedding(texto: str) -> Optional[list[float]]:
    """Gera embedding de um texto usando Azure OpenAI text-embedding-3-small.

    Returns None se falhar (API indisponível, texto vazio, etc.)
    para que o caller possa funcionar sem RAG.
    """
    if not texto or not texto.strip():
        return None
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_KEY:
        logger.warning("RAG: Azure OpenAI não configurado, embedding não gerado")
        return None

    try:
        from openai import AzureOpenAI

        client = AzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-01-01-preview",
        )

        # Truncar a 8000 tokens (~32000 chars) para segurança
        texto_truncado = texto[:32000]

        response = client.embeddings.create(
            input=texto_truncado,
            model=EMBEDDING_MODEL,
        )
        embedding = response.data[0].embedding
        logger.info("RAG: Embedding gerado com sucesso (%d dimensões)", len(embedding))
        return embedding
    except Exception as exc:
        msg = str(exc)
        if "DeploymentNotFound" in msg or "404" in msg:
            logger.warning("RAG: Deployment de embedding '%s' nao encontrado no Azure. RAG desativado temporariamente.", EMBEDDING_MODEL)
        else:
            logger.error("RAG: Falha ao gerar embedding: %s", exc)
        return None


def salvar_feedback_rag_sync(
    tipo: str,
    situacao: str,
    correcao: str,
    justificativa: str,
    criado_por: str,
    setor: Optional[str] = None,
    exemplo_transcricao: Optional[str] = None,
) -> None:
    """Gera feedback com embedding de forma síncrona.

    Usado como gatilho RLHF: quando o auditor corrige uma classificação,
    esta função gera o embedding e salva o feedback diretamente.
    No Cloud Run, threads daemon são congeladas no retorno do HTTP,
    portanto a execução síncrona é obrigatória (~200ms via Azure API).
    """
    try:
        # 1. Gerar embedding da transcrição
        embedding = None
        if exemplo_transcricao:
            embedding = gerar_embedding(exemplo_transcricao)

        # 2. Salvar feedback com embedding
        from core.ai_feedback import add_feedback
        result = add_feedback(
            tipo=tipo,
            situacao=situacao,
            correcao=correcao,
            justificativa=justificativa,
            criado_por=criado_por,
            setor=setor,
            exemplo_transcricao=exemplo_transcricao,
            transcricao_embedding=embedding,
        )
        logger.info(
            "RAG RLHF: Feedback #%s salvo com embedding=%s",
            result.get("id"),
            "sim" if embedding else "não",
        )
    except Exception as exc:
        logger.error("RAG RLHF falhou: %s", exc)


# Backward-compatible alias for callers still using the old name
disparar_feedback_rag_background = salvar_feedback_rag_sync


def buscar_procedimento_chunks(
    query_embedding: list[float] | None,
    *,
    setor: Optional[str] = None,
    alert_id: Optional[str] = None,
    limit: int = 3,
) -> list[dict]:
    """Return semantically relevant official POP chunks.

    This is the pgvector-backed layer for curated procedure sources. It is a
    safe optional dependency: if the migration/extension is not available yet,
    callers receive an empty list and the audit flow keeps using deterministic
    direct POP injection.
    """
    if not query_embedding:
        return []

    try:
        from db.database import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()
            filters = ["embedding IS NOT NULL"]
            filter_params: list = []
            if setor and not alert_id:
                filters.append("(setor = %s OR setor IS NULL)")
                filter_params.append(setor)
            if alert_id:
                filters.append("(alert_id = %s OR metadata_json::jsonb -> 'alert_ids' ? %s OR alert_id IS NULL)")
                filter_params.extend([alert_id, alert_id])

            where_clause = " AND ".join(filters)
            embedding_param = str(query_embedding)
            limit_param = max(1, min(int(limit), 10))
            cursor.execute(
                f"""
                SELECT source_path, source_hash, setor, alert_id, alert_label,
                       section_title, chunk_index, content, metadata_json,
                       embedding <-> %s::vector AS distance
                FROM procedimento_chunks
                WHERE {where_clause}
                ORDER BY embedding <-> %s::vector
                LIMIT %s
                """,
                (
                    embedding_param,
                    *filter_params,
                    embedding_param,
                    limit_param,
                ),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("RAG procedimentos: semantic chunk search unavailable: %s", exc)
        return []

    return [
        {
            "source_path": row["source_path"],
            "source_hash": row["source_hash"],
            "setor": row["setor"],
            "alert_id": row["alert_id"],
            "alert_label": row["alert_label"],
            "section_title": row["section_title"],
            "chunk_index": row["chunk_index"],
            "content": row["content"],
            "metadata": json_loads(row["metadata_json"], {}),
            "distance": float(row["distance"]) if row["distance"] is not None else None,
        }
        for row in rows
    ]
