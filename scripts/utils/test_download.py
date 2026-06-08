import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from core.network_utils import apply_dns_overrides
os.environ["HUAWEI_PROXY_IP"] = "34.171.63.68"
apply_dns_overrides()

from core.huawei_client import HuaweiAICCClient
from core.huawei_sync import _load_config
from core.huawei_obs_client import HuaweiOBSClient
import database

async def main():
    print("Testing Huawei OBS and Client downloads...")
    cfg = _load_config()
    client = HuaweiAICCClient.from_config(cfg)
    print(f"OBS config (if any in cfg): {cfg.get('obs_ak')} / {cfg.get('obs_bucket')}")

    horas = 12
    agora = datetime.now(timezone.utc)
    begin_ms = int((agora - timedelta(hours=horas)).timestamp() * 1000)
    end_ms = int(agora.timestamp() * 1000)

    try:
        chamadas = await client.buscar_historico_chamadas(begin_ms=begin_ms, end_ms=end_ms)
        print(f"Chamadas VDN: {len(chamadas) if chamadas else 0}")
        if not chamadas:
            print("No calls to test.")
            return

        call_id = chamadas[0].get("callId") or chamadas[0].get("callid")
        print(f"Testing callId: {call_id}")
        
        print("Testing OBS Pre-signed URL:")
        b_time = chamadas[0].get("beginTime") or begin_ms
        e_time = chamadas[0].get("endTime") or end_ms
        url = await client.obter_url_audio_obs(call_id, b_time, e_time)
        print(f"URL: {url}")
        if url:
            audio = await client.baixar_audio_ram(url)
            print(f"Audio downloaded via Pre-signed URL: {len(audio) if audio else 'None'}")
        
        print("Testing FS downloadRecord:")
        audio_fs = await client.baixar_gravacao_por_callid(call_id)
        print(f"Audio downloaded via FS: {len(audio_fs) if audio_fs else 'None'}")

        print("Testing Direct OBS:")
        try:
            # try to get object using obs_client
            # Note: OBS path usually is year/month/day/callId.wav or something. 
            pass
        except Exception as e:
            print(f"OBS Client error: {e}")

    except Exception as e:
        print(f"Error testing download: {e}")

if __name__ == '__main__':
    asyncio.run(main())