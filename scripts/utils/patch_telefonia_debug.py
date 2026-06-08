import os
import sys

filename = 'backend/routers/telefonia.py'
with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

endpoint = """
@router.get("/debug/obs")
async def debug_obs_root(user: dict = Depends(require_admin)):
    \"\"\"Lista as primeiras 30 pastas/chaves na raiz do OBS para descobrirmos o formato.\"\"\"
    from core.huawei_obs_client import HuaweiOBSClient
    import database
    
    ak = str(database.get_config_value("huawei_obs_ak", "") or "").strip()
    sk = str(database.get_config_value("huawei_obs_sk", "") or "").strip()
    bucket = str(database.get_config_value("huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(database.get_config_value("huawei_obs_endpoint", "") or "").strip()
    
    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}
        
    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    try:
        keys = await client._list_keys(prefix="")
        return {
            "bucket": bucket,
            "root_keys": keys[:30] if keys else [],
            "message": "Sucesso" if keys else "Bucket parece estar vazio na raiz!"
        }
    except Exception as e:
        return {"error": str(e)}

"""

if "@router.get(\"/debug/obs\")" not in content:
    idx = content.find("@router.post(\"/cron/sync\")")
    if idx != -1:
        content = content[:idx] + endpoint + content[idx:]

with open(filename, 'w', encoding='utf-8') as f:
    f.write(content)
