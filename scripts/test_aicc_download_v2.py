import asyncio
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

# Ajusta o path para encontrar o backend
sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from backend.core.huawei_client import HuaweiAICCClient
from backend.core.huawei_sync import _load_config, _missing_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_aicc_download_v2(call_id: str = None):
    print("=== Teste de Download Huawei AICC v2 ===")
    
    cfg = _load_config()
    missing = _missing_credentials(cfg)
    if missing:
        print(f"ERRO: Credenciais ausentes: {missing}")
        return

    client = HuaweiAICCClient.from_config(cfg)
    print(f"Configuracao: CCID={client.cc_id}, VDN={client.vdn}, Modo={client.auth_mode}")
    print(f"URL FS: {client.fs_url}")

    if not call_id:
        # Tenta buscar uma chamada recente para testar
        print("\nBuscando chamada recente para teste...")
        agora = datetime.now(timezone.utc)
        begin_ms = int((agora - timedelta(hours=2)).timestamp() * 1000)
        end_ms = int(agora.timestamp() * 1000)
        
        chamadas = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="OUTBOUND")
        if not chamadas:
            chamadas = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="INBOUND")
            
        if not chamadas:
            print("Nenhuma chamada encontrada nas ultimas 2 horas para teste.")
            return
            
        call_id = chamadas[0].get("callId")
        print(f"Selecionada chamada {call_id} para teste.")

    print(f"\nIniciando download da chamada {call_id}...")
    start_time = datetime.now()
    
    try:
        audio_bytes = await client.baixar_gravacao_por_callid(call_id)
        duration = (datetime.now() - start_time).total_seconds()
        
        if audio_bytes:
            size_kb = len(audio_bytes) / 1024
            print(f"SUCESSO! Download concluido em {duration:.2f}s")
            print(f"Tamanho: {size_kb:.2f} KB")
            
            save_path = f"ligacoes/test_download_{call_id}.wav"
            os.makedirs("ligacoes", exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(audio_bytes)
            print(f"Arquivo salvo em: {save_path}")
        else:
            print(f"FALHA: O download retornou vazio em {duration:.2f}s. Verifique os logs do backend para detalhes do erro da Huawei.")
            
    except Exception as e:
        print(f"ERRO CRITICO durante o download: {e}")
        logger.exception(e)

if __name__ == "__main__":
    target_call = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(test_aicc_download_v2(target_call))
