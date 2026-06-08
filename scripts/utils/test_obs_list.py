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
    
    kwargs = {"ak": ak, "sk": sk, "bucket": bucket}
    if endpoint_url:
        kwargs["endpoint"] = endpoint_url
        
    client = HuaweiOBSClient(**kwargs)
    
    date_str = datetime.now(timezone.utc).strftime('%Y%m%d')
    print(f"Listing Voice/{date_str}/")
    keys = await client._list_keys(prefix=f"Voice/{date_str}/")
    print(f"Found {len(keys)} keys")
    if keys:
        print(f"Keys: {keys[:10]}")
        
    date_str2 = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    print(f"Listing Voice/{date_str2}/")
    keys2 = await client._list_keys(prefix=f"Voice/{date_str2}/")
    print(f"Found {len(keys2)} keys")
    if keys2:
        print(f"Keys: {keys2[:10]}")

if __name__ == "__main__":
    asyncio.run(test_obs())