
import asyncio
import os
import logging
from datetime import datetime, timedelta, timezone
from backend.core.huawei_client import HuaweiAICCClient
from backend.core.huawei_sync import _load_config, _missing_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_huawei_connectivity():
    print("--- INICIANDO TESTE DE CONECTIVIDADE HUAWEI ---")
    
    cfg = _load_config()
    missing = _missing_credentials(cfg)
    if missing:
        print(f"ERRO: Credenciais ausentes no .env: {missing}")
        return

    client = HuaweiAICCClient.from_config(cfg)
    
    # Testar busca de chamadas (Inbound)
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=1)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    print(f"Buscando chamadas de {agora - timedelta(hours=1)} ate {agora}...")
    
    try:
        chamadas = await client.buscar_historico_chamadas(
            begin_ms, 
            end_ms, 
            call_direction="INBOUND",
            limit=5
        )
        print(f"SUCESSO: Foram encontradas {len(chamadas)} chamadas Inbound.")
        for i, c in enumerate(chamadas):
            print(f"  [{i+1}] CallID: {c.get('callId')} | Duracao: {c.get('duration')}s | Motivo: {c.get('callReason')}")
            
    except Exception as e:
        print(f"ERRO ao buscar chamadas: {e}")

if __name__ == "__main__":
    asyncio.run(test_huawei_connectivity())
