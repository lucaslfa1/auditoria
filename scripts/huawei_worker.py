"""Worker LOCAL de sincronismo Huawei — ferramenta de dev/manual, NÃO é deploy de produção.

Loop infinito que chama `executar_sync_huawei(horas_retroativas=1)` e dorme 10
minutos entre os ciclos. Pensado para rodar numa máquina local cujo `.env`
aponta para o Neon de produção — os dados caem direto no banco real.

COMO RODAR: `python scripts/huawei_worker.py` (fica em primeiro plano; morre se o
terminal/máquina fechar — por isso é best-effort, não confiável para produção).

EM PRODUÇÃO a coleta NÃO usa este worker: ela roda pelos endpoints de cron
(`POST /api/automation/cron/run` e o pipeline D-1), disparados pelo agendador
externo (Cloud Scheduler). Ver `docs/05-operacao-runbook.md` e
`backend/routers/automation.py`. Para uma coleta avulsa pontual use
`scripts/huawei_manual_sync.py`.
"""

import asyncio
import os
import logging
import sys
import time
from datetime import datetime

# Ajusta o path para encontrar o backend
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

import database
from core.huawei_sync import executar_sync_huawei

# Configuração de Logs para o terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("huawei_worker")

async def run_worker():
    logger.info("=== INICIANDO WORKER DE SINCRONISMO HUAWEI LOCAL ===")
    logger.info("IP de Saida detectado: (validando conectividade...)")
    
    # Loop infinito de sincronismo
    while True:
        try:
            logger.info("Iniciando ciclo de sincronismo (retroativo 1 hora)...")
            
            # Chama a função oficial do sistema
            # Como o .env local deve estar apontando para o Neon, 
            # os dados cairão direto no banco de produção.
            result = await executar_sync_huawei(horas_retroativas=1)
            
            logger.info(f"Ciclo concluído: {result.get('baixadas', 0)} baixadas, {result.get('enfileiradas', 0)} enfileiradas.")
            
            if result.get("status") == "error":
                logger.error(f"Erro no ciclo: {result.get('message')}")

        except Exception as e:
            logger.exception("Falha crítica no loop do worker")
        
        # Espera 10 minutos para o próximo ciclo (ajustável)
        logger.info("Aguardando 10 minutos para o próximo ciclo...")
        await asyncio.sleep(600)

if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker parado pelo usuário.")
