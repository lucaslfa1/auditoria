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

async def test_list():
    cfg = database.get_all_configs()
    ak = get_cfg_value(cfg, "huawei_obs_ak")
    sk = get_cfg_value(cfg, "huawei_obs_sk")
    bucket = get_cfg_value(cfg, "huawei_obs_bucket")
    endpoint = get_cfg_value(cfg, "huawei_obs_endpoint", "obs.sa-brazil-1.myhuaweicloud.com")
    
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint)
    
    url = f"{client._base_url}/?prefix=voice/&delimiter=/&max-keys=1000"
    headers = client._sign("GET")
    async with client._client(30.0) as cli:
        resp = await cli.get(url, headers=headers)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        ns = {"s": "http://obs.myhwclouds.com/doc/2015-06-30/"}
        prefixes = [elem.text for elem in root.findall("s:CommonPrefixes/s:Prefix", ns)]
        print("Last 10 folders in Voice/:")
        for p in prefixes[-10:]:
            print(p)

if __name__ == "__main__":
    asyncio.run(test_list())