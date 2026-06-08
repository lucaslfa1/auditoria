import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from dotenv import load_dotenv
from core.huawei_obs_client import HuaweiOBSClient

load_dotenv("backend/.env")

async def testar():
    try:
        ak = os.getenv("HUAWEI_OBS_AK")
        sk = os.getenv("HUAWEI_OBS_SK")
        bucket = os.getenv("HUAWEI_OBS_BUCKET")
        endpoint = os.getenv("HUAWEI_OBS_ENDPOINT")
        
        if not all([ak, sk, bucket]):
            # Tentar da tabela configuracoes do banco de dados (que e de onde o sync pega)
            import database
            ak = str(database.get_config_value("huawei_obs_ak", "") or "").strip()
            sk = str(database.get_config_value("huawei_obs_sk", "") or "").strip()
            bucket = str(database.get_config_value("huawei_obs_bucket", "") or "").strip()
            endpoint = str(database.get_config_value("huawei_obs_endpoint", "") or "").strip()

        if not all([ak, sk, bucket]):
            print("Credenciais do OBS nao encontradas")
            return
            
        client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint)
        print("Listando a RAIZ do bucket OBS...")
        
        keys = await client._list_keys(prefix="")
        if not keys:
            print("Nenhuma chave encontrada na raiz.")
        for k in keys[:20]:
            print(f"Encontrado: {k}")
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    asyncio.run(testar())
