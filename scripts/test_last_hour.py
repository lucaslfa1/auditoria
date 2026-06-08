import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.getcwd(), "backend"))
sys.path.append(os.getcwd())

from backend.core.huawei_client import HuaweiAICCClient
from backend.core.huawei_sync import _load_config

async def test():
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    agora = datetime.now(timezone.utc)
    begin = int((agora - timedelta(hours=1)).timestamp() * 1000)
    end = int(agora.timestamp() * 1000)
    print(f"Buscando de {agora - timedelta(hours=1)} ate {agora}...")
    res = await client.buscar_historico_chamadas(begin, end)
    print(f"Chamadas na ultima hora: {len(res)}")

if __name__ == "__main__":
    asyncio.run(test())
