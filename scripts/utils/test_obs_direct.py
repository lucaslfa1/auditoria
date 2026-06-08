import asyncio
import sys
import logging

sys.path.append('backend')
from core.huawei_obs_client import HuaweiOBSClient
import database
from datetime import datetime, timezone

logging.basicConfig(level=logging.DEBUG)

async def test_obs():
    ak = str(database.get_config_value("huawei_obs_ak", "") or "").strip()
    sk = str(database.get_config_value("huawei_obs_sk", "") or "").strip()
    bucket = str(database.get_config_value("huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(database.get_config_value("huawei_obs_endpoint", "") or "").strip()
    
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    
    # Test a recent call ID
    call_id = "1777995463-591768"
    call_time = datetime.now(timezone.utc) # Close enough for folder date
    record_id = "591768"  # Suffix
    
    print(f"Testing OBS for call {call_id} (Record ID: {record_id})")

    print("\nAttempting baixar_voice_por_callid with call_id...")
    res = await client.baixar_voice_por_callid(call_id, begin_time=call_time)
    if res:
        audio, path = res
        print(f"SUCCESS: Found audio at {path} ({len(audio)} bytes)")
    else:
        print("FAILED to find audio with call_id")
        
    print("\nAttempting baixar_voice_por_callid with record_id...")
    res2 = await client.baixar_voice_por_callid(record_id, begin_time=call_time)
    if res2:
        audio2, path2 = res2
        print(f"SUCCESS: Found audio at {path2} ({len(audio2)} bytes)")
    else:
        print("FAILED to find audio with record_id")

if __name__ == "__main__":
    asyncio.run(test_obs())
