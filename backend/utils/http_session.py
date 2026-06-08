import os
from urllib.parse import urlparse

import requests


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_proxy_url(value: str) -> str:
    value = value.strip()
    if "://" in value:
        return value
    return f"http://{value}"


def _is_broken_loopback_proxy(proxy_url: str | None) -> bool:
    if not proxy_url:
        return False

    try:
        parsed = urlparse(_normalize_proxy_url(proxy_url))
    except ValueError:
        return False

    return (parsed.hostname or "").lower() in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9


def should_trust_env_proxies() -> bool:
    forced = os.getenv("AUDITORIA_TRUST_ENV_PROXY")
    if forced is not None:
        return _is_truthy(forced)

    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        if _is_broken_loopback_proxy(os.getenv(key)):
            return False

    return True


def create_requests_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = should_trust_env_proxies()
    return session
