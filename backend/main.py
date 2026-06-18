"""Entrypoint da API FastAPI de auditoria (montagem do app e middlewares).

Responsável por inicializar e configurar a aplicação ASGI servida em produção
(Cloud Run) e em dev:

- carrega ``.env`` (raiz do projeto e backend/, este último com override);
- inicializa logging, overrides de DNS e, opcionalmente, o Sentry;
- valida credenciais de runtime (estrito em produção);
- define o ``lifespan`` (startup/shutdown): init do banco, reconciliação de runs
  de sync da Telefonia órfãos e flush da fila de saved-files no shutdown;
- configura CORS, headers de segurança e um rate limit global em memória;
- expõe um endpoint interno de cron (Knowledge Agent) protegido por token;
- inclui todos os routers da API (``/api/...``);
- monta o frontend estático (``dist/``) com política de cache e fallback SPA.

Custo de API: este módulo em si não chama Azure OpenAI/Speech (só faz wiring); o
log de boot apenas informa o deployment configurado. As rotas incluídas é que
podem gerar custo. A inicialização carrega ``services`` (que re-exporta o pipeline
de IA), mas não dispara chamadas pagas no import.
"""

import logging
import asyncio
import hashlib
import os
import sys
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=True)

from core.classification import classify_multiple_audios
import db.database as database
from routers.admin import router as admin_router
from routers.audit import router as audit_router
from routers.auth import SESSION_COOKIE_NAME, router as auth_router
from routers.classifier import router as classifier_router
from routers.common import generate_temporary_password as _generate_temporary_password
from routers.automation import router as automation_router
from routers.telefonia import router as telefonia_router
from routers.review import router as review_router
from routers.saved_files import router as saved_files_router
from routers.supervisor import router as supervisor_router
from routers.system import router as system_router
from routers.ai_feedback import router as ai_feedback_router
from routers.golden_dataset import router as golden_dataset_router
from routers.admin_criteria import router as admin_criteria_router
from routers.admin_sector_aliases import router as admin_sector_aliases_router
from routers.admin_ai_prompts import router as admin_ai_prompts_router
from routers.operadores import router as operadores_router
from routers.supervisores import router as supervisores_router
from routers.fechamento import router as fechamento_router
from services import AI_AUDIT_MODEL, AI_MODEL
from core.config import validate_runtime_credentials
from core.logging_config import setup_logging
from core.network_utils import apply_dns_overrides

setup_logging()
apply_dns_overrides()
logger = logging.getLogger(__name__)


try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
except Exception as exc:  # pragma: no cover - only hit when the optional package is absent/broken
    sentry_sdk = None
    LoggingIntegration = None
    _SENTRY_IMPORT_ERROR = exc
else:
    _SENTRY_IMPORT_ERROR = None


def _runtime_environment() -> str:
    return os.getenv("SENTRY_ENVIRONMENT") or os.getenv("ENVIRONMENT", "development").strip().lower()


def _parse_sentry_sample_rate(env_name: str, default: float) -> float:
    raw_value = os.getenv(env_name)
    if raw_value is None or str(raw_value).strip() == "":
        return default
    try:
        parsed = float(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning("%s invalido para Sentry: %r. Usando %.2f.", env_name, raw_value, default)
        return default
    return min(1.0, max(0.0, parsed))


def _sentry_monitoring_disabled() -> bool:
    flag = (os.getenv("SENTRY_ENABLED") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        return True
    return bool(os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)


def _scrub_sentry_event(event, _hint):
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            sensitive_headers = {"authorization", "cookie", "set-cookie", "x-api-key", "x-openai-api-key"}
            for header_name in list(headers.keys()):
                if str(header_name).lower() in sensitive_headers:
                    headers[header_name] = "[Filtered]"
    return event


def _initialize_sentry() -> None:
    if _sentry_monitoring_disabled():
        return
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    if sentry_sdk is None:
        logger.warning("SENTRY_DSN configurado, mas sentry-sdk nao esta disponivel: %s", _SENTRY_IMPORT_ERROR)
        return

    environment = _runtime_environment()
    integrations = []
    if LoggingIntegration is not None:
        integrations.append(LoggingIntegration(level=logging.INFO, event_level=logging.ERROR))
    try:
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except Exception as exc:  # pragma: no cover - defensive against optional integration changes
        logger.debug("Integracao FastAPI do Sentry indisponivel: %s", exc)
    else:
        integrations.append(FastApiIntegration())

    init_kwargs = {
        "dsn": dsn,
        "environment": environment,
        "traces_sample_rate": _parse_sentry_sample_rate("SENTRY_TRACES_SAMPLE_RATE", 0.05),
        "send_default_pii": False,
        "attach_stacktrace": True,
        "before_send": _scrub_sentry_event,
    }
    profiles_sample_rate = _parse_sentry_sample_rate("SENTRY_PROFILES_SAMPLE_RATE", 0.0)
    if profiles_sample_rate > 0:
        init_kwargs["profiles_sample_rate"] = profiles_sample_rate
    if integrations:
        init_kwargs["integrations"] = integrations

    release = (os.getenv("SENTRY_RELEASE") or os.getenv("K_REVISION") or os.getenv("GIT_COMMIT_SHA") or "").strip()
    if release:
        init_kwargs["release"] = release
    server_name = (os.getenv("K_SERVICE") or os.getenv("HOSTNAME") or "").strip()
    if server_name:
        init_kwargs["server_name"] = server_name

    try:
        sentry_sdk.init(**init_kwargs)
    except Exception:
        logger.exception("Falha ao inicializar Sentry.")
        return

    sentry_sdk.set_tag("service", "backend")
    if os.getenv("K_SERVICE"):
        sentry_sdk.set_tag("cloud_run_service", os.getenv("K_SERVICE"))
    logger.info("Sentry habilitado para environment=%s release=%s", environment, release or "unset")


_initialize_sentry()

validate_runtime_credentials(strict=os.getenv("ENVIRONMENT", "development").strip().lower() == "production")

# ── Lifecycle (startup / shutdown) ───────────────────────────────────────────

_DB_INITIALIZED = False


def _initialize_database_once() -> None:
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return
    if os.getenv("PYTEST_CURRENT_TEST"):
        logger.info("Pytest detected - skipping database.init_db() during app startup")
        return

    logger.info("Inicializando banco de dados")
    try:
        database.init_db()
    except RuntimeError:
        if os.getenv("ENVIRONMENT", "development").strip().lower() == "production":
            raise
        logger.exception("Database initialization failed (development mode, continuing)")
    else:
        _DB_INITIALIZED = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida do app (startup antes do ``yield``, shutdown depois).

    Startup: inicializa o banco uma única vez e reconcilia runs de sync da
    Telefonia abandonados por restart do pod (marca como ``interrupted`` os com
    heartbeat stale). Não há loop residente de automação — o ciclo só acorda por
    scheduler HTTP externo (GCP Cloud Scheduler; Azure Container Apps Job/Logic
    App) em ``/api/automation/cron/run`` ou pela UI.

    Shutdown: aguarda (com timeout) o flush da fila de sincronização de
    saved-files. Falhas em startup/shutdown são logadas, não propagadas (exceto a
    de banco em produção, tratada em ``_initialize_database_once``).
    """
    # Startup
    _initialize_database_once()
    # Reconcilia runs de sync da Telefonia abandonados em restart do pod (v1.3.95).
    try:
        from db import database as _db
        from repositories.telefonia import reconcile_stale_telefonia_sync_runs

        reconciled = reconcile_stale_telefonia_sync_runs(_db.get_connection, stale_after_seconds=120)
        if reconciled:
            logger.warning(
                "Bootstrap: %d run(s) de sync da Telefonia marcado(s) como 'interrupted' (heartbeat stale).",
                reconciled,
            )
    except Exception:
        logger.exception("Bootstrap: falha ao reconciliar runs orfaos de sync da Telefonia.")
    logger.info("Servidor iniciado")
    # Nao existe loop residente de automacao: o ciclo so acorda por scheduler
    # externo (/api/automation/cron/run, 1x/dia) ou pela UI.
    logger.info("Automacao por gatilho externo; use /api/automation/cron/run.")
    yield
    # Shutdown
    try:
        from core.saved_files_sync_queue import flush as flush_saved_files_sync_queue

        await asyncio.to_thread(flush_saved_files_sync_queue, 15.0)
    except Exception:
        logger.exception("Falha ao aguardar flush da fila saved-files no shutdown.")
    logger.info("Servidor encerrado")

app = FastAPI(title="nstech Audit API", lifespan=lifespan)

_azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip() or "(nao configurado)"
_legacy_genai = AI_MODEL or AI_AUDIT_MODEL or "desativado"
logger.info(
    "Provedor IA: Azure GPT-4o (deployment=%s). GenAI legado: %s.",
    _azure_deployment,
    _legacy_genai,
)

ALLOWED_CORS_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]


def _is_production_environment() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() == "production"


def _resolve_allowed_origins() -> list[str]:
    origins = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    if "*" in origins:
        if _is_production_environment():
            raise RuntimeError(
                "ALLOWED_ORIGINS='*' is not permitted in production. "
                "Set explicit origins separated by commas."
            )
        return ["http://localhost:5173"]
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_allowed_origins(),
    allow_credentials=True,
    allow_methods=ALLOWED_CORS_METHODS,
    allow_headers=["Content-Type", "Authorization", "X-Requested-With", "Accept", "Origin"],
)




@app.middleware("http")
async def add_security_headers(request, call_next):
    """Middleware: adiciona cabeçalhos de segurança a toda resposta.

    Define (via ``setdefault``, sem sobrescrever cabeçalhos já presentes):
    X-Content-Type-Options, X-Frame-Options, Referrer-Policy, Permissions-Policy e
    X-Permitted-Cross-Domain-Policies. Em produção, adiciona também
    Strict-Transport-Security (HSTS). Retorna a resposta da cadeia.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "microphone=(), camera=(), geolocation=()")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    if _is_production_environment():
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# ── Global API rate limiting ─────────────────────────────────────────────────

_GLOBAL_RATE_LIMIT: OrderedDict[str, list[float]] = OrderedDict()
_GLOBAL_RATE_LIMIT_LOCK = asyncio.Lock()
_RATE_LIMIT_LAST_CLEANUP: float = 0.0
_RATE_LIMIT_CLEANUP_INTERVAL: float = 300.0  # sweep stale IPs every 5 minutes


def _get_global_rate_limit_settings() -> tuple[bool, int, int]:
    enabled = os.getenv("ENVIRONMENT", "development").strip().lower() == "production"
    flag = (os.getenv("ENABLE_GLOBAL_RATE_LIMIT") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        enabled = True
    elif flag in ("0", "false", "no", "off"):
        enabled = False
    max_requests = int(os.getenv("GLOBAL_RATE_LIMIT_MAX_REQUESTS", "200"))
    window_seconds = int(os.getenv("GLOBAL_RATE_LIMIT_WINDOW_SECONDS", "60"))
    return enabled, max(1, max_requests), max(1, window_seconds)


def _get_global_rate_limit_max_keys() -> int:
    raw = os.getenv("GLOBAL_RATE_LIMIT_MAX_KEYS", "10000")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 10000
    return max(1, parsed)


def _sweep_global_rate_limit(now: float, cutoff: float, max_keys: int) -> None:
    stale_keys = [key for key, timestamps in _GLOBAL_RATE_LIMIT.items() if not timestamps or timestamps[-1] < cutoff]
    for key in stale_keys:
        _GLOBAL_RATE_LIMIT.pop(key, None)

    while len(_GLOBAL_RATE_LIMIT) > max_keys:
        _GLOBAL_RATE_LIMIT.popitem(last=False)


def _resolve_client_ip(request: Request) -> str:
    # Cloud Run / Load Balancer injeta X-Forwarded-For com o IP real do cliente.
    # O primeiro IP da lista é o do usuário original.
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client and request.client.host else "unknown"


def _resolve_rate_limit_key(request: Request) -> str:
    session_token = (request.cookies.get(SESSION_COOKIE_NAME) or "").strip()
    if session_token:
        digest = hashlib.sha256(session_token.encode("utf-8")).hexdigest()[:24]
        return f"session:{digest}"
    return f"ip:{_resolve_client_ip(request)}"


_RATE_LIMIT_EXEMPT_PREFIXES = ("/docs", "/openapi.json", "/redoc")
# Auth endpoints possuem seu próprio rate limiter dedicado (login_rate_limit).
# Incluí-los no global causa falso-positivo quando múltiplos usuários
# compartilham o mesmo IP (proxy/LB do Cloud Run).
_RATE_LIMIT_EXEMPT_PATHS = frozenset({
    "/api/auth/me",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/health",
    "/api/ui/theme",
    "/api/system/client-logs",
})


@app.middleware("http")
async def global_rate_limit_middleware(request: Request, call_next):
    """Middleware: rate limit global por sessão/IP em janela deslizante.

    Habilitado em produção (ou via ``ENABLE_GLOBAL_RATE_LIMIT``). Só limita rotas
    ``/api/...``, isentando prefixes de docs e paths com limiter próprio (auth,
    health etc. em ``_RATE_LIMIT_EXEMPT_PATHS``). A chave é a sessão (hash do
    cookie) quando logado, senão o IP do cliente (X-Forwarded-For). Mantém os
    timestamps por chave em memória (``_GLOBAL_RATE_LIMIT``); ao exceder
    ``max_requests`` na janela, responde 429 com cabeçalho ``Retry-After``. Faz
    sweep periódico das chaves stale para evitar vazamento de memória.

    Efeitos colaterais: muta o estado em memória do processo (não compartilhado
    entre réplicas). Retorna a resposta da cadeia ou um 429.
    """
    global _RATE_LIMIT_LAST_CLEANUP

    enabled, max_requests, window_seconds = _get_global_rate_limit_settings()
    max_keys = _get_global_rate_limit_max_keys()
    if not enabled:
        return await call_next(request)

    path = request.url.path
    if path.startswith(_RATE_LIMIT_EXEMPT_PREFIXES) or not path.startswith("/api/") or path in _RATE_LIMIT_EXEMPT_PATHS:
        return await call_next(request)

    rate_limit_key = _resolve_rate_limit_key(request)
    now = time.monotonic()
    cutoff = now - window_seconds

    async with _GLOBAL_RATE_LIMIT_LOCK:
        timestamps = [t for t in _GLOBAL_RATE_LIMIT.get(rate_limit_key, []) if t > cutoff]
        _GLOBAL_RATE_LIMIT[rate_limit_key] = timestamps
        _GLOBAL_RATE_LIMIT.move_to_end(rate_limit_key)
        if len(timestamps) >= max_requests:
            retry_after = int(window_seconds - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Limite de requisicoes excedido. Tente novamente em alguns segundos."},
                headers={"Retry-After": str(max(1, retry_after))},
            )
        timestamps.append(now)

        # Periodic sweep: remove IPs with no recent requests to prevent memory leak
        if now - _RATE_LIMIT_LAST_CLEANUP > _RATE_LIMIT_CLEANUP_INTERVAL:
            _RATE_LIMIT_LAST_CLEANUP = now
            _sweep_global_rate_limit(now, cutoff, max_keys)
        elif len(_GLOBAL_RATE_LIMIT) > max_keys:
            _sweep_global_rate_limit(now, cutoff, max_keys)

    return await call_next(request)


# ── Internal cron endpoint (scheduler externo) ────────────────────────────────


@app.post("/api/internal/cron/knowledge-agent")
async def cron_knowledge_agent(request: Request):
    """Rota interna para o scheduler externo executar o DB Knowledge Agent.

    Protegida por token via header ``Authorization: Bearer <CRON_SECRET_TOKEN>``.
    GCP atual: Cloud Scheduler. Azure equivalente: Container Apps Job agendado
    ou Logic App chamando esta URL diariamente as 18:00 com o mesmo bearer token.
    """
    expected_token = os.getenv("CRON_SECRET_TOKEN", "").strip()
    if not expected_token:
        logger.error("CRON_SECRET_TOKEN não configurado — rota cron desabilitada")
        return JSONResponse(status_code=503, content={"detail": "Cron não configurado."})

    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header != f"Bearer {expected_token}":
        return JSONResponse(status_code=403, content={"detail": "Token inválido."})

    try:
        import asyncio
        from jobs.scheduler import run_knowledge_agent
        files = await asyncio.to_thread(run_knowledge_agent)
        return {"status": "ok", "documents_generated": len(files), "files": files}
    except Exception as exc:
        logger.exception("Erro ao executar Knowledge Agent via cron")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


app.include_router(auth_router)
app.include_router(system_router)
app.include_router(saved_files_router)
app.include_router(audit_router)
app.include_router(classifier_router)
app.include_router(supervisor_router)
app.include_router(review_router)
app.include_router(admin_router)
app.include_router(automation_router)
app.include_router(telefonia_router)
app.include_router(ai_feedback_router)
app.include_router(golden_dataset_router)
app.include_router(admin_criteria_router)
app.include_router(admin_sector_aliases_router)
app.include_router(admin_ai_prompts_router)
app.include_router(operadores_router)
app.include_router(supervisores_router)
app.include_router(fechamento_router)


dist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist"))
if os.path.exists(dist_path):
    logger.info("Servindo frontend em: %s", dist_path)
    
    class CacheControlStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            from starlette.exceptions import HTTPException
            try:
                response = await super().get_response(path, scope)
            except HTTPException as ex:
                if ex.status_code == 404:
                    response = await super().get_response("index.html", scope)
                else:
                    raise

            if response.status_code == 404:
                response = await super().get_response("index.html", scope)

            if response.status_code == 200:
                if path == "" or path == "/" or path.endswith(".html") or path == "index.html" or response.headers.get("content-type") == "text/html; charset=utf-8":
                    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                elif path.startswith("assets/"):
                    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response

    app.mount("/", CacheControlStaticFiles(directory=dist_path, html=True), name="static")
else:
    logger.warning("Frontend dist folder not found at %s", dist_path)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
