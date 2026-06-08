import asyncio
import sys
sys.path.append('backend')
from core.huawei_obs_client import HuaweiOBSClient
import database
import httpx

async def t():
    ak = database.get_config_value('huawei_obs_ak', '')
    sk = database.get_config_value('huawei_obs_sk', '')
    print('DB AK:', repr(ak))
    print('DB SK:', repr(sk))
    
    ak = ak.strip()
    sk = sk.strip()
    
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket='obs-nstech-opentech')
    headers = client._sign('GET')
    print('Generated Headers:', headers)
    
    url = "https://obs-nstech-opentech.obs.sa-brazil-1.myhuaweicloud.com/?prefix=Voice/20260505/&max-keys=10"
    async with httpx.AsyncClient() as hc:
        r = await hc.get(url, headers=headers)
        print('Status:', r.status_code)
        print('Body:', r.text)

if __name__ == '__main__':
    asyncio.run(t())
