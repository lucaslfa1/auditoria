import socket
import os
import logging

logger = logging.getLogger(__name__)

def apply_dns_overrides():
    """
    Aplica redirecionamentos de DNS em nível de processo Python.
    Isso permite que a aplicação direcione domínios para IPs específicos 
    via variável DNS_OVERRIDES (ex: "host:ip,host2:ip2") sem precisar de 
    privilégios de root para alterar o /etc/hosts.
    """
    
    # Instalamos o patch preventivamente para permitir redirecionamentos dinâmicos
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
        # host pode vir como bytes em algumas bibliotecas (ex: httpx/anyio)
        host_str = host.decode("utf-8") if isinstance(host, bytes) else host
        
        # Redirecionamento via variável DNS_OVERRIDES (ex: "host:ip,host2:ip2")
        overrides_raw = os.getenv("DNS_OVERRIDES", "")
        if overrides_raw:
            for entry in overrides_raw.split(","):
                if ":" in entry:
                    h, ip = entry.split(":", 1)
                    if h.strip() == host_str:
                        return original_getaddrinfo(ip.strip(), port, family, socktype, proto, flags)
            
        return original_getaddrinfo(host, port, family, socktype, proto, flags)

    socket.getaddrinfo = patched_getaddrinfo
    logger.info("DNS Override System instalado")
