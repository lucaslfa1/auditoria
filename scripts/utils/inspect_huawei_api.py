import os
import asyncio
import sys
import logging
import json
import time
import psycopg2

sys.path.append('backend')
from core.huawei_client import HuaweiAICCClient

DATABASE_URL = os.environ["DATABASE_URL"]

async def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT chave, valor FROM configuracoes")
    cfg_raw = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()

    cfg = {k.replace("huawei_", ""): v for k, v in cfg_raw.items()}
    if "ccid" in cfg:
        cfg["cc_id"] = cfg["ccid"]
        
    client = HuaweiAICCClient.from_config(cfg)
    now = int(time.time() * 1000)
    calls = await client.buscar_historico_chamadas(now - 3600*1000 * 2, now, call_direction='INBOUND')
    print(json.dumps(calls[:1], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
