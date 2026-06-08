import asyncio
import sys
import logging
sys.path.append('backend')
import database
from core.huawei_obs_client import HuaweiOBSClient

def get_cfg_value(cfg, key, default=""):
    val = cfg.get(key)
    if isinstance(val, dict):
        return str(val.get("valor") or default).strip()
    return str(val or default).strip()

async def test_download():
    logging.basicConfig(level=logging.DEBUG)
    cfg = database.get_all_configs()
    ak = get_cfg_value(cfg, "huawei_obs_ak")
    sk = get_cfg_value(cfg, "huawei_obs_sk")
    bucket = get_cfg_value(cfg, "huawei_obs_bucket")
    endpoint = get_cfg_value(cfg, "huawei_obs_endpoint", "obs.sa-brazil-1.myhuaweicloud.com")
    
    if not all([ak, sk, bucket]):
        print("Missing creds")
        return

    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint)
    
    call_id = "1778000155-68508"
    prefixes = ["31971625284", "4721016122", "182.0"]
    extra_match_ids = ["68508", "177800025076518505500876309249", "2051707870129057793", "177800024978534092105309623736"]
    begin_time = 1778011049000
    end_time = 1778011204000
    
    print(f"Testing OBS for call {call_id}...")
    audio = await client.baixar_voice_por_callid(
        call_id=call_id,
        prefixes=prefixes,
        begin_time=begin_time,
        end_time=end_time,
        extra_match_ids=extra_match_ids
    )
    if audio:
        print(f"SUCCESS! Audio size: {len(audio)} bytes")
    else:
        print("FAILED to find audio.")

if __name__ == "__main__":
    asyncio.run(test_download())