"""Fábrica de sessões HTTP `requests` resilientes a proxy de ambiente quebrado.

Papel no sistema: centraliza a criação de `requests.Session` para as chamadas
HTTP do backend (incluindo as integrações pagas com Azure OpenAI/Speech, que são
feitas por outras camadas usando sessões deste módulo). O ponto-chave é decidir se
a sessão deve confiar nas variáveis de ambiente de proxy (`HTTPS_PROXY`,
`HTTP_PROXY`, `ALL_PROXY`): em alguns ambientes essas variáveis apontam para um
proxy de loopback inválido (ex.: `127.0.0.1:9` — porta de descarte), o que faria
TODA requisição falhar. Aqui detectamos esse caso e desligamos `trust_env` para
não usar o proxy quebrado.

Sem custo de API: este módulo só lê variáveis de ambiente e monta o objeto de
sessão; nenhuma requisição de rede é disparada aqui.
"""

import os
from urllib.parse import urlparse

import requests


def _is_truthy(value: str | None) -> bool:
    """Interpreta uma string de env como booleano (`1/true/yes/on` => True)."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_proxy_url(value: str) -> str:
    value = value.strip()
    if "://" in value:
        return value
    return f"http://{value}"


def _is_broken_loopback_proxy(proxy_url: str | None) -> bool:
    """Indica se a URL de proxy aponta para um loopback notoriamente inválido.

    Considera "quebrado" um proxy cujo host seja `127.0.0.1`/`localhost`/`::1` E
    cuja porta seja 9 (porta de descarte/Discard Protocol) — um valor que costuma
    ser injetado por engano no ambiente e que faz toda requisição falhar. Retorna
    False para qualquer outra URL ou quando a URL não pode ser parseada.
    """
    if not proxy_url:
        return False

    try:
        parsed = urlparse(_normalize_proxy_url(proxy_url))
    except ValueError:
        return False

    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9


def should_trust_env_proxies() -> bool:
    """Decide se as sessões devem confiar nas variáveis de proxy do ambiente.

    Regras:
    - Se `AUDITORIA_TRUST_ENV_PROXY` estiver definida, ela tem prioridade absoluta
      (valor truthy => True, qualquer outra coisa => False) — override manual.
    - Caso contrário, retorna False se qualquer uma das variáveis `HTTPS_PROXY`,
      `HTTP_PROXY` ou `ALL_PROXY` apontar para um proxy de loopback quebrado
      (ver `_is_broken_loopback_proxy`); senão retorna True (confia no ambiente).

    Efeitos colaterais: apenas leitura de variáveis de ambiente.
    """
    forced = os.getenv("AUDITORIA_TRUST_ENV_PROXY")
    if forced is not None:
        return _is_truthy(forced)

    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        if _is_broken_loopback_proxy(os.getenv(key)):
            return False

    return True


def create_requests_session() -> requests.Session:
    """Cria uma `requests.Session` com `trust_env` ajustado contra proxy quebrado.

    Retorna uma sessão pronta para uso cujo `trust_env` reflete a decisão de
    `should_trust_env_proxies()` — ou seja, ignora automaticamente um proxy de
    loopback inválido configurado no ambiente. Não dispara requisições de rede.
    """
    session = requests.Session()
    session.trust_env = should_trust_env_proxies()
    return session
