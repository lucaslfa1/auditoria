"""Backfill feedback embeddings — regenera embeddings para os feedbacks RAG existentes.

Este script busca todos os feedbacks na tabela ``ai_feedback`` que possuem
texto de exemplo de transcrição, mas cujos embeddings são nulos (geralmente
porque o deployment de embeddings do Azure OpenAI não estava configurado ou ativo).
Gera os embeddings e os salva usando pgvector.

Uso:
  python backend/scripts/backfill_feedback_embeddings.py
"""

import sys
import os
import logging

# Adiciona o diretório backend ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv('backend/.env')

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("backfill_embeddings")

def backfill():
    from db.connection import get_connection
    from core.rag_triagem import gerar_embedding
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Verifica se a extensão pgvector e a coluna de embedding existem
        from core.ai_feedback import _feedback_embedding_column_available
        if not _feedback_embedding_column_available(cursor):
            logger.error("A coluna 'transcricao_embedding' nao esta disponivel no banco de dados. Execute as migracoes primeiro.")
            return
            
        # 2. Busca registros com transcricao de exemplo mas sem embedding
        cursor.execute("""
            SELECT id, exemplo_transcricao 
            FROM ai_feedback 
            WHERE exemplo_transcricao IS NOT NULL 
              AND exemplo_transcricao != ''
              AND transcricao_embedding IS NULL
              AND ativo = 1
            ORDER BY criado_em DESC
        """)
        rows = cursor.fetchall()
        
        if not rows:
            logger.info("Nenhum feedback ativo com embedding nulo foi encontrado para processamento.")
            return
            
        logger.info("Encontrados %d registros para gerar embedding.", len(rows))
        
        success_count = 0
        fail_count = 0
        
        for idx, row in enumerate(rows, 1):
            feedback_id = row["id"]
            texto = row["exemplo_transcricao"]
            
            logger.info("[%d/%d] Gerando embedding para feedback ID #%d (%d chars)...", idx, len(rows), feedback_id, len(texto))
            
            embedding = gerar_embedding(texto)
            if embedding:
                cursor.execute("""
                    UPDATE ai_feedback
                    SET transcricao_embedding = %s::vector,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (str(embedding), feedback_id))
                conn.commit()
                success_count += 1
                logger.info("  --> Salvo com sucesso.")
            else:
                fail_count += 1
                logger.warning("  --> Falha ao gerar embedding para ID #%d.", feedback_id)
                
        logger.info("Processamento finalizado! Sucesso: %d | Falha: %d", success_count, fail_count)
        
    finally:
        conn.close()

if __name__ == "__main__":
    backfill()
