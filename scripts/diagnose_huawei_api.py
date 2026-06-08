
import asyncio
import os
import sys
import json
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from backend.core.huawei_client import HuaweiAICCClient
from backend.core.huawei_sync import _load_config
from backend.core.network_utils import apply_dns_overrides

apply_dns_overrides()

async def diagnose():
    print("--- DIAGNOSTICO API HUAWEI ---")
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    
    agora = datetime.now(timezone.utc)
    # Vamos olhar as últimas 24 horas para garantir que pegamos algo
    begin_ms = int((agora - timedelta(hours=24)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    print(f"Config: CCID={cfg.get('cc_id')}, VDN={cfg.get('vdn')}")
    print(f"Periodo: {agora - timedelta(hours=24)} ate {agora}")
    
    for direction in ["INBOUND", "OUTBOUND"]:
        print(f"\nBuscando {direction}...")
        try:
            chamadas = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction=direction, limit=10)
            print(f"Retornadas {len(chamadas)} chamadas.")
            for i, c in enumerate(chamadas):
                call_id = c.get('callId')
                duration = c.get('duration')
                begin_time = c.get('beginTime')
                print(f"  [{i+1}] ID: {call_id} | Duracao: {duration}s | Inicio: {begin_time}")
        except Exception as e:
            print(f"Erro em {direction}: {e}")

if __name__ == "__main__":
    asyncio.run(diagnose())
