import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from core.huawei_client import HuaweiAICCClient
from core.huawei_sync import _load_config

async def main():
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=24)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)
    
    chamadas_in = await client.buscar_historico_chamadas(begin_ms, end_ms, call_direction="INBOUND", limit=5)
    
    if chamadas_in:
        print("Example call keys:")
        print(list(chamadas_in[0].keys()))
        print("Example call content:")
        for k, v in chamadas_in[0].items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(main())
