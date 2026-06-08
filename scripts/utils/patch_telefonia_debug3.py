import os
import sys

filename = 'backend/routers/telefonia.py'
with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

endpoint = """
@router.get("/debug/obs/search")
async def debug_obs_search(user: dict = Depends(require_admin)):
    \"\"\"Procura pastas uteis no OBS.\"\"\"
    from core.huawei_obs_client import HuaweiOBSClient
    import database
    from datetime import datetime, timezone
    
    ak = str(database.get_config_value("huawei_obs_ak", "") or "").strip()
    sk = str(database.get_config_value("huawei_obs_sk", "") or "").strip()
    bucket = str(database.get_config_value("huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(database.get_config_value("huawei_obs_endpoint", "") or "").strip()
    
    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}
        
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    
    agora = datetime.now(timezone.utc)
    date_str = agora.strftime("%Y%m%d")
    
    prefixes_to_test = [
        f"Voice/{date_str}/",
        f"voice/{date_str}/",
        f"Recordings/{date_str}/",
        f"recordings/{date_str}/",
        f"Contact_Record/",
        "Voice/",
        "Recordings/"
    ]
    
    results = {}
    
    for prefix in prefixes_to_test:
        try:
            keys = await client._list_keys(prefix=prefix)
            results[prefix] = keys[:10] if keys else []
        except Exception as e:
            results[prefix] = f"Error: {e}"

    return {
        "bucket": bucket,
        "search_results": results
    }

"""

if "@router.get(\"/debug/obs/search\")" not in content:
    idx = content.find("@router.post(\"/cron/sync\")")
    if idx != -1:
        content = content[:idx] + endpoint + content[idx:]

with open(filename, 'w', encoding='utf-8') as f:
    f.write(content)
