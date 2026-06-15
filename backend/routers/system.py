import json
import logging
import os
import re
from contextlib import nullcontext
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import sentry_sdk
except Exception:  # pragma: no cover - Sentry is optional outside monitored deployments
    sentry_sdk = None

from db.domain_constants import (
    AUDIT_STATUS_AWAITING_PAIR,
    AUDIT_STATUS_PENDING_APPROVAL,
    DEFAULT_REVIEW_QUEUE_STATUS,
)
import db.database as database
from repositories import audits
from routers.auth import require_admin, require_authenticated_user
from schemas import AuditResult


router = APIRouter(tags=["system"])


class ConfigUpdateRequest(BaseModel):
    chave: str
    valor: str
    motivo: str | None = None


class ClientLogRequest(BaseModel):
    level: str = Field(..., max_length=16)
    message: str = Field(..., max_length=2000)
    stack: str | None = Field(default=None, max_length=12000)
    url: str | None = Field(default=None, max_length=2048)
    user_agent: str | None = Field(default=None, max_length=512)


_CLIENT_LOG_LEVELS = {
    "debug": (logging.DEBUG, "debug"),
    "info": (logging.INFO, "info"),
    "warn": (logging.WARNING, "warning"),
    "warning": (logging.WARNING, "warning"),
    "error": (logging.ERROR, "error"),
    "fatal": (logging.CRITICAL, "fatal"),
}


def _normalize_client_log_level(raw_level: str | None) -> tuple[int, str]:
    return _CLIENT_LOG_LEVELS.get((raw_level or "").strip().lower(), (logging.ERROR, "error"))


def _truncate_client_log_value(value: str | None, max_length: int = 4000) -> str | None:
    if value is None:
        return None
    return str(value)[:max_length]


def _sanitize_client_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return _truncate_client_log_value(raw_url, 2048)
    sanitized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return _truncate_client_log_value(sanitized or raw_url, 2048)


def _capture_client_log_in_sentry(req: ClientLogRequest, sentry_level: str) -> None:
    if sentry_sdk is None or sentry_level not in {"warning", "error", "fatal"}:
        return
    try:
        scope_factory = getattr(sentry_sdk, "new_scope", None) or getattr(sentry_sdk, "push_scope", None)
        with (scope_factory() if scope_factory else nullcontext(None)) as scope:
            if scope is not None:
                scope.set_tag("source", "frontend")
                scope.set_tag("client_log_level", sentry_level)
                frontend_url = _sanitize_client_url(req.url)
                if frontend_url:
                    scope.set_extra("frontend_url", frontend_url)
                if req.user_agent:
                    scope.set_extra("user_agent", _truncate_client_log_value(req.user_agent, 512))
                if req.stack:
                    scope.set_extra("frontend_stack", _truncate_client_log_value(req.stack))
            sentry_sdk.capture_message(_truncate_client_log_value(req.message, 1000) or "Frontend error", level=sentry_level)
    except Exception:
        logger.exception("Falha ao encaminhar log do frontend para o Sentry.")


VALID_UI_THEME_PRESETS = {"corporativo", "opentech", "nstech"}
_SEMVER_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:$|[-_])")


def _parse_semver(value: str | None) -> tuple[int, int, int] | None:
    match = _SEMVER_PATTERN.match((value or "").strip())
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _format_semver(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]}.{version[2]}"


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_package_version(root: Path) -> str | None:
    try:
        package_data = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    version = str(package_data.get("version") or "").strip()
    return version or None


def _read_latest_log_version(root: Path) -> str | None:
    versions_dir = root / "logs" / "versions"
    if not versions_dir.exists():
        return None

    latest: tuple[int, int, int] | None = None
    for version_file in versions_dir.glob("*.md"):
        parsed = _parse_semver(version_file.stem)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return _format_semver(latest) if latest is not None else None


@lru_cache(maxsize=1)
def _resolve_app_version() -> str | None:
    env_version = (os.getenv("APP_VERSION") or "").strip()
    if env_version:
        return env_version

    root = _project_root()
    package_version = _read_package_version(root)
    latest_log_version = _read_latest_log_version(root)
    package_semver = _parse_semver(package_version)
    log_semver = _parse_semver(latest_log_version)

    if package_semver and log_semver:
        return latest_log_version if log_semver >= package_semver else package_version
    return latest_log_version or package_version


def _env_text(name: str) -> str | None:
    value = (os.getenv(name) or "").strip()
    return value or None


def _build_release_info() -> dict:
    commit_sha = (
        _env_text("GIT_COMMIT_SHA")
        or _env_text("COMMIT_SHA")
        or _env_text("SOURCE_COMMIT")
        or _env_text("SENTRY_RELEASE")
    )
    return {
        "version": _resolve_app_version(),
        "revision": _env_text("K_REVISION"),
        "service": _env_text("K_SERVICE"),
        "configuration": _env_text("K_CONFIGURATION"),
        "commit_sha": commit_sha,
        "commit_short": commit_sha[:12] if commit_sha else None,
        "environment": _env_text("ENVIRONMENT"),
    }


def _normalize_ui_theme_preset(raw_value: str | None) -> str:
    preset = (raw_value or "").strip().lower()
    if preset in VALID_UI_THEME_PRESETS:
        return preset
    return "corporativo"


@router.post("/api/system/client-logs")
async def receive_client_logs(req: ClientLogRequest):
    log_level, sentry_level = _normalize_client_log_level(req.level)
    console_log_level = logging.WARNING if log_level >= logging.ERROR else log_level
    logger.log(
        console_log_level,
        "[Frontend Error] %s: %s | URL: %s | User-Agent: %s\nStack: %s",
        req.level.upper(),
        req.message,
        _sanitize_client_url(req.url),
        _truncate_client_log_value(req.user_agent, 512),
        _truncate_client_log_value(req.stack) or "N/A"
    )
    _capture_client_log_in_sentry(req, sentry_level)
    return {"status": "ok"}


@router.get("/api/system/network-check")
async def check_network_connectivity(
    host: str = "34.171.63.68", 
    port: int = 28443, 
    _user: dict = Depends(require_admin)
) -> dict:
    import asyncio
    import socket
    import time
    
    start = time.time()
    try:
        # Tenta abrir uma conexão TCP básica com timeout curto
        conn = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(conn, timeout=3.0)
        writer.close()
        await writer.wait_closed()
        latency = (time.time() - start) * 1000
        return {
            "success": True,
            "target": f"{host}:{port}",
            "latency_ms": round(latency, 2),
            "message": "Conexão TCP estabelecida com sucesso."
        }
    except Exception as e:
        return {
            "success": False,
            "target": f"{host}:{port}",
            "error": str(e),
            "type": type(e).__name__,
            "message": "Falha na conexão TCP."
        }


@router.get("/api/health")
def health_check() -> dict:
    return {
        "status": "online",
        "division": "NSTECH",
        "release": _build_release_info(),
    }


@router.get("/api/configuracoes")
def get_configuracoes(_user: dict = Depends(require_admin)) -> dict:
    # mask_secrets=True por default no repositorio: chaves com is_secret=true
    # voltam mascaradas. Para obter o valor real, use os getters internos.
    return database.get_all_configs()


@router.post("/api/configuracoes")
def update_configuracao(req: ConfigUpdateRequest, user: dict = Depends(require_admin)) -> dict:
    sucesso = database.update_config(
        req.chave,
        req.valor,
        alterado_por=user.get("username", "admin"),
        motivo=req.motivo or "",
        origem="ui",
    )
    if sucesso:
        return {"status": "success"}
    logger.error(
        "Falha ao persistir configuracao chave=%s valor_len=%s alterado_por=%s",
        req.chave,
        len(req.valor or ""),
        user.get("username"),
    )
    raise HTTPException(status_code=500, detail="Erro ao atualizar a configuração")


@router.get("/api/configuracoes/audit-log")
def list_configuracoes_audit_log(
    chave: str | None = None,
    limit: int = 50,
    _user: dict = Depends(require_admin),
) -> list[dict]:
    """Trilha de mudancas em `configuracoes`. Filtra por `chave` se informado."""
    from repositories.configuration import list_audit_log

    return list_audit_log(database.get_connection, chave=chave, limit=limit)


@router.get("/api/ui/theme")
def get_ui_theme(_user: dict = Depends(require_authenticated_user)) -> dict:
    return {
        "preset": _normalize_ui_theme_preset(database.get_config_value("tema_visual", "corporativo")),
    }


@router.get("/api/dashboard/stats")
def get_dashboard_stats(_user: dict = Depends(require_authenticated_user)) -> dict:
    return database.get_stats()


@router.get("/api/dashboard/history")
def get_dashboard_history(_user: dict = Depends(require_authenticated_user)) -> list:
    return database.get_history()


@router.get("/api/sectors")
def get_sectors(_user: dict = Depends(require_authenticated_user)) -> list:
    return database.get_sectors()


@router.get("/api/dashboard/ligacoes-auditadas/resumo")
def get_dashboard_ligacoes_auditadas_resumo(
    sector_id: str = None,
    setor: str = None,
    _user: dict = Depends(require_authenticated_user),
) -> dict:
    return database.get_resumo_ligacoes_auditadas(sector_id or setor)


@router.get("/api/dashboard/ligacoes-auditadas")
def get_dashboard_ligacoes_auditadas(
    limit: int = 100,
    qualidade: str = None,
    setor: str = None,
    sector_id: str = None,
    _user: dict = Depends(require_authenticated_user),
) -> list:
    limit = max(1, min(limit, 1000))
    return database.listar_ligacoes_auditadas(limit=limit, qualidade=qualidade, setor=sector_id or setor)


@router.get("/api/dashboard/classificacao-revisao")
def get_dashboard_classificacao_revisao(
    limit: int | None = None,
    status: str = DEFAULT_REVIEW_QUEUE_STATUS,
    sector_id: str = None,
    _user: dict = Depends(require_authenticated_user),
) -> list:
    return database.listar_fila_revisao_classificacao(limit=limit, status=status, sector_id=sector_id)


@router.get("/api/reports/exports")
def list_report_exports(
    limit: int = 100,
    report_kind: str = None,
    file_format: str = None,
    operator_name: str = None,
    _user: dict = Depends(require_authenticated_user),
) -> list:
    limit = max(1, min(limit, 1000))
    return database.list_report_exports(
        limit=limit,
        report_kind=report_kind,
        file_format=file_format,
        operator_name=operator_name,
    )


@router.post("/api/dashboard/save")
def save_to_dashboard(
    result: AuditResult,
    _user: dict = Depends(require_admin),
    alert_id: str = None,
    alert_label: str = None,
    operator_id: str = None,
    sector_id: str = None,
    ai_feedback: str = None,
    audio_date: str = None,
) -> dict:
    import hashlib

    input_hash = str(getattr(result, "input_hash", "") or "").strip()
    if not input_hash:
        result_str = f"{result.summary}{result.score}{result.timestamp}"
        input_hash = hashlib.sha256(result_str.encode()).hexdigest()

    effective_operator_id = str(operator_id or getattr(result, "operatorId", "") or "").strip()
    if effective_operator_id:
        result.operatorId = effective_operator_id

    # Inject audio_date into result if provided
    if audio_date:
        result.audio_date = audio_date

    try:
        existing = audits.get_audit_by_hash(database.get_connection, input_hash)
        if existing:
            audit_id = database.update_audit_result(
                input_hash, 
                result, 
                ai_feedback=ai_feedback or getattr(result, "ai_feedback", None)
            )
            if not audit_id:
                raise ValueError("Auditoria existente nao encontrada para atualizacao.")
            # Update operator ID if changed
            if effective_operator_id:
                conn = database.get_connection()
                try:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE audits SET operator_id = %s WHERE id = %s", (effective_operator_id, audit_id))
                    conn.commit()
                finally:
                    conn.close()
            stored = audits.get_audit_by_id(database.get_connection, audit_id)
            review_status = (stored or {}).get("status") or AUDIT_STATUS_AWAITING_PAIR
            if review_status not in {AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_PENDING_APPROVAL}:
                review_status = AUDIT_STATUS_PENDING_APPROVAL
            queued = {"audit_id": audit_id, "status": review_status, "pending_count": 0, "open_count": 0}
        else:
            queued = database.queue_audit_for_supervisor_review(
                result,
                input_hash=input_hash,
                alert_id=alert_id,
                alert_label=alert_label,
                operator_id=effective_operator_id or None,
                sector_id=sector_id,
                ai_feedback=ai_feedback or getattr(result, "ai_feedback", None),
                rebalance=False,
            )
            queued = {**queued, "status": AUDIT_STATUS_AWAITING_PAIR}
    except Exception as exc:
        logger.exception("[save_to_dashboard] Falha ao enfileirar auditoria: %s", exc)
        raise HTTPException(status_code=500, detail=f"Erro interno ao salvar auditoria: {exc}")

    logger.info(
        "[pair-queue] Audit saved: audit_id=%s, status=%s, pending_count=%s, open_count=%s, operator=%s/%s",
        queued.get("audit_id"), queued.get("status"),
        queued.get("pending_count"), queued.get("open_count"),
        result.operatorName, effective_operator_id,
    )

    review_status = queued.get("status")
    if review_status not in {AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_PENDING_APPROVAL}:
        review_status = AUDIT_STATUS_AWAITING_PAIR
    message = (
        "Auditoria arquivada. Revise, edite ou descarte antes de enviar ao supervisor."
        if review_status == AUDIT_STATUS_AWAITING_PAIR
        else "Auditoria atualizada. Ela permanece enviada ao supervisor."
    )
    return {
        "success": True,
        "audit_id": queued.get("audit_id"),
        "review_status": review_status,
        "message": message,
    }


@router.put("/api/dashboard/audits/{audit_id}")
def update_saved_audit(
    audit_id: int,
    result: AuditResult,
    _user: dict = Depends(require_admin),
) -> dict:
    try:
        outcome = database.update_audit_by_id(
            audit_id,
            result,
            ai_feedback=getattr(result, "ai_feedback", None),
        )
        if not outcome or not outcome.get("updated"):
            raise HTTPException(status_code=404, detail="Auditoria nao encontrada.")
        return {"success": True, "audit_id": audit_id}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar auditoria.")


@router.post("/api/dashboard/force-send")
def force_send_to_supervisor(
    audit_id: int,
    force: bool = False,
    _user: dict = Depends(require_admin),
) -> dict:
    try:
        from db.domain_constants import (
            AUDIT_STATUS_AWAITING_PAIR,
            AUDIT_STATUS_PENDING_APPROVAL,
        )

        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Auditoria nao encontrada.")

        current_status = audit.get("status")
        if current_status == AUDIT_STATUS_PENDING_APPROVAL:
            return {
                "success": True,
                "audit_id": audit_id,
                "review_status": AUDIT_STATUS_PENDING_APPROVAL,
                "message": "Auditoria ja esta na fila do supervisor.",
            }
        
        # Validação de cota mensal no painel supervisor (Máximo de auditorias por operador por mês)
        # O auditor humano pode ignorar este aviso via parâmetro 'force'.
        if not force:
            operator_name = audit.get("operator_name")
            operator_id = audit.get("operator_id")
            if operator_name:
                from datetime import datetime
                from core.automation import _get_monthly_audit_quota
                from repositories.audits import get_supervisor_audit_count_for_month
                
                now = datetime.now()
                cota_max = _get_monthly_audit_quota()
                count = get_supervisor_audit_count_for_month(
                    database.get_connection, 
                    operator_name, 
                    now.year, 
                    now.month, 
                    operator_id
                )
                
                if count >= cota_max:
                    raise HTTPException(
                        status_code=429,
                        detail=f"Limite de {cota_max} auditorias mensais atingido no painel do supervisor para este operador. "
                               "Delete uma auditoria existente para liberar espaço, ou ative a opção de forçar envio."
                    )

        if current_status != AUDIT_STATUS_AWAITING_PAIR:
            raise HTTPException(
                status_code=409,
                detail=f"Auditoria nao pode ser enviada ao supervisor a partir do status {current_status}.",
            )

        database.update_audit_status(audit_id, AUDIT_STATUS_PENDING_APPROVAL)
        updated = audits.get_audit_by_id(database.get_connection, audit_id) or audit
        review_status = updated.get("status") or AUDIT_STATUS_PENDING_APPROVAL
        return {
            "success": True,
            "audit_id": audit_id,
            "review_status": review_status,
            "message": "Auditoria enviada para a fila do supervisor.",
        }
    except HTTPException:
        raise
    except ValueError as exc:
        logger.warning("[force-send] Envio recusado audit_id=%s: %s", audit_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("[force-send] Erro ao forçar envio audit_id=%s: %s", audit_id, exc)
        raise HTTPException(status_code=500, detail=f"Erro ao forçar envio da auditoria: {exc}")
