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
    
    horas = 24
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=horas)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    chamadas_in = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="INBOUND", limit=100)
    chamadas_out = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="OUTBOUND", limit=100)
    
    todas = chamadas_in + chamadas_out
    
    agent_ids_in_calls = set()
    for c in todas:
        agent_id = str(c.get("agentId") or c.get("agentid") or "").strip()
        if agent_id:
            agent_ids_in_calls.add(agent_id)
            
    print("Agent IDs found in calls:")
    print(list(agent_ids_in_calls)[:20])
    
    operadores = database.listar_auditaveis_com_id_huawei()
    print("\nFirst 20 DB Operators id_huawei:")
    for op in operadores[:20]:
        print(f"  {op.get('nome')}: {op.get('id_huawei')}")

if __name__ == "__main__":
    asyncio.run(main())
