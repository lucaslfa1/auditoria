from collections import defaultdict, deque
from threading import Lock
import base64
import bcrypt
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

import db.database as database
from repositories import auth_users

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE_NAME = "nstech_session"
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
_LOGIN_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)
_LOGIN_ATTEMPTS_LOCK = Lock()
_LOGIN_ATTEMPTS_LAST_CLEANUP: float = 0.0
_LOGIN_ATTEMPTS_CLEANUP_INTERVAL: float = 300.0  # 5 minutes


def _load_session_secret() -> str:
    configured_secret = (os.getenv("SESSION_SECRET") or "").strip()
    if configured_secret:
        return configured_secret

    environment = (os.getenv("ENVIRONMENT", "development") or "").strip().lower()
    if environment == "production":
        # Seguro: falhar explicitamente e MUITO melhor do que usar um fallback
        # previsivel hardcoded no repositorio. Quem tiver acesso ao codigo poderia
        # forjar tokens de sessao validos com o fallback antigo.
        raise RuntimeError(
            "SESSION_SECRET não configurado em produção. "
            "Defina a variável de ambiente SESSION_SECRET com um valor aleatório seguro "
            "(ex: openssl rand -hex 32)."
        )

    logger.warning(
        "SESSION_SECRET nao configurado fora de producao. "
        "Usando segredo efemero apenas para a sessao atual do processo."
    )
    return secrets.token_hex(32)


SESSION_SECRET = _load_session_secret()


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in ("1", "true", "yes", "on")


def _read_int_env(name: str, default: int, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    try:
        parsed = int(str(raw_value).strip()) if raw_value is not None else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _get_login_rate_limit_settings() -> tuple[bool, int, int]:
    enabled = _env_flag("ENABLE_LOGIN_RATE_LIMIT", os.getenv("ENVIRONMENT", "development") == "production")
    max_attempts = _read_int_env("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 5)
    window_seconds = _read_int_env("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)
    return enabled, max_attempts, window_seconds


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUserResponse(BaseModel):
    username: str
    role: str = "admin"


class AuthSessionResponse(BaseModel):
    authenticated: bool
    username: str = ""
    role: str = ""


class AuthStatusResponse(BaseModel):
    success: bool


def _sign_payload(encoded_payload: str) -> str:
    return hmac.new(
        SESSION_SECRET.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_payload(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_payload(encoded_payload: str) -> dict:
    padding = "=" * (-len(encoded_payload) % 4)
    decoded = base64.urlsafe_b64decode(encoded_payload + padding)
    return json.loads(decoded.decode("utf-8"))


def _resolve_request_ip(request: Request) -> str:
    # Cloud Run: o trafego passa pelo Load Balancer do Google, entao
    # request.client.host sempre retorna o IP do LB. Precisamos do
    # X-Forwarded-For para obter o IP real do usuario.
    forwarded = (request.headers.get("x-forwarded-for") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _build_login_rate_limit_key(request: Request, username: str) -> str:
    return f"{_resolve_request_ip(request)}|{_normalize_auth_lookup(username)}"


def _prune_login_attempts(attempts: deque[float], now: float, window_seconds: int) -> None:
    while attempts and now - attempts[0] >= window_seconds:
        attempts.popleft()


def _gc_login_attempts_locked(now: float, window_seconds: int) -> None:
    """Remove stale keys from _LOGIN_ATTEMPTS. Must hold _LOGIN_ATTEMPTS_LOCK."""
    global _LOGIN_ATTEMPTS_LAST_CLEANUP
    if now - _LOGIN_ATTEMPTS_LAST_CLEANUP < _LOGIN_ATTEMPTS_CLEANUP_INTERVAL:
        return
    _LOGIN_ATTEMPTS_LAST_CLEANUP = now
    stale_keys = [
        key for key, attempts in _LOGIN_ATTEMPTS.items()
        if not attempts or (now - attempts[-1]) >= window_seconds
    ]
    for key in stale_keys:
        del _LOGIN_ATTEMPTS[key]


def _enforce_login_rate_limit(request: Request, username: str) -> None:
    enabled, max_attempts, window_seconds = _get_login_rate_limit_settings()
    if not enabled:
        return

    key = _build_login_rate_limit_key(request, username)
    now = time.time()
    with _LOGIN_ATTEMPTS_LOCK:
        _gc_login_attempts_locked(now, window_seconds)
        attempts = _LOGIN_ATTEMPTS[key]
        _prune_login_attempts(attempts, now, window_seconds)
        if len(attempts) < max_attempts:
            return
        retry_after = max(1, int(window_seconds - (now - attempts[0])))

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Muitas tentativas de login. Tente novamente mais tarde.",
        headers={"Retry-After": str(retry_after)},
    )


def _register_failed_login_attempt(request: Request, username: str) -> None:
    enabled, _, window_seconds = _get_login_rate_limit_settings()
    if not enabled:
        return

    key = _build_login_rate_limit_key(request, username)
    now = time.time()
    with _LOGIN_ATTEMPTS_LOCK:
        attempts = _LOGIN_ATTEMPTS[key]
        _prune_login_attempts(attempts, now, window_seconds)
        attempts.append(now)


def _clear_login_rate_limit(request: Request, username: str) -> None:
    enabled, _, _ = _get_login_rate_limit_settings()
    if not enabled:
        return

    key = _build_login_rate_limit_key(request, username)
    with _LOGIN_ATTEMPTS_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)


def create_session_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(8),
    }
    encoded_payload = _encode_payload(payload)
    signature = _sign_payload(encoded_payload)
    return f"{encoded_payload}.{signature}"


def validate_session_token(token: str) -> str | None:
    try:
        encoded_payload, provided_signature = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(provided_signature, _sign_payload(encoded_payload)):
        return None
    try:
        payload = _decode_payload(encoded_payload)
    except Exception:
        return None
    exp = int(payload.get("exp", 0))
    username = str(payload.get("sub", "")).strip()
    if not username or exp < int(time.time()):
        return None
    return username


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_env_flag("SESSION_COOKIE_SECURE", os.getenv("ENVIRONMENT", "development") == "production"),
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", samesite="lax")


def _resolve_authenticated_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    username = validate_session_token(token)
    if not username:
        return None
    user = auth_users.get_user_by_username(database.get_connection, username) or {}
    if not user:
        return None
    return {
        "username": user.get("username", username),
        "role": user.get("role", "admin"),
        "supervisor_name": user.get("supervisor_name", ""),
    }


def require_authenticated_user(request: Request) -> dict:
    try:
        user = _resolve_authenticated_user(request)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if sentry_sdk:
            sentry_sdk.set_user({"username": user.get("username"), "role": user.get("role")})
        return user
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Auth Error: {e} | {traceback.format_exc()}")


def require_admin(request: Request) -> dict:
    user = require_authenticated_user(request)
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores.",
        )
    return user


def require_supervisor_or_admin(request: Request) -> dict:
    user = require_authenticated_user(request)
    if user["role"] not in ("admin", "supervisor"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito.",
        )
    return user


@router.post("/login", response_model=AuthUserResponse)
def auth_login(payload: LoginRequest, response: Response, request: Request) -> dict:
    normalized_username = payload.username.strip().lower()
    _enforce_login_rate_limit(request, normalized_username)
    logger.info("Tentativa de login: '%s'", normalized_username)

    user = auth_users.get_user_by_username(database.get_connection, normalized_username)

    if not user:
        _register_failed_login_attempt(request, normalized_username)
        logger.warning("Login rejeitado: usuario '%s' nao encontrado.", normalized_username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")

    is_password_correct = False
    if user.get("password_hash"):
        try:
            is_password_correct = bcrypt.checkpw(
                payload.password.encode("utf-8"),
                user["password_hash"].encode("utf-8"),
            )
        except Exception:
            is_password_correct = False

    if not is_password_correct:
        _register_failed_login_attempt(request, normalized_username)
        logger.warning("Login rejeitado: senha incorreta para '%s'.", normalized_username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas.")

    token = create_session_token(normalized_username)
    _clear_login_rate_limit(request, normalized_username)
    _set_session_cookie(response, token)

    logger.info("Login realizado com sucesso: '%s'", normalized_username)
    return {"username": user.get("username", normalized_username), "role": user.get("role", "admin")}


@router.get("/me", response_model=AuthSessionResponse)
def auth_me(request: Request, response: Response) -> dict:
    user = _resolve_authenticated_user(request)
    if not user:
        _clear_session_cookie(response)
        return {"authenticated": False, "username": "", "role": ""}
    return {"authenticated": True, "username": user["username"], "role": user["role"]}


@router.post("/logout", response_model=AuthStatusResponse)
def auth_logout(response: Response) -> dict:
    _clear_session_cookie(response)
    return {"success": True}


def _normalize_auth_lookup(value: str) -> str:
    return str(value or "").strip().lower()

