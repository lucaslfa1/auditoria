"""Orquestrador de sincronizacao com a plataforma Huawei AICC.

Fluxo:
1. Carrega credenciais da tabela `configuracoes`.
2. Consulta a VDN globalmente, sem filtrar por agentId/mediaType.
3. Complementa a descoberta com o manifesto Contact_Record do OBS.
4. Deduplica por callId, aplica apenas filtros operacionais minimos antes do
   download e tenta baixar via FS/OBS.
5. Salva a midia baixada e deixa o item pendente na fila de triagem.

O sync nao chama auditoria nem decide envio ao supervisor. O objetivo deste
modulo e somente baixar ligacoes da Huawei e disponibiliza-las para triagem.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import httpx

import database
from automation import load_classified_audio, store_classified_audio
from classification import (
    ClassificationResult,
    align_classification_with_catalog,
    classify_with_gpt,
    enforce_alert_hierarchy_guardrail,
    enforce_operator_and_direction_guardrails,
    enforce_parada_desvio_guardrail,
    enforce_temperature_guardrail,
    finalize_classification_result,
    get_mime_type,
    load_audit_criteria_catalog,
    transcribe_for_classification,
)
from core.automation_rules import get_call_duration_seconds
from core.audit import extract_text_from_pdf
from core.huawei_client import OAUTH_DIRECT_MODES, HuaweiAICCClient
from core.huawei_obs_client import HuaweiOBSClient
from db.domain_constants import SOURCE_TYPE_AUDIO, SOURCE_TYPE_PDF

logger = logging.getLogger(__name__)
_HUAWEI_SYNC_LOCK_KEY = 2026042202
DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT = 20
DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS = 10
DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS = 0
DEFAULT_HUAWEI_SYNC_DOWNLOAD_CONCURRENCY = 5
DEFAULT_HUAWEI_SYNC_CLASSIFY_CONCURRENCY = 5
# Timeout generoso o bastante para download via FS (audios podem ter ate 50MB).
_OBS_HTTP_TIMEOUT = 120.0


def _ensure_enabled() -> bool:
    return (os.getenv("ENABLE_HUAWEI_SYNC", "false") or "").strip().lower() == "true"


def _load_config() -> Dict[str, Any]:
    """Le AK/SK/CCID/VDN/App Key da tabela configuracoes.

    Env vars funcionam como override local (`HUAWEI_AK`, etc.).
    """

    def read(key: str) -> str:
        env_key = f"HUAWEI_{key.upper()}"
        if os.getenv(env_key):
            return str(os.getenv(env_key)).strip()
        return str(database.get_config_value(f"huawei_{key}", "") or "").strip()

    cfg = {
        "cms_url": read("cms_url") or read("portal_url"),
        "fs_url": read("fs_url"),
        "cc_id": read("ccid") or read("cc_id"),
        "vdn": read("vdn"),
        "ak": read("ak"),
        "sk": read("sk"),
        "app_key": read("app_key"),
        "app_secret": read("app_secret"),
        "proxy_url": read("proxy_url"),
        "auth_mode": read("auth_mode"),
        # OAuth direct (modo `oauth_direct`): credenciais isoladas do proxy
        # Teledata para o tokenByAkSk + cabecalho X-TenantSpaceID.
        "auth_base_url": read("auth_base_url"),
        "tenant_space_id": read("tenant_space_id"),
        "direct_app_key": read("direct_app_key"),
        "direct_app_secret": read("direct_app_secret"),
        # Credenciais OBS (fallback direto no bucket quando CC-FS retorna 0300012).
        # Lidas do mesmo padrao: env HUAWEI_OBS_* ou tabela configuracoes huawei_obs_*.
        "obs_ak": read("obs_ak"),
        "obs_sk": read("obs_sk"),
        "obs_bucket": read("obs_bucket"),
        "obs_endpoint": read("obs_endpoint"),
    }
        
    return cfg


def _missing_credentials(cfg: Dict[str, Any]) -> List[str]:
    auth_mode = str(cfg.get("auth_mode") or "proxy").strip().lower()
    if auth_mode in OAUTH_DIRECT_MODES:
        obrigatorios = ["cc_id", "vdn", "direct_app_key", "direct_app_secret"]
    else:
        obrigatorios = ["ak", "sk", "cc_id", "vdn"]
    return [k for k in obrigatorios if not cfg.get(k)]


def _slug_filename_part(value: Any, fallback: str, max_len: int = 64) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    parts: list[str] = []
    last_separator = False
    for char in normalized:
        if unicodedata.category(char) == "Mn":
            continue
        if char.isalnum():
            parts.append(char)
            last_separator = False
            continue
        if not last_separator and parts:
            parts.append("_")
            last_separator = True

    slug = "".join(parts).strip("_")
    if not slug:
        slug = fallback
    slug = slug[:max_len].rstrip("_")
    return slug or fallback


def _make_filename(op_nome: str, call_id: str, extensao: str) -> str:
    operator_name = str(op_nome or "").strip()
    if _normalize_identity_text(operator_name) == "nao identificado":
        operator_part = "operador_nao_identificado"
    else:
        operator_part = _slug_filename_part(operator_name, "operador")
    call_part = _slug_filename_part(call_id, "call", max_len=48)
    extension = _slug_filename_part(extensao, "wav", max_len=12)
    return f"ligacao_huawei_{operator_part}_{call_part}.{extension}"


def _resolve_call_key(chamada: dict) -> str:
    return str(
        chamada.get("callId")
        or chamada.get("callid")
        or chamada.get("id")
        or ""
    ).strip()


def _clean_obs_prefix(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"none", "null"}:
        return ""
    return text


def _obs_prefix_candidates(interacao: dict, agent_id: Any) -> list[str]:
    caller_no = interacao.get("callerNo")
    if not _clean_obs_prefix(caller_no):
        caller_no = interacao.get("caller_no")
    callee_no = interacao.get("calleeNo")
    if not _clean_obs_prefix(callee_no):
        callee_no = interacao.get("callee_no")
    raw_candidates = [
        caller_no,
        callee_no,
        agent_id,
        interacao.get("workNo"),
    ]
    prefixes: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        prefix = _clean_obs_prefix(raw)
        if not prefix or prefix in seen:
            continue
        seen.add(prefix)
        prefixes.append(prefix)
    return prefixes


def _obs_match_ids(interacao: dict, call_id: str) -> list[str]:
    call_id_text = _clean_obs_prefix(call_id)
    call_id_parts = call_id_text.split("-")
    call_id_suffix = (
        call_id_parts[-1]
        if len(call_id_parts) > 1 and all(part.isdigit() for part in call_id_parts)
        else ""
    )
    raw_candidates = [
        call_id_text,
        call_id_suffix,
        interacao.get("recordId"),
        interacao.get("recordID"),
        interacao.get("record_id"),
        interacao.get("contactId"),
        interacao.get("contact_id"),
        interacao.get("callSerialno"),
        interacao.get("callSerialNo"),
        interacao.get("call_no"),
        interacao.get("callNo"),
    ]
    match_ids: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        value = _clean_obs_prefix(raw)
        if not value or value in seen:
            continue
        seen.add(value)
        match_ids.append(value)
    return match_ids


def _download_id_candidates(interacao: dict, call_id: str) -> list[str]:
    """IDs que podem resolver midia na Huawei/OBS, em ordem de menor risco."""
    return _obs_match_ids(interacao, call_id)


_DURATION_KEYS = (
    "duration",
    "duracao",
    "callDuration",
    "calllDuration",
    "talkDuration",
    "talkTime",
    "durationSeconds",
    "durationSec",
    "recordDuration",
    "recordTime",
)


def _call_duration_is_known(interacao: dict) -> bool:
    for key in _DURATION_KEYS:
        value = interacao.get(key)
        if value in (None, ""):
            continue
        try:
            int(float(str(value).strip()))
            return True
        except (TypeError, ValueError):
            continue

    start = (
        _coerce_huawei_time_ms(interacao.get("callBegin"))
        or _coerce_huawei_time_ms(interacao.get("beginTime"))
        or _coerce_huawei_time_ms(interacao.get("ackBegin"))
        or _coerce_huawei_time_ms(interacao.get("waitBegin"))
    )
    end = (
        _coerce_huawei_time_ms(interacao.get("callEnd"))
        or _coerce_huawei_time_ms(interacao.get("endTime"))
        or _coerce_huawei_time_ms(interacao.get("logDate"))
    )
    return start is not None and end is not None and end >= start


def _normalize_setor_regra(raw_setor: str) -> str:
    import unicodedata

    normalized = "".join(
        c for c in unicodedata.normalize("NFD", str(raw_setor or "").lower())
        if unicodedata.category(c) != "Mn"
    ).strip()
    if normalized.startswith("rastreamento"):
        return "transferencia"
    if normalized.startswith("uti"):
        return "uti"
    if normalized == "unilever":
        return "logistica_unilever"
    return normalized


# Setores de risco operam apenas com ligacoes EFETUADAS (outbound). Receptivas
# desses setores nao devem ser auditadas — sao descartadas antes do download.
# Mantenha em sincronia com classification._OUTBOUND_DIRECTION_SECTORS.
_RISK_OUTBOUND_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix", "bbm"}


def _should_skip_receptive_risk_call(interacao: dict, operador: dict) -> bool:
    operator_sector = _normalize_setor_regra(str(operador.get("setor") or ""))
    if operator_sector not in _RISK_OUTBOUND_SECTORS:
        return False
    is_call_in = str(interacao.get("isCallIn") or "").strip().lower() == "true"
    return is_call_in


def _get_duration_limits_for_sector(
    raw_setor: str,
    default_min: int,
    default_max: int = DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS,
) -> tuple[int, int]:
    # A coleta de ligacoes deve ser ampla; setor nao deve bloquear download.
    _ = raw_setor
    return max(0, default_min), max(0, default_max)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _cancel_requested(should_cancel: Optional[Callable[[], bool]]) -> bool:
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:
        logger.warning("Sync Huawei: callback de cancelamento falhou.", exc_info=True)
        return False


def _coerce_huawei_time_ms(value: Any) -> Optional[int]:
    numeric = HuaweiAICCClient._coerce_epoch_millis(value)
    if numeric is not None:
        return numeric
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
            return int(dt.astimezone(timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
    return None


def _window_date_strings(begin_ms: int, end_ms: int) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for ms in (begin_ms, end_ms):
        for tz in (timezone.utc, ZoneInfo("America/Sao_Paulo")):
            date_str = datetime.fromtimestamp(ms / 1000, tz=tz).strftime("%Y%m%d")
            if date_str not in seen:
                seen.add(date_str)
                dates.append(date_str)
    return dates


def _query_time_windows(begin_ms: int, end_ms: int) -> list[tuple[int, int]]:
    """Breaks `querycalls` into time slices instead of unsupported pagination."""
    if end_ms < begin_ms:
        return []

    window_minutes = max(
        1,
        _coerce_int(os.getenv("HUAWEI_QUERYCALLS_WINDOW_MINUTES"), 60),
    )
    window_ms = window_minutes * 60 * 1000
    windows: list[tuple[int, int]] = []
    current = begin_ms
    while current <= end_ms:
        chunk_end = min(current + window_ms, end_ms)
        if chunk_end <= current:
            break
        windows.append((current, chunk_end))
        current = chunk_end + 1
    return windows


def _normalize_identity_text(value: Any) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return " ".join(part for part in normalized.replace("_", " ").split() if part)


def _build_operator_indexes(operadores: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for operador in operadores:
        for value in (
            operador.get("id_huawei"),
            operador.get("id_telefonia"),
            operador.get("matricula"),
        ):
            text = str(value or "").strip()
            if text:
                by_id.setdefault(text, operador)
        name_key = _normalize_identity_text(operador.get("nome"))
        if name_key:
            by_name.setdefault(name_key, operador)
    return by_id, by_name


def _resolve_operador_interacao(
    interacao: dict,
    by_id: dict[str, dict],
    by_name: dict[str, dict],
) -> dict:
    for value in (
        interacao.get("agentId"),
        interacao.get("agentid"),
        interacao.get("workNo"),
        interacao.get("operatorId"),
        interacao.get("operator_id"),
    ):
        text = str(value or "").strip()
        if text and text in by_id:
            return by_id[text]

    for value in (
        interacao.get("operatorName"),
        interacao.get("countName"),
        interacao.get("agentName"),
    ):
        name_key = _normalize_identity_text(value)
        if name_key and name_key in by_name:
            return by_name[name_key]

    operator_name = (
        interacao.get("operatorName")
        or interacao.get("countName")
        or interacao.get("agentName")
        or "Nao Identificado"
    )
    operator_id = (
        interacao.get("workNo")
        or interacao.get("agentId")
        or interacao.get("agentid")
        or ""
    )
    return {
        "nome": str(operator_name or "Nao Identificado").strip() or "Nao Identificado",
        "id_huawei": str(operator_id or "").strip(),
        "id_telefonia": str(operator_id or "").strip(),
        "setor": "",
        "matricula": "",
    }


def _manifest_row_to_interacao(row: dict[str, str]) -> dict:
    begin_ms = _coerce_huawei_time_ms(row.get("beginTime"))
    end_ms = _coerce_huawei_time_ms(row.get("endTime"))
    duration = _coerce_int(
        row.get("calllDuration")
        or row.get("callDuration")
        or row.get("duration"),
        0,
    )
    if duration <= 0 and begin_ms is not None and end_ms is not None and end_ms >= begin_ms:
        duration = int((end_ms - begin_ms) / 1000)

    return {
        "callId": str(row.get("callId") or row.get("recordId") or "").strip(),
        "recordId": str(row.get("recordId") or "").strip(),
        "contactId": str(row.get("contactId") or "").strip(),
        "callSerialno": str(row.get("callSerialno") or "").strip(),
        "callerNo": str(row.get("caller") or "").strip(),
        "calleeNo": str(row.get("called") or "").strip(),
        "beginTime": begin_ms if begin_ms is not None else row.get("beginTime"),
        "endTime": end_ms if end_ms is not None else row.get("endTime"),
        "duration": duration,
        "duracao": duration,
        "callReason": str(row.get("talkReason") or row.get("talkRemark") or "").strip(),
        "workNo": str(row.get("workNo") or "").strip(),
        "operatorName": str(row.get("countName") or "").strip(),
        "mediaTypeId": str(row.get("mediaTypeId") or "").strip(),
        "source": "obs_contact_record",
    }


def _merge_interacoes(*collections: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    sem_id: list[dict] = []
    for collection in collections:
        for interacao in collection:
            call_id = _resolve_call_key(interacao)
            if not call_id:
                sem_id.append(interacao)
                continue
            current = merged.setdefault(call_id, {})
            sources = set(str(current.get("source") or "").split("+")) if current.get("source") else set()
            if interacao.get("source"):
                sources.add(str(interacao["source"]))
            for key, value in interacao.items():
                if value in (None, ""):
                    continue
                if not current.get(key):
                    current[key] = value
            if sources:
                current["source"] = "+".join(sorted(s for s in sources if s))
    return list(merged.values()) + sem_id


async def _buscar_chamadas_globais(
    client: HuaweiAICCClient,
    begin_ms: int,
    end_ms: int,
    *,
    limit_per_page: int = 100,
    max_rows: int = 500,
) -> list[dict]:
    # Kept for backward-compatible internal callers; querycalls has no
    # supported limit/offset pagination, so the collection window is split by
    # time instead.
    _ = (limit_per_page, max_rows)
    chamadas_por_id: dict[str, dict] = {}
    chamadas_sem_id: list[dict] = []

    for window_begin_ms, window_end_ms in _query_time_windows(begin_ms, end_ms):
        for direction in ("INBOUND", "OUTBOUND"):
            chamadas = await client.buscar_historico_chamadas(
                window_begin_ms,
                window_end_ms,
                call_direction=direction,
            )
            if not chamadas:
                continue
            for chamada in chamadas:
                chamada = dict(chamada)
                chamada.setdefault("isCallIn", "true" if direction == "INBOUND" else "false")
                chamada["source"] = "vdn"
                call_key = _resolve_call_key(chamada)
                if not call_key:
                    chamadas_sem_id.append(chamada)
                    continue
                chamadas_por_id.setdefault(call_key, chamada)

    return list(chamadas_por_id.values()) + chamadas_sem_id


async def _buscar_chamadas_obs_manifest(
    obs_client: Optional[HuaweiOBSClient],
    begin_ms: int,
    end_ms: int,
) -> list[dict]:
    if obs_client is None:
        return []

    interacoes: list[dict] = []
    for date_str in _window_date_strings(begin_ms, end_ms):
        for row in await obs_client.listar_contact_record_rows(date_str):
            interacao = _manifest_row_to_interacao(row)
            begin_time = _coerce_huawei_time_ms(interacao.get("beginTime"))
            if begin_time is not None and (begin_time < begin_ms or begin_time > end_ms):
                continue
            interacoes.append(interacao)
    return interacoes


_PROCESS_DELTA_INT_KEYS = (
    "tentativas_download",
    "ignoradas_receptiva_setor_risco",
    "sem_duracao_consideradas",
    "obs_primary_tentativas",
    "obs_primary_sem_record_id_tentativas",
    "obs_primary_hits",
    "obs_primary_misses",
    "obs_primary_pulado_sem_record_id",
    "fs_fallback_tentativas",
    "fs_fallback_ids_tentados",
    "fs_fallback_hits",
    "fs_fallback_misses",
    "url_fallback_tentativas",
    "url_fallback_ids_tentados",
    "url_fallback_hits",
    "url_fallback_misses",
    "baixadas",
    "enfileiradas",
    "duplicadas",
)


def _empty_process_delta() -> Dict[str, Any]:
    delta: Dict[str, Any] = {key: 0 for key in _PROCESS_DELTA_INT_KEYS}
    delta["erros"] = []
    return delta


async def _processar_candidato(
    interacao: dict,
    *,
    client: HuaweiAICCClient,
    obs_client: Optional[HuaweiOBSClient],
    operator_by_id: dict,
    operator_by_name: dict,
    should_cancel: Optional[Callable[[], bool]],
) -> Dict[str, Any]:
    """Faz o download + enfileiramento de uma unica chamada e devolve um delta
    de contadores. Pensado para rodar em paralelo via asyncio.gather; nao toca
    no dict global de contadores para evitar race conditions cooperativas.
    """
    delta = _empty_process_delta()
    if _cancel_requested(should_cancel):
        return delta

    call_id = _resolve_call_key(interacao)
    if not call_id:
        return delta

    operador_resolvido = _resolve_operador_interacao(
        interacao,
        operator_by_id,
        operator_by_name,
    )
    agent_id = operador_resolvido.get("id_huawei") or interacao.get("workNo") or ""
    nome_op = operador_resolvido.get("nome", "Nao Identificado")

    if _should_skip_receptive_risk_call(interacao, operador_resolvido):
        delta["ignoradas_receptiva_setor_risco"] += 1
        return delta

    delta["tentativas_download"] += 1

    try:
        audio_bytes: Optional[bytes] = None

        record_id = str(interacao.get("recordId") or "").strip()
        obs_prefixes = _obs_prefix_candidates(interacao, agent_id)
        obs_match_ids = _obs_match_ids(interacao, call_id)
        download_ids = _download_id_candidates(interacao, call_id)

        # 1. OBS direto (primario) — em producao tem sido o metodo mais confiavel.
        # 1. OBS direto (primario) — em producao tem sido o metodo mais confiavel.
        # So pulamos se tivermos certeza (via manifesto) que nao ha recordId.
        # Se veio via VDN, tentamos mesmo sem recordId pois o API pode omiti-lo.
        is_from_manifest = "obs_contact_record" in str(interacao.get("source") or "")
        should_try_obs = (obs_client is not None and obs_match_ids) and (record_id or not is_from_manifest)

        if should_try_obs:
            if not record_id:
                delta["obs_primary_sem_record_id_tentativas"] += 1

            delta["obs_primary_tentativas"] += 1
            audio_bytes = await obs_client.baixar_voice_por_callid(
                call_id=call_id,
                prefixes=obs_prefixes,
                begin_time=interacao.get("beginTime"),
                end_time=interacao.get("endTime"),
                extra_match_ids=obs_match_ids,
            )
            if audio_bytes:
                delta["obs_primary_hits"] += 1
                logger.info("Sync Huawei: callId %s baixado via OBS direto (primario)", call_id)
            else:
                delta["obs_primary_misses"] += 1
        elif obs_client is not None and not record_id and is_from_manifest:

            delta["obs_primary_pulado_sem_record_id"] += 1

        # 2. FS (fallback 1).
        if not audio_bytes:
            delta["fs_fallback_tentativas"] += 1
            for download_id in download_ids:
                delta["fs_fallback_ids_tentados"] += 1
                audio_bytes = await client.baixar_gravacao_por_callid(download_id)
                if audio_bytes:
                    break
            if audio_bytes:
                delta["fs_fallback_hits"] += 1
                logger.info("Sync Huawei: callId %s baixado via FS (fallback)", call_id)
            else:
                delta["fs_fallback_misses"] += 1

        # 3. URL OBS pre-assinada via FS (fallback 2).
        if not audio_bytes:
            delta["url_fallback_tentativas"] += 1
            for download_id in download_ids:
                delta["url_fallback_ids_tentados"] += 1
                obs_url = await client.obter_url_audio_obs(
                    download_id,
                    interacao.get("beginTime"),
                    interacao.get("endTime"),
                )
                if obs_url:
                    audio_bytes = await client.baixar_audio_ram(obs_url)
                    if audio_bytes:
                        break
            if audio_bytes:
                delta["url_fallback_hits"] += 1
                logger.info("Sync Huawei: callId %s baixado via URL pre-assinada (fallback)", call_id)
            else:
                delta["url_fallback_misses"] += 1

        if not audio_bytes:
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                status='failed',
                failure_reason='audio_not_found'
            )
            return delta

        if _cancel_requested(should_cancel):
            return delta

        filename = _make_filename(nome_op, call_id, "wav")
        resultado = await _enfileirar_audio(
            audio_bytes,
            filename,
            operador_resolvido,
            extra_metadata={
                "huawei_call_id": call_id,
                "huawei_begin_time": interacao.get("beginTime"),
                "huawei_end_time": interacao.get("endTime"),
                "huawei_duration": interacao.get("duration") or interacao.get("duracao"),
                "huawei_caller_no": interacao.get("callerNo") or interacao.get("caller_no"),
                "huawei_callee_no": interacao.get("calleeNo") or interacao.get("callee_no"),
                "huawei_record_id": interacao.get("recordId"),
                "huawei_work_no": interacao.get("workNo"),
                "huawei_operator_name": interacao.get("operatorName"),
                "huawei_source": interacao.get("source"),
                "huawei_obs_prefixes": _obs_prefix_candidates(interacao, agent_id),
                "huawei_obs_match_ids": _obs_match_ids(interacao, call_id),
                "huawei_download_id_candidates": download_ids,
            },
        )

        delta["baixadas"] += 1
        if resultado.get("status") == "queued":
            delta["enfileiradas"] += 1
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                media_url=resultado.get("filename"),
            )
        elif resultado.get("status") == "duplicate":
            delta["duplicadas"] += 1
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                media_url=resultado.get("filename"),
            )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao processar interacao %s do operador %s", call_id, nome_op)
        delta["erros"].append(f"Op {nome_op} Call {call_id}: {str(exc)}")
        try:
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                status='failed',
                failure_reason=f'exception: {str(exc)}'
            )
        except Exception:
            logger.exception("Falha tambem ao registrar erro no huawei_sync_logs")

    return delta


def _download_candidate_sort_key(interacao: dict) -> tuple[int, int, int]:
    # Chamadas com recordId preenchido tendem a resolver mais rapido no OBS/FS.
    # As sem recordId ainda sao tentadas, porque a VDN pode omitir esse campo
    # mesmo quando o Contact_Record ou o objeto Voice existe.
    record_id = str(interacao.get("recordId") or "").strip()
    return (
        1 if record_id else 0,
        get_call_duration_seconds(interacao),
        _coerce_huawei_time_ms(interacao.get("beginTime")) or 0,
    )


class _HuaweiSyncExecutionLock:
    def __init__(self) -> None:
        self._conn = None
        self.acquired = False

    def acquire(self) -> bool:
        import database
        self._conn = database.get_connection()
        try:
            cursor = self._conn.cursor()
            
            # Limpa locks travados ha mais de 30 mins
            cursor.execute("""
                UPDATE configuracoes 
                SET valor = 'false' 
                WHERE chave = 'sync_lock' 
                AND valor = 'true' 
                AND atualizado_em::timestamp < NOW() - INTERVAL '30 minutes'
            """)
            
            # Tenta adquirir
            cursor.execute("""
                INSERT INTO configuracoes (chave, valor, atualizado_em) 
                VALUES ('sync_lock', 'true', NOW()::text)
                ON CONFLICT (chave) DO UPDATE 
                SET valor = 'true', atualizado_em = NOW()::text
                WHERE configuracoes.valor = 'false' OR configuracoes.valor IS NULL
                RETURNING valor
            """)
            row = cursor.fetchone()
            self._conn.commit()
            
            if row:
                self.acquired = True
                return True
            return False
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Falha ao adquirir table lock do sync Huawei: {exc}")
            if self._conn:
                self._conn.rollback()
            return False

    def release(self) -> None:
        if self._conn is None:
            return
        try:
            if self.acquired:
                cursor = self._conn.cursor()
                cursor.execute(
                    "UPDATE configuracoes SET valor = 'false', atualizado_em = NOW() WHERE chave = 'sync_lock'"
                )
                self._conn.commit()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(f"Falha ao liberar table lock do sync Huawei: {exc}")
        finally:
            self.acquired = False
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


async def _buscar_chamadas_por_regra(
    client: HuaweiAICCClient,
    begin_ms: int,
    end_ms: int,
    operador: dict,
    regra: dict,
) -> list[dict]:
    """Busca chamadas respeitando a semântica de `call_direction=None => qualquer`.

    A API da Huawei exige `isCallIn`, então quando a regra não fixa direção
    consultamos ambos os sentidos e deduplicamos por `callId`.
    """
    raw_direction = str(regra.get("call_direction") or "").strip().upper()
    directions = [raw_direction] if raw_direction in {"INBOUND", "OUTBOUND"} else ["INBOUND", "OUTBOUND"]

    chamadas_por_id: dict[str, dict] = {}
    chamadas_sem_id: list[dict] = []

    for direction in directions:
        chamadas = await client.buscar_historico_chamadas(
            begin_ms,
            end_ms,
            call_direction=direction,
        )
        for chamada in chamadas:
            call_key = _resolve_call_key(chamada)
            if not call_key:
                chamadas_sem_id.append(chamada)
                continue
            chamadas_por_id.setdefault(call_key, chamada)

    return list(chamadas_por_id.values()) + chamadas_sem_id


async def _classificar_audio_huawei(
    audio_bytes: bytes,
    filename: str,
    operador: dict,
) -> ClassificationResult:
    """Classificacao real (Whisper + GPT) reutilizando o pipeline do Triagem standalone.

    Espelha _classificar_pdf_huawei mas para audio: transcreve via Azure Speech,
    chama classify_with_gpt e aplica os mesmos guardrails do classify_audio.
    """
    mime_type = get_mime_type(filename)
    try:
        transcription = await transcribe_for_classification(audio_bytes, mime_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao transcrever audio Huawei %s", filename)
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id=operador.get("setor") or "desconhecido",
                sector_label=operador.get("setor") or "Não Identificado",
                alert_id="erro",
                alert_label=f"Falha na transcricao ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )

    if not transcription or len(transcription.strip()) < 10:
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id=operador.get("setor") or "desconhecido",
                sector_label=operador.get("setor") or "Não Identificado",
                alert_id="desconhecido",
                alert_label="Áudio curto/sem fala",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error="Short transcription",
            )
        )

    operator_name = str(operador.get("nome") or "").strip()
    operator_sector = str(operador.get("setor") or "").strip().lower()
    try:
        classification = await classify_with_gpt(transcription, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao classificar audio Huawei %s", filename)
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id=operator_sector or "desconhecido",
                sector_label=operator_sector or "Não Identificado",
                alert_id="erro",
                alert_label=f"Falha na IA ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operator_name or None,
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )

    classification["_filename"] = filename
    classification = align_classification_with_catalog(classification)
    classification.pop("_filename", None)
    classification = enforce_temperature_guardrail(classification, transcription, filename)
    classification = enforce_alert_hierarchy_guardrail(classification, transcription, filename)
    classification = enforce_parada_desvio_guardrail(classification, transcription, filename)

    if operator_sector:
        classification = enforce_operator_and_direction_guardrails(
            classification,
            operator_name or None,
            db_sector=operator_sector,
        )
        catalog = load_audit_criteria_catalog()
        current_sector = classification.get("sector_id")
        if current_sector in {"desconhecido", "erro", "", None} and operator_sector in catalog:
            classification["sector_id"] = operator_sector
            classification["sector_label"] = str(catalog[operator_sector]["label"])

    try:
        confidence = float(classification.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    needs_review = bool(classification.get("needs_review")) or confidence < 0.7

    return finalize_classification_result(
        ClassificationResult(
            filename=filename,
            sector_id=classification.get("sector_id", "desconhecido"),
            sector_label=classification.get("sector_label", "Não Identificado"),
            alert_id=classification.get("alert_id", "desconhecido"),
            alert_label=classification.get("alert_label", "Não Identificado"),
            confidence=confidence,
            operator_name=classification.get("operator_name") or operator_name or None,
            direction=classification.get("direction"),
            id_huawei=operador.get("id_huawei"),
            direction_mismatch=classification.get("_direction_mismatch", False),
            needs_review=needs_review,
            review_reasons=list(classification.get("review_reasons") or []),
            review_priority=classification.get("review_priority", "low"),
        )
    )


async def _enfileirar_audio(
    audio_bytes: bytes,
    filename: str,
    operador: dict,
    extra_metadata: Optional[dict] = None,
) -> Dict[str, Any]:
    classification = ClassificationResult(
        filename=filename,
        sector_id=operador.get("setor") or "desconhecido",
        sector_label=operador.get("setor") or "Não Identificado",
        alert_id="desconhecido",
        alert_label="Aguardando classificação",
        confidence=0.0,
        operator_name=operador.get("nome"),
        error=None,
        needs_review=False,
        review_reasons=[],
        id_huawei=operador.get("id_huawei"),
        matricula=operador.get("matricula"),
    )

    audio_metadata = dict(extra_metadata or {})
    audio_metadata.setdefault("classification_status", "pending")

    return _enfileirar_classificado(
        audio_bytes,
        filename,
        operador,
        classification,
        source_type=SOURCE_TYPE_AUDIO,
        extra_metadata=audio_metadata,
    )


async def _classificar_pdf_huawei(
    pdf_bytes: bytes,
    filename: str,
    operador: dict,
) -> ClassificationResult:
    raw_text = extract_text_from_pdf(pdf_bytes).strip()
    if len(raw_text) < 10:
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="desconhecido",
                sector_label="Não Identificado",
                alert_id="desconhecido",
                alert_label="PDF sem texto suficiente",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error="Short PDF text",
            )
        )

    operator_name = str(operador.get("nome") or "").strip()
    operator_sector = str(operador.get("setor") or "").strip().lower()
    context = (
        f"OPERADOR CADASTRADO: {operator_name or 'N/A'}\n"
        f"SETOR CADASTRADO: {operator_sector or 'N/A'}\n\n"
        f"{raw_text}"
    )
    try:
        classification = await classify_with_gpt(context, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao classificar PDF Huawei %s", filename)
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label=f"Falha na IA ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operator_name or None,
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )
    classification["_filename"] = filename
    classification = align_classification_with_catalog(classification)
    classification.pop("_filename", None)

    if operator_sector:
        classification = enforce_operator_and_direction_guardrails(
            classification,
            operator_name or None,
            db_sector=operator_sector,
        )
        catalog = load_audit_criteria_catalog()
        current_sector = classification.get("sector_id")
        if current_sector in {"desconhecido", "erro", "", None} and operator_sector in catalog:
            classification["sector_id"] = operator_sector
            classification["sector_label"] = str(catalog[operator_sector]["label"])

    try:
        confidence = float(classification.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    return finalize_classification_result(
        ClassificationResult(
            filename=filename,
            sector_id=classification.get("sector_id", "desconhecido"),
            sector_label=classification.get("sector_label", "Não Identificado"),
            alert_id=classification.get("alert_id", "desconhecido"),
            alert_label=classification.get("alert_label", "Não Identificado"),
            confidence=confidence,
            operator_name=classification.get("operator_name") or operator_name or None,
            direction=classification.get("direction"),
            id_huawei=operador.get("id_huawei"),
            direction_mismatch=classification.get("_direction_mismatch", False),
        )
    )


async def _enfileirar_pdf(
    pdf_bytes: bytes,
    filename: str,
    operador: dict,
) -> Dict[str, Any]:
    classification = await _classificar_pdf_huawei(pdf_bytes, filename, operador)
    return _enfileirar_classificado(
        pdf_bytes,
        filename,
        operador,
        classification,
        source_type=SOURCE_TYPE_PDF,
    )


def _enfileirar_classificado(
    media_bytes: bytes,
    filename: str,
    operador: dict,
    classification: ClassificationResult,
    *,
    source_type: str,
    extra_metadata: Optional[dict] = None,
) -> Dict[str, Any]:
    input_hash = hashlib.sha256(media_bytes).hexdigest()

    existing = database.obter_fila_revisao_classificacao_por_hash(input_hash)
    if existing:
        return {"status": "duplicate", "input_hash": input_hash, "filename": filename}

    media_path = store_classified_audio(input_hash, filename, media_bytes)
    detected_operator_name = (
        getattr(classification, "operator_name", None)
        or operador.get("nome")
    )
    detected_id_huawei = getattr(classification, "id_huawei", None) or operador.get("id_huawei")
    detected_matricula = getattr(classification, "matricula", None)
    detected_operator_id = detected_id_huawei or detected_matricula or operador.get("id_huawei")
    metadata = {
        "filename_upload": filename,
        "classified_audio_path": media_path,
        "classified_file_path": media_path,
        "source_type": source_type,
        "origem": "huawei_sync",
        "operator_id": detected_operator_id,
        "id_huawei": detected_id_huawei,
        "matricula": detected_matricula,
        "operator_name": detected_operator_name,
    }
    if extra_metadata:
        metadata.update({k: v for k, v in extra_metadata.items() if v not in (None, "")})

    database.sincronizar_fila_revisao_classificacao(
        input_hash=input_hash,
        nome_arquivo=filename,
        setor_previsto=classification.sector_id,
        alerta_previsto=classification.alert_id,
        confianca=getattr(classification, "confidence", 0.0),
        operador_previsto=detected_operator_name,
        erro=getattr(classification, "error", None),
        precisa_revisao=getattr(classification, "needs_review", False),
        prioridade=getattr(classification, "review_priority", "low"),
        motivos_revisao=getattr(classification, "review_reasons", []),
        metadata=metadata,
    )
    return {"status": "queued", "input_hash": input_hash, "filename": filename}


_MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000  # 30 dias


async def _classificar_pendentes_async(
    *,
    concurrency: int,
    operator_by_id: Dict[str, dict],
    operator_by_name: Dict[str, dict],
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Fase 2 do sync: classifica em paralelo todos os itens Huawei com
    metadata.classification_status='pending'. Atualiza setor/alerta/operador
    via corrigir_classificacao_fila_revisao (que ja dispara o RAG/RLHF) e
    marca classification_status='done' ou 'error' no metadata.
    """
    try:
        fila = database.listar_fila_revisao_classificacao(
            limit=500,
            status="all",
            origem="huawei_sync",
        )
    except Exception:
        logger.exception("Fase 2 (classificacao): falha ao listar fila de revisao")
        return {"classificadas": 0, "erros": 0, "pendentes_restantes": 0}

    pendentes: List[dict] = []
    for item in fila or []:
        meta = item.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if str(meta.get("classification_status") or "").strip().lower() != "pending":
            continue
        pendentes.append(item)

    if not pendentes:
        return {"classificadas": 0, "erros": 0, "pendentes_restantes": 0}

    logger.info("Fase 2 sync Huawei: %d itens para classificar (concurrency=%d).", len(pendentes), concurrency)
    semaphore = asyncio.Semaphore(max(1, concurrency))
    classificadas = 0
    erros = 0

    async def _processar(item: dict) -> str:
        nonlocal classificadas, erros
        async with semaphore:
            if _cancel_requested(should_cancel):
                return "cancelled"
            input_hash = str(item.get("input_hash") or "").strip()
            metadata = item.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            media_path = str(metadata.get("classified_audio_path") or metadata.get("classified_file_path") or "").strip()
            filename = str(item.get("nome_arquivo") or "gravacao.wav")
            if not input_hash or not media_path:
                erros += 1
                return "missing_path"
            try:
                audio_bytes = load_classified_audio(media_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fase 2: falha ao ler audio %s (%s)", media_path, exc)
                _marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                erros += 1
                return "io_error"
            if not audio_bytes:
                _marcar_classificacao_status(input_hash, status="error", erro="audio_indisponivel")
                erros += 1
                return "no_bytes"

            operator_id = str(metadata.get("operator_id") or metadata.get("id_huawei") or "").strip()
            operator_name = str(metadata.get("operator_name") or item.get("operador_previsto") or "").strip()
            operador = (
                operator_by_id.get(operator_id.lower()) if operator_id else None
            ) or (operator_by_name.get(operator_name.lower()) if operator_name else None) or {
                "nome": operator_name,
                "id_huawei": operator_id,
                "setor": item.get("setor_previsto") or "",
            }

            try:
                result = await _classificar_audio_huawei(audio_bytes, filename, operador)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Fase 2: erro ao classificar %s", filename)
                _marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                erros += 1
                return "classify_error"

            sector_id = getattr(result, "sector_id", None) or "desconhecido"
            alert_id = getattr(result, "alert_id", None) or "desconhecido"
            confidence = getattr(result, "confidence", 0.0) or 0.0
            try:
                _aplicar_auto_classificacao(
                    input_hash,
                    sector_id=sector_id,
                    alert_id=alert_id,
                    operator_name=getattr(result, "operator_name", None) or operator_name or None,
                    confianca=confidence,
                    needs_review=bool(getattr(result, "needs_review", False)),
                    review_reasons=list(getattr(result, "review_reasons", []) or []),
                    review_priority=str(getattr(result, "review_priority", "low") or "low"),
                    erro=getattr(result, "error", None),
                )
                classificadas += 1
                return "ok"
            except Exception as exc:  # noqa: BLE001
                logger.exception("Fase 2: falha ao persistir classificacao de %s", filename)
                _marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                erros += 1
                return "persist_error"

    await asyncio.gather(*[_processar(item) for item in pendentes])

    pendentes_restantes = max(0, len(pendentes) - classificadas - erros)
    return {
        "classificadas": classificadas,
        "erros": erros,
        "pendentes_restantes": pendentes_restantes,
    }


def _marcar_classificacao_status(
    input_hash: str,
    *,
    status: str,
    erro: Optional[str] = None,
) -> None:
    """Atualiza apenas metadata.classification_status mantendo status da fila."""
    metadata_merge: Dict[str, Any] = {"classification_status": status}
    if status == "error" and erro:
        metadata_merge["classification_error"] = erro[:500]
    if status == "done":
        metadata_merge["classification_error"] = None
    try:
        from database import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT metadata_json FROM fila_revisao_classificacao WHERE input_hash = %s",
                (input_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return
            try:
                meta_atual = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                if not isinstance(meta_atual, dict):
                    meta_atual = {}
            except Exception:  # noqa: BLE001
                meta_atual = {}
            meta_atual.update(metadata_merge)
            cursor.execute(
                "UPDATE fila_revisao_classificacao SET metadata_json = %s, atualizado_em = %s WHERE input_hash = %s",
                (
                    json.dumps(meta_atual, ensure_ascii=False),
                    datetime.now().isoformat(),
                    input_hash,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao registrar classification_status=%s para %s", status, input_hash)


def _aplicar_auto_classificacao(
    input_hash: str,
    *,
    sector_id: str,
    alert_id: str,
    operator_name: Optional[str],
    confianca: float,
    needs_review: bool,
    review_reasons: List[str],
    review_priority: str,
    erro: Optional[str],
) -> None:
    """Persiste o resultado de uma classificacao automatica (Whisper+GPT) sem
    promover o status para 'reviewed' (que e reservado para correcao humana).

    Mantem o status atual (auto_resolved / pending) salvo se a classificacao
    real exigir revisao manual e o item estava em auto_resolved — nesse caso
    rebaixa para pending para o auditor decidir.
    """
    from database import get_connection

    sector_norm = (sector_id or "").strip().lower() or "desconhecido"
    motivos = [str(m).strip() for m in (review_reasons or []) if str(m).strip()]
    prioridade = (review_priority or "low").strip().lower() or "low"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, motivos_json, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return

        try:
            meta_atual = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
            if not isinstance(meta_atual, dict):
                meta_atual = {}
        except Exception:  # noqa: BLE001
            meta_atual = {}
        meta_atual["classification_status"] = "done"
        meta_atual["classification_error"] = None
        meta_atual["classified_by"] = "huawei_auto_classifier"

        try:
            motivos_existentes = json.loads(row["motivos_json"]) if row["motivos_json"] else []
            if not isinstance(motivos_existentes, list):
                motivos_existentes = []
        except Exception:  # noqa: BLE001
            motivos_existentes = []
        motivos_atualizados = list(dict.fromkeys([*motivos_existentes, *motivos]))

        status_atual = (row["status"] or "").strip().lower()
        # Auto-classificacao com baixa confianca rebaixa para pending; alta confianca
        # permanece em auto_resolved (worker captura via filtro virtual READY_FOR_AUDIT).
        if needs_review:
            novo_status = "pending"
        elif status_atual in {"auto_resolved", "pending"}:
            novo_status = "auto_resolved"
        else:
            # Se ja foi humano-revisado/auditado/cota, nao mexer.
            novo_status = status_atual or "auto_resolved"

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET setor_previsto = %s,
                alerta_previsto = %s,
                operador_previsto = COALESCE(NULLIF(%s, ''), operador_previsto),
                confianca = %s,
                erro = %s,
                prioridade = %s,
                motivos_json = %s,
                metadata_json = %s,
                status = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                sector_norm,
                alert_id or "desconhecido",
                str(operator_name or "").strip(),
                float(confianca or 0.0),
                erro,
                prioridade,
                json.dumps(motivos_atualizados, ensure_ascii=False),
                json.dumps(meta_atual, ensure_ascii=False),
                novo_status,
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def executar_sync_huawei(
    horas_retroativas: float = 1.0,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    begin_time_ms: Optional[int] = None,
    end_time_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Funcao principal que baixa, tria e enfileira as ligacoes na revisao."""
    sync_lock = _HuaweiSyncExecutionLock()
    if not sync_lock.acquire():
        logger.info("Sync Huawei ignorado porque outra execucao ja esta em andamento.")
        return {
            "status": "skipped",
            "message": "Sync Huawei ja esta em andamento.",
            "baixadas": 0,
            "enfileiradas": 0,
        }

    try:
        if not _ensure_enabled():
            logger.info("ENABLE_HUAWEI_SYNC desativado; retornando stub amigavel.")
            return {
                "status": "disabled",
                "message": "Sincronizacao Huawei desligada. Defina ENABLE_HUAWEI_SYNC=true para executar.",
                "baixadas": 0,
                "enfileiradas": 0,
            }

        cfg = _load_config()
        faltando = _missing_credentials(cfg)
        if faltando:
            return {
                "status": "missing_credentials",
                "message": f"Credenciais ausentes: {', '.join(faltando)}.",
                "baixadas": 0,
                "enfileiradas": 0,
            }

        agora = datetime.now(timezone.utc)
        if begin_time_ms is not None and end_time_ms is not None:
            begin_ms = int(begin_time_ms)
            end_ms = int(end_time_ms)
            if begin_ms >= end_ms:
                return {
                    "status": "error",
                    "message": "Janela invalida: data inicial deve ser anterior a data final.",
                    "baixadas": 0,
                    "enfileiradas": 0,
                }
            if (end_ms - begin_ms) > _MAX_WINDOW_MS:
                return {
                    "status": "error",
                    "message": "Janela invalida: o intervalo nao pode exceder 30 dias.",
                    "baixadas": 0,
                    "enfileiradas": 0,
                }
            horas = max(0.5, float(end_ms - begin_ms) / (3600 * 1000.0))
            logger.info("Sync Huawei usando janela explicita: %s -> %s", begin_ms, end_ms)
        else:
            horas = max(0.5, float(horas_retroativas or 1.0))
            begin_ms = int((agora - timedelta(hours=horas)).timestamp() * 1000)
            end_ms = int(agora.timestamp() * 1000)

        client = HuaweiAICCClient.from_config(cfg)

        # Cliente HTTP compartilhado por todo o ciclo (Keep-Alive + 1 handshake
        # TLS para N listagens/downloads OBS). Fechado no finally do orquestrador.
        obs_http_client: Optional[httpx.AsyncClient] = None

        # Cliente OBS direto (fallback definitivo quando CC-FS devolve 0300012).
        # Cache vive por instancia, ou seja, dura apenas este ciclo de sync.
        obs_client: Optional[HuaweiOBSClient] = None
        if cfg.get("obs_ak") and cfg.get("obs_sk"):
            obs_kwargs: Dict[str, Any] = {
                "ak": cfg["obs_ak"],
                "sk": cfg["obs_sk"],
                "bucket": cfg.get("obs_bucket") or "",
            }
            if cfg.get("obs_endpoint"):
                obs_kwargs["endpoint"] = cfg["obs_endpoint"]
            obs_http_client = httpx.AsyncClient(timeout=_OBS_HTTP_TIMEOUT)
            obs_client = HuaweiOBSClient(http_client=obs_http_client, **obs_kwargs)
            logger.info(
                "Sync Huawei: fallback OBS direto habilitado (bucket=%s).",
                obs_client.bucket,
            )
        else:
            logger.info(
                "Sync Huawei: credenciais OBS ausentes; fallback direto desabilitado.",
            )

        contadores = {
            "status": "ok",
            "modo_coleta": "global_vdn_obs_manifest",
            "operadores_considerados": 0,
            "operadores_sem_regra": 0,
            "operadores_sem_chamadas": 0,
            "chamadas_na_vdn": 0,
            "chamadas_no_manifest_obs": 0,
            "chamadas_descobertas_total": 0,
            "chamadas_validas_pos_filtro": 0,
            "candidatos_download": 0,
            "ignoradas_duracao_minima": 0,
            "sem_duracao_consideradas": 0,
            "ignoradas_receptiva_setor_risco": 0,
            "ignoradas_ja_sincronizadas": 0,
            "ignoradas_tentadas_no_ciclo": 0,
            "tentativas_download": 0,
            "obs_primary_tentativas": 0,
            "obs_primary_sem_record_id_tentativas": 0,
            "obs_primary_hits": 0,
            "obs_primary_misses": 0,
            "obs_primary_pulado_sem_record_id": 0,
            "fs_fallback_tentativas": 0,
            "fs_fallback_ids_tentados": 0,
            "fs_fallback_hits": 0,
            "fs_fallback_misses": 0,
            "url_fallback_tentativas": 0,
            "url_fallback_ids_tentados": 0,
            "url_fallback_hits": 0,
            "url_fallback_misses": 0,
            "baixadas": 0,
            "enfileiradas": 0,
            "duplicadas": 0,
            "erros": [],
        }
        call_ids_tentados_no_ciclo: set[str] = set()
        call_ids_vdn_unicos: set[str] = set()
        call_ids_manifest_unicos: set[str] = set()
        call_ids_descobertos_unicos: set[str] = set()
        call_ids_validos_unicos: set[str] = set()
        call_ids_ja_sincronizados_no_ciclo: set[str] = set()

        # 1. Obter operadores para enriquecer metadata. O download nao deve
        # depender disso, pois a VDN frequentemente nao devolve agentId.
        operadores = database.listar_auditaveis_com_id_huawei()
        contadores["operadores_considerados"] = len(operadores)
        operator_by_id, operator_by_name = _build_operator_indexes(operadores)

        if _cancel_requested(should_cancel):
            contadores.update(
                {
                    "status": "cancelled",
                    "message": "Coleta de ligacoes cancelada antes da busca.",
                    "cancelado": True,
                }
            )
            return contadores

        # 2. Descobrir chamadas globalmente. A Huawei ignora/omite agentId no
        # querycalls, entao a coleta por operador pode retornar zero ou repetir
        # as mesmas linhas. O manifesto OBS entra como fallback independente da
        # VDN e costuma carregar workNo/countName/caller/called/recordId.
        vdn_interacoes = await _buscar_chamadas_globais(client, begin_ms, end_ms)
        obs_manifest_interacoes = await _buscar_chamadas_obs_manifest(obs_client, begin_ms, end_ms)
        for chamada in vdn_interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_vdn_unicos.add(chamada_call_id)
        for chamada in obs_manifest_interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_manifest_unicos.add(chamada_call_id)
        interacoes = _merge_interacoes(vdn_interacoes, obs_manifest_interacoes)
        for chamada in interacoes:
            chamada_call_id = _resolve_call_key(chamada)
            if chamada_call_id:
                call_ids_descobertos_unicos.add(chamada_call_id)

        contadores["chamadas_na_vdn"] = len(call_ids_vdn_unicos)
        contadores["chamadas_no_manifest_obs"] = len(call_ids_manifest_unicos)
        contadores["chamadas_descobertas_total"] = len(call_ids_descobertos_unicos)

        if not interacoes:
            logger.info("Sync Huawei: nenhuma chamada descoberta na VDN nem no manifesto OBS.")
            return contadores

        min_duration_seconds = max(
            0,
            _coerce_int(
                os.getenv("HUAWEI_SYNC_MIN_DURATION_SECONDS"),
                DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS,
            ),
        )
        max_duration_seconds = max(
            0,
            _coerce_int(
                os.getenv("HUAWEI_SYNC_MAX_DURATION_SECONDS"),
                DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS,
            ),
        )
        max_download_attempts = max(
            1,
            _coerce_int(
                os.getenv("HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS"),
                DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT,
            ),
        )
        contadores["min_duracao_padrao_segundos"] = min_duration_seconds
        contadores["max_duracao_padrao_segundos"] = max_duration_seconds
        contadores["limite_tentativas_download"] = max_download_attempts
        contadores["limite_downloads"] = max_download_attempts

        candidatas: list[dict] = []
        for interacao in sorted(interacoes, key=_download_candidate_sort_key, reverse=True):
            if _cancel_requested(should_cancel):
                contadores.update(
                    {
                        "status": "cancelled",
                        "message": "Coleta de ligacoes cancelada antes de selecionar novos downloads.",
                        "cancelado": True,
                    }
                )
                break

            call_id = _resolve_call_key(interacao)
            if not call_id:
                continue

            operador_resolvido = _resolve_operador_interacao(
                interacao,
                operator_by_id,
                operator_by_name,
            )

            # Setores de risco so auditam ligacoes EFETUADAS — descarta receptivas
            # antes mesmo de ocupar slot de download.
            if _should_skip_receptive_risk_call(interacao, operador_resolvido):
                contadores["ignoradas_receptiva_setor_risco"] += 1
                continue

            setor = str(operador_resolvido.get("setor") or "").strip()
            min_sec, max_sec = _get_duration_limits_for_sector(
                setor,
                min_duration_seconds,
                max_duration_seconds,
            )

            duration = get_call_duration_seconds(interacao)
            duration_known = _call_duration_is_known(interacao)
            if duration_known and duration < min_sec:
                contadores.setdefault("ignoradas_duracao_minima", 0)
                contadores["ignoradas_duracao_minima"] += 1
                continue
            if duration_known and max_sec > 0 and duration > max_sec:
                contadores.setdefault("ignoradas_duracao_maxima", 0)
                contadores["ignoradas_duracao_maxima"] += 1
                continue
            if not duration_known:
                contadores["sem_duracao_consideradas"] += 1

            call_ids_validos_unicos.add(call_id)
            if len(candidatas) >= max_download_attempts:
                continue
            if call_id in call_ids_tentados_no_ciclo:
                contadores["ignoradas_tentadas_no_ciclo"] += 1
                continue
            if database.huawei_sync_log_exists(call_id):
                if call_id not in call_ids_ja_sincronizados_no_ciclo:
                    call_ids_ja_sincronizados_no_ciclo.add(call_id)
                    contadores["duplicadas"] += 1
                    contadores["ignoradas_ja_sincronizadas"] += 1
                continue
            candidatas.append(interacao)
            call_ids_tentados_no_ciclo.add(call_id)

        contadores["chamadas_validas_pos_filtro"] = len(call_ids_validos_unicos)
        contadores["candidatos_download"] = len(candidatas)

        if contadores.get("status") == "cancelled":
            return contadores

        concurrency = max(
            1,
            _coerce_int(
                os.getenv("HUAWEI_SYNC_DOWNLOAD_CONCURRENCY"),
                DEFAULT_HUAWEI_SYNC_DOWNLOAD_CONCURRENCY,
            ),
        )
        contadores["concurrency_downloads"] = concurrency
        semaforo = asyncio.Semaphore(concurrency)

        async def _wrap(interacao: dict) -> Dict[str, Any]:
            async with semaforo:
                return await _processar_candidato(
                    interacao,
                    client=client,
                    obs_client=obs_client,
                    operator_by_id=operator_by_id,
                    operator_by_name=operator_by_name,
                    should_cancel=should_cancel,
                )

        if candidatas:
            logger.info(
                "Sync Huawei: %d candidatos sendo processados em paralelo (concurrency=%d).",
                len(candidatas),
                concurrency,
            )
            resultados = await asyncio.gather(*[_wrap(i) for i in candidatas])
            for delta in resultados:
                if not isinstance(delta, dict):
                    continue
                for key in _PROCESS_DELTA_INT_KEYS:
                    contadores[key] = contadores.get(key, 0) + int(delta.get(key, 0) or 0)
                erros = delta.get("erros") or []
                if erros:
                    contadores["erros"].extend(erros)

        if _cancel_requested(should_cancel) and contadores.get("status") != "cancelled":
            contadores.update(
                {
                    "status": "cancelled",
                    "message": "Coleta de ligacoes cancelada pelo usuario.",
                    "cancelado": True,
                }
            )

        # Fase 2 — Classificacao real (Whisper + GPT) dos itens recem enfileirados.
        # Roda dentro do mesmo task asyncio para nao perder execucao no Cloud Run.
        # Opcionalmente desativada via HUAWEI_SYNC_SKIP_CLASSIFY=true.
        if (
            contadores.get("status") != "cancelled"
            and (os.getenv("HUAWEI_SYNC_SKIP_CLASSIFY", "") or "").strip().lower() != "true"
        ):
            classify_stats = await _classificar_pendentes_async(
                concurrency=_coerce_int(
                    os.getenv("HUAWEI_SYNC_CLASSIFY_CONCURRENCY"),
                    DEFAULT_HUAWEI_SYNC_CLASSIFY_CONCURRENCY,
                ),
                operator_by_id=operator_by_id,
                operator_by_name=operator_by_name,
                should_cancel=should_cancel,
            )
            contadores["classificadas"] = classify_stats.get("classificadas", 0)
            contadores["erros_classificacao"] = classify_stats.get("erros", 0)
            contadores["pendentes_classificacao"] = classify_stats.get("pendentes_restantes", 0)

        logger.info(
            "Sync Huawei concluido: %(baixadas)d baixadas, %(enfileiradas)d enfileiradas, %(duplicadas)d duplicadas",
            contadores,
        )
        return contadores

    except Exception as exc:
        logger.exception("Erro critico na sync Huawei: %s", exc)
        return {
            "status": "error",
            "message": str(exc),
            "baixadas": 0,
            "enfileiradas": 0,
        }
    finally:
        sync_lock.release()
        if 'obs_http_client' in locals() and obs_http_client is not None:
            try:
                await obs_http_client.aclose()
            except Exception:
                logger.exception("Falha ao fechar httpx.AsyncClient compartilhado do OBS.")

