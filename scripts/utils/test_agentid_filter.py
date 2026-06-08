import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from core.huawei_client import HuaweiAICCClient
from core.huawei_sync import _load_config
import database

async def main():
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=24)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    # Try querying specifically for Caio
    agent_id = "13426"  # Let's see if we know Caio's ID or anyone's ID
    
    operadores = database.listar_auditaveis_com_id_huawei()
    for op in operadores:
        if op.get("id_huawei"):
            print(f"Testing operator {op.get('nome')} with ID {op.get('id_huawei')}")
            chamadas = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="INBOUND", agent_id=op.get("id_huawei"), limit=5)
            if chamadas:
                print(f"Found {len(chamadas)} inbound calls for {op.get('nome')}")
                break
            chamadas = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="OUTBOUND", agent_id=op.get("id_huawei"), limit=5)
            if chamadas:
                print(f"Found {len(chamadas)} outbound calls for {op.get('nome')}")
                break

if __name__ == "__main__":
    asyncio.run(main())
