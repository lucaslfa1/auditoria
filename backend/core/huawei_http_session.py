import asyncio
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class HuaweiHttpSession:
    _instance: Optional[httpx.AsyncClient] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> httpx.AsyncClient:
        if cls._instance is not None:
            return cls._instance
        async with cls._lock:
            if cls._instance is not None:
                return cls._instance
            limits = httpx.Limits(
                max_connections=int(os.getenv("HUAWEI_HTTP_MAX_CONNECTIONS", "20")),
                max_keepalive_connections=int(os.getenv("HUAWEI_HTTP_MAX_KEEPALIVE", "10"))
            )
            verify_ssl = os.getenv("HUAWEI_SSL_VERIFY", "true").lower() == "true"
            timeout = float(os.getenv("HUAWEI_HTTP_TIMEOUT", "30.0"))

            # follow_redirects=False: requests assinados (HMAC/Bearer) nao devem
            # seguir redirects automaticamente — httpx remove o Authorization em
            # redirects cross-origin, e mesmo same-origin pode mascarar 403/401.
            cls._instance = httpx.AsyncClient(
                limits=limits,
                verify=verify_ssl,
                timeout=timeout,
                follow_redirects=False,
            )
            logger.info("HuaweiHttpSession: Novo pool httpx.AsyncClient instanciado (limits=%s, follow_redirects=False)", limits)
            return cls._instance

    @classmethod
    async def close(cls):
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None
            logger.info("HuaweiHttpSession: Pool httpx.AsyncClient encerrado.")
