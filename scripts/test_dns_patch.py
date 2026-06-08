import asyncio
import httpx
import logging
import sys
import os

sys.path.append(os.path.abspath('backend'))
from core.network_utils import apply_dns_overrides

logging.basicConfig(level=logging.INFO)

async def test_dns_override():
    os.environ["HUAWEI_PROXY_IP"] = "1.2.3.4" # Dummy IP
    apply_dns_overrides()
    
    print("Testing httpx call to brazilsaas.aicccloud.com...")
    async with httpx.AsyncClient(verify=False) as client:
        try:
            # This should try to connect to 1.2.3.4
            await client.get("https://brazilsaas.aicccloud.com:28443", timeout=2)
        except Exception as e:
            print(f"Caught expected error or actual error: {e}")

if __name__ == "__main__":
    asyncio.run(test_dns_override())
