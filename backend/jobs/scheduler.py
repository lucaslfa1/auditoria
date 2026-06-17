"""
Agendador de tarefas diárias do backend.

Em plataformas serverless (Cloud Run hoje; Azure Container Apps no destino),
threads em background podem ser congeladas quando não há requisições HTTP
ativas. Por isso, a execução é exposta como função síncrona chamada por rota
HTTP. O disparo vem de um scheduler externo: Google Cloud Scheduler no GCP, ou
Container Apps Job / Logic App no Azure.
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
