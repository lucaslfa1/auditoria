
import asyncio
import os
import logging
import sys
import argparse

# Ajusta o path para encontrar o backend
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

import database
from core.huawei_sync import executar_sync_huawei

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("huawei_manual_sync")

async def run_manual_sync(horas: int):
    logger.info(f"=== INICIANDO SINCRONISMO HUAWEI MANUAL (Retroativo {horas}h) ===")
    
    try:
        # Chama a função oficial
        result = await executar_sync_huawei(horas_retroativas=horas)
        
        print("\n" + "="*50)
        print(f"RESULTADO DO SINCRONISMO:")
        print(f" - Chamadas encontradas na API: {result.get('chamadas_consideradas', 0)}")
        print(f" - Baixadas com sucesso:        {result.get('baixadas', 0)}")
        print(f" - Enfileiradas para triagem:   {result.get('enfileiradas', 0)}")
        print(f" - Já existiam no banco:        {result.get('duplicadas', 0)}")
        print("="*50 + "\n")

        if result.get("status") == "error":
            logger.error(f"Erro: {result.get('message')}")

    except Exception as e:
        logger.exception("Falha na execução do sincronismo manual")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sincronismo manual Huawei via IP local.")
    parser.add_argument("--horas", type=int, default=1, help="Quantidade de horas retroativas para buscar.")
    
    args = parser.parse_args()
    asyncio.run(run_manual_sync(args.horas))
