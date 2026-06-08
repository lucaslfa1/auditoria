import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from core.huawei_client import HuaweiAICCClient
from core.huawei_sync import _load_config

async def main():
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    
    call_ids = ["1777093663-792075", "1777095569-792178"] # From the OBS list
    
    for call_id in call_ids:
        print(f"Testing downloadRecord for callId: {call_id}")
        url = f"{client.fs_url}/CCFS/resource/ccfs/downloadRecord"
        payload = {
            "request": {"version": "2.0"},
            "msgBody": {"callId": call_id, "ccId": client.cc_id},
        }
        resp = await client._post_json(url, payload)
        if resp:
            print("Response Headers:", resp.headers)
            try:
                print("Response JSON:", resp.json())
            except:
                print("Not JSON. Content type:", resp.headers.get("content-type"))
        else:
            print("No response")

if __name__ == "__main__":
    asyncio.run(main())
