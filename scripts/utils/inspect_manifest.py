import asyncio
import os
import sys
import logging

sys.path.append('backend')
from core.huawei_sync import _load_config, _buscar_chamadas_obs_manifest, _download_candidate_sort_key
from core.huawei_obs_client import HuaweiOBSClient
from core.network_utils import apply_dns_overrides
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO)

async def run():
    cfg = _load_config()
    apply_dns_overrides()
    
    import httpx
    # Need to disable SSL verify like the real client does
    verify_ssl = os.getenv("HUAWEI_SSL_VERIFY", "true").lower() == "true"
    
    async with httpx.AsyncClient(verify=verify_ssl) as http_cli:
        obs_client = HuaweiOBSClient(
            http_client=http_cli,
            ak=cfg["obs_ak"],
            sk=cfg["obs_sk"],
            bucket=cfg.get("obs_bucket"),
            endpoint=cfg.get("obs_endpoint")
        )
        
        agora = datetime.now(timezone.utc)
        begin_ms = int((agora - timedelta(hours=4)).timestamp() * 1000)
        end_ms = int(agora.timestamp() * 1000)
        
        calls = await _buscar_chamadas_obs_manifest(obs_client, begin_ms, end_ms)
        print(f"Total manifest calls: {len(calls)}")
        
        sorted_calls = sorted(calls, key=_download_candidate_sort_key, reverse=True)
        
        print("\nTop 5 candidates by our sort key:")
        for c in sorted_calls[:5]:
            print(f"CallId: {c.get('callId')}, RecordId: {c.get('recordId')}, Duration: {c.get('duration')}, Caller: {c.get('callerNo')}, Callee: {c.get('calleeNo')}, WorkNo: {c.get('workNo')}")

if __name__ == '__main__':
    asyncio.run(run())
