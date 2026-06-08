"""
Agendador de tarefas diárias do backend.

Em Cloud Run (serverless), threads em background são congeladas quando não há
requisições HTTP ativas (CPU throttling). Por isso, a execução é exposta como
uma função síncrona chamada por uma rota HTTP, que deve ser disparada pelo
Google Cloud Scheduler via gatilho HTTP.
"""

import logging

logger = logging.getLogger(__name__)


def run_knowledge_agent() -> list[str]:
    """Executa o DB Knowledge Agent e retorna a lista de documentos gerados.

    Chamada pela rota ``POST /api/internal/cron/knowledge-agent``.
    """
    from scripts.db_knowledge_agent import DBKnowledgeAgent

    logger.info("Executando DB Knowledge Agent (via cron HTTP)")
    agent = DBKnowledgeAgent()
    files = agent.run()
    logger.info("DB Knowledge Agent concluido - %d documentos gerados", len(files))
    return files
