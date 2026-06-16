"""Pool HTTP compartilhado (singleton) para chamadas a Huawei.

Mantem uma unica instancia de `httpx.AsyncClient` reutilizada por todo o
processo, para aproveitar Keep-Alive/handshake TLS entre as muitas
requisicoes ao gateway AICC/OBS da Huawei. Limites e timeouts vem de
variaveis de ambiente (HUAWEI_HTTP_*).

Detalhe importante: `follow_redirects=False` e proposital — requests
assinados (HMAC/Bearer) nao devem seguir redirects automaticamente, pois o
httpx remove o header Authorization em redirects cross-origin (e mesmo
same-origin pode mascarar 401/403).

Sem custo de API (so gerencia o cliente HTTP; quem faz as chamadas pagas/
externas e o codigo que usa este pool).
"""

import asyncio
import httpx
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class HuaweiHttpSession:
    """Guarda o `httpx.AsyncClient` singleton usado nas chamadas Huawei."""

    _instance: Optional[httpx.AsyncClient] = None
    _lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_instance(cls) -> httpx.AsyncClient:
        """Retorna o `httpx.AsyncClient` compartilhado, criando-o sob demanda.

        Usa double-checked locking com `_lock` para garantir que apenas uma
        instancia seja criada mesmo sob concorrencia. Na primeira chamada
        instancia o cliente com limites/timeout/verify lidos das envs
        (HUAWEI_HTTP_MAX_CONNECTIONS, HUAWEI_HTTP_MAX_KEEPALIVE,
        HUAWEI_SSL_VERIFY, HUAWEI_HTTP_TIMEOUT) e `follow_redirects=False`.

        Efeito colateral: na primeira chamada cria o pool (recurso de rede) e
        registra um log INFO. Chamadas seguintes apenas devolvem a instancia.
        """
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
        """Fecha o cliente HTTP compartilhado e zera o singleton.

        Idempotente: nao faz nada se nenhuma instancia foi criada. Efeito
        colateral: encerra o pool de conexoes (`aclose`) e registra log INFO.
        Deve ser chamado no shutdown do processo para liberar conexoes.
        """
        if cls._instance:
            await cls._instance.aclose()
            cls._instance = None
            logger.info("HuaweiHttpSession: Pool httpx.AsyncClient encerrado.")
