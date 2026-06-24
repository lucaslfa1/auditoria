from __future__ import annotations
from .huawei.telemetry import _notify_progress, _increment_skip_counter, _empty_process_delta, _is_direction_skip
from .huawei.download_candidates import _normalize_identity_text
from .huawei.download_candidates import _slug_filename_part, _call_duration_is_known, _clean_huawei_operator_id, _obs_prefix_candidates, _obs_match_ids, _download_id_candidates, _clean_obs_prefix, _download_candidate_sort_key, _make_filename, _resolve_call_key
# Resolução de operador (matching/índices/verdade do cadastro) movida para
# core/huawei/operator_resolution.py. Reexport mantém compat (callers internos +
# sync_triagem/enqueue/classification/audit_actions/automation_engine + testes).
from .huawei.operator_resolution import (  # noqa: F401
    _normalize_setor_regra,
    _operator_sector_id,
    _build_operator_indexes,
    _resolve_huawei_operator_id,
    _resolve_operador_interacao,
    _operator_field,
    _operator_truth_snapshot,
    _inject_operator_truth,
)
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


import asyncio
import hashlib
import json
import logging
import os
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo
from collections import defaultdict

import httpx

import db.database as database
from repositories import audits
from repositories import operators
from core.automation import load_classified_audio, store_classified_audio
from core.classification import (
    ClassificationResult,
    align_classification_with_catalog,
    classify_with_gpt,
    enforce_alert_hierarchy_guardrail,
    enforce_context_not_non_auditable_guardrail,
    enforce_operator_and_direction_guardrails,
    enforce_parada_desvio_guardrail,
    enforce_temperature_guardrail,
    finalize_classification_result,
    get_mime_type,
    load_audit_criteria_catalog,
    transcribe_for_classification,
)
from core.automation_rules import AUTOMATION_RULES, get_call_duration_seconds, get_call_reason_text, filtrar_chamadas
from core.audit import extract_text_from_pdf
from core.huawei_client import OAUTH_DIRECT_MODES, HuaweiAICCClient
from core.huawei_direction import (
    NON_TELEFONIA_SECTORS,
    OUTBOUND_ONLY_RISK_SECTORS,
    coerce_huawei_is_call_in,
    format_huawei_is_call_in,
    normalize_huawei_sector,
    resolve_huawei_is_call_in,
)
from core.huawei_obs_client import HuaweiOBSClient
from core.huawei_discovery import HuaweiDiscoveryService
from core import cost_guard
from core.llm_triage import filtrar_ligacoes_com_llm
from core.automation_disposition import Disposition, execute_discard
from core.automation_guardrails import AutomationGatekeeper
from db.domain_constants import (
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    SOURCE_TYPE_AUDIO,
    SOURCE_TYPE_PDF,
)
from repositories.common import json_loads, normalize_huawei_agent_id

logger = logging.getLogger(__name__)
_HUAWEI_SYNC_LOCK_KEY = 2026042202
# Config/credenciais/tuning de runtime do sync: extraído para
# core/huawei/automation_config.py (v1.3.169); reexportado p/ compat (callers
# internos, sync_classification via hs.<nome>, huawei_d_minus_1 e scripts que
# importam from core.huawei_sync import _load_config).
from core.huawei.automation_config import (  # noqa: E402,F401
    DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT,
    HUAWEI_SYNC_DOWNLOAD_HARD_CEILING,
    DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS,
    DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS,
    DEFAULT_HUAWEI_SYNC_DOWNLOAD_CONCURRENCY,
    DEFAULT_HUAWEI_SYNC_CLASSIFY_CONCURRENCY,
    DEFAULT_HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD,
    _ensure_enabled,
    _load_config,
    _missing_credentials,
    _coerce_int,
    _coerce_float,
    _runtime_int_config,
    _runtime_float_config,
    _effective_download_attempt_limit,
    _get_huawei_auto_audit_confidence_threshold,
    _env_flag,
    _should_run_auto_classification_after_sync,
    _get_duration_limits_for_sector,
)
_AUDIO_DIRECTION_GATE_SECTORS = OUTBOUND_ONLY_RISK_SECTORS
_NON_TELEFONIA_SECTORS = NON_TELEFONIA_SECTORS
_AUTOMATION_CONFIDENCE_REVIEW_REASON = "confianca_insuficiente_automacao"
# Timeout generoso o bastante para download via FS (audios podem ter ate 50MB).
_OBS_HTTP_TIMEOUT = 120.0


# Setores de risco aceitam somente ligacoes ativas (outbound). Ligacoes
# receptivas devem ser descartadas antes do download sempre que a Huawei
# informar a direcao.

def _coerce_huawei_is_call_in(value: Any) -> Optional[bool]:
    return coerce_huawei_is_call_in(value)

def _resolve_huawei_is_call_in(interacao: dict) -> Optional[bool]:
    return resolve_huawei_is_call_in(interacao)


_BAS_POLICE_NUMBERS_CACHE: Optional[set] = None


def _get_bas_police_numbers() -> set:
    """Whitelist de números policiais da BAS (cacheada por execução de sync).

    Lê uma vez de `configuracoes` por ciclo (reset em `executar_sync_huawei`);
    fail-soft para set vazio se a leitura falhar — sem whitelist, oitiva por
    celular continua sendo descartada normalmente.
    """
    global _BAS_POLICE_NUMBERS_CACHE
    if _BAS_POLICE_NUMBERS_CACHE is None:
        try:
            from repositories import configuration
            _BAS_POLICE_NUMBERS_CACHE = configuration.get_bas_police_numbers(database.get_connection)
        except Exception:
            logger.debug("Sync Huawei: falha ao ler whitelist policial da BAS.", exc_info=True)
            _BAS_POLICE_NUMBERS_CACHE = set()
    return _BAS_POLICE_NUMBERS_CACHE


def _should_skip_call(interacao: dict, operador: dict) -> Optional[str]:
    from core.huawei_sync_gatekeeper import SyncDownloadGatekeeper
    gatekeeper = SyncDownloadGatekeeper(AUTOMATION_RULES, police_numbers=_get_bas_police_numbers())
    return gatekeeper.check_eligibility(interacao, operador)

_SKIP_REASON_COUNTERS = {
    "mondelez": "ignoradas_mondelez",
    "operator_not_registered": "ignoradas_operador_huawei_nao_cadastrado",
    "direction_mismatch": "ignoradas_direcao_incompativel",
    "direction_unknown": "ignoradas_direcao_desconhecida",
    "risk_inbound": "ignoradas_receptiva_setor_risco",
    "non_telefonia_sector": "ignoradas_setor_nao_telefonia",
    "receptiva_setor_desconhecido": "ignoradas_receptiva_setor_desconhecido",
    "operator_huawei_not_registered": "ignoradas_operador_huawei_nao_cadastrado",
}
_SKIP_REASON_EXTRA_COUNTERS = {
    "risk_inbound": ("ignoradas_direcao_incompativel",),
    "receptiva_setor_desconhecido": ("ignoradas_direcao_incompativel",),
}



def _resolve_operator_name_from_interacao(interacao: dict, operador: dict) -> Optional[str]:
    # Preferencia: nome que a Huawei reportou na chamada (operatorName da VDN
    # ou countName do manifest OBS). Cai pra nome do colaborador resolvido
    # apenas se for um nome real (nao o placeholder "Nao Identificado").
    for key in ("operatorName", "countName", "agentName"):
        value = str(interacao.get(key) or "").strip()
        if value:
            return value
    nome_op = str(operador.get("nome") or "").strip()
    if nome_op and nome_op.lower() != "nao identificado":
        return nome_op
    return "Não Identificado"

def _resolve_huawei_skill_id_field(interacao: dict) -> Optional[str]:
    for key in ("callSkill", "skillId", "skill_id", "skillid", "skillID"):
        value = interacao.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return None

def _huawei_call_reason_metadata(interacao: dict) -> dict[str, Any]:
    """Preserva a tabulacao nativa da Huawei para triagem/auditoria."""
    metadata: dict[str, Any] = {
        "huawei_call_reason": get_call_reason_text(interacao),
        "huawei_talk_reason": str(interacao.get("talkReason") or "").strip(),
        "huawei_talk_remark": str(interacao.get("talkRemark") or "").strip(),
        "huawei_call_reason_code": str(
            interacao.get("callReasonCode")
            or interacao.get("leaveReason")
            or ""
        ).strip(),
        "huawei_call_skill": str(interacao.get("callSkill") or "").strip(),
    }
    if "native_reason_match" in interacao:
        metadata["native_reason_match"] = interacao.get("native_reason_match")
    if interacao.get("native_reason_targets"):
        metadata["native_reason_targets"] = interacao.get("native_reason_targets")
    return metadata

def _register_direction_skip(call_id: str, interacao: dict, operador: dict, reason: str) -> None:
    if not call_id:
        return
    if reason == "operator_not_registered":
        status = "skipped_operator"
        failure_reason = "operador_huawei_nao_cadastrado"
    elif reason == "non_telefonia_sector":
        status = "skipped_non_telefonia"
        failure_reason = "setor_nao_telefonia"
    elif _is_direction_skip(reason):
        status = "skipped_direction"
        failure_reason = {
            "direction_unknown": "direcao_desconhecida",
            "risk_inbound": "receptiva_setor_risco",
            "receptiva_setor_desconhecido": "receptiva_setor_desconhecido",
        }.get(reason, "direcao_incompativel")
    elif reason == "operator_huawei_not_registered":
        status = "skipped_operator"
        failure_reason = "operador_huawei_nao_cadastrado"
    elif reason == "oitiva_bas":
        # Descarte definitivo: oitiva (celular) da BAS não é auditável. Status
        # fora da lista reversível de huawei_sync_log_exists evita re-download.
        status = "skipped_oitiva_bas"
        failure_reason = "oitiva_bas_celular"
    else:
        return
    agent_id = (
        _operator_field(operador, "id_huawei", "idHuawei", "id_telefonia", "idTelefonia")
        or _resolve_huawei_operator_id(interacao)
        or None
    )
    database.huawei_sync_log_registrar(
        call_id=call_id,
        agent_id=agent_id,
        media_url=None,
        status=status,
        failure_reason=failure_reason,
        operator_name=_resolve_operator_name_from_interacao(interacao, operador),
        huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
    )

def _debug_direction_skip(call_id: str, interacao: dict, operador: dict, reason: str) -> None:
    if not logger.isEnabledFor(logging.DEBUG) or not _is_direction_skip(reason):
        return
    sector_slug = _operator_sector_id(operador)
    expected = (AUTOMATION_RULES.get(sector_slug) or {}).get("call_direction")
    logger.debug(
        "Sync Huawei: chamada ignorada por direcao "
        "(call_id=%s, setor=%s, esperado=%s, inferido=%s, caller=%s, callee=%s, workNo=%s, reason=%s)",
        call_id,
        sector_slug,
        expected,
        _resolve_huawei_is_call_in(interacao),
        interacao.get("callerNo") or interacao.get("caller"),
        interacao.get("calleeNo") or interacao.get("called"),
        interacao.get("workNo"),
        reason,
    )

def _required_query_directions_for_operators(operadores: list[dict]) -> list[str]:
    directions: set[str] = set()
    if not operadores:
        return ["INBOUND", "OUTBOUND"]

    for operador in operadores:
        sector_slug = _operator_sector_id(operador)
        regra = AUTOMATION_RULES.get(sector_slug)
        raw_direction = str((regra or {}).get("call_direction") or "").strip().upper()
        if raw_direction in {"INBOUND", "OUTBOUND"}:
            directions.add(raw_direction)
        else:
            directions.update({"INBOUND", "OUTBOUND"})

    return [direction for direction in ("INBOUND", "OUTBOUND") if direction in directions]

def _should_skip_receptive_risk_call(interacao: dict, operador: dict) -> bool:
    """Compatibilidade com callers antigos; a regra atual usa _should_skip_call."""
    return _should_skip_call(interacao, operador) is not None


def _cancel_requested(should_cancel: Optional[Callable[[], bool]]) -> bool:
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception:
        logger.warning("Sync Huawei: callback de cancelamento falhou.", exc_info=True)
        return False


def _pause_requested(should_pause: Optional[Callable[[], bool]]) -> bool:
    if should_pause is None:
        return False
    try:
        return bool(should_pause())
    except Exception:
        logger.warning("Sync Huawei: callback de pausa falhou.", exc_info=True)
        return False


async def _wait_if_paused(
    should_pause: Optional[Callable[[], bool]],
    should_cancel: Optional[Callable[[], bool]],
) -> None:
    """Bloqueia o loop enquanto should_pause() retornar True.

    Sai imediatamente se cancel for solicitado. Polling de 0.5s evita busy-loop
    e mantem responsividade ao retomar/cancelar.
    """
    if not _pause_requested(should_pause):
        return
    logger.info("Sync Huawei: pausado pelo usuario; aguardando retomada.")
    while _pause_requested(should_pause):
        if _cancel_requested(should_cancel):
            return
        await asyncio.sleep(0.5)
    logger.info("Sync Huawei: retomado pelo usuario.")


_PROCESS_DELTA_INT_KEYS = (
    "tentativas_download",
    "ignoradas_direcao_incompativel",
    "ignoradas_direcao_desconhecida",
    "ignoradas_receptiva_setor_risco",
    "ignoradas_receptiva_setor_desconhecido",
    "ignoradas_setor_nao_telefonia",
    "ignoradas_operador_huawei_nao_cadastrado",
    "ignoradas_mondelez",
    "ignoradas_teste",
    "sem_duracao_consideradas",
    "pretriagem_direcao_receptiva_descartadas",
    "pretriagem_direcao_ativa_aprovadas",
    "pretriagem_direcao_indefinida",
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
    "obs_voice_dir_empty",
    "baixadas",
    "enfileiradas",
    "duplicadas",
)


from core.huawei_download_chain import HuaweiDownloadChain

async def _processar_candidato(
    interacao: dict,
    *,
    client: HuaweiAICCClient,
    obs_client: Optional[HuaweiOBSClient],
    download_chain: HuaweiDownloadChain,
    operator_by_id: dict,
    operator_by_name: dict,
    should_cancel: Optional[Callable[[], bool]],
    is_manual: bool = False,
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
    operator_truth = _inject_operator_truth(interacao, operador_resolvido)
    agent_id = operator_truth.get("id_huawei") or _resolve_huawei_operator_id(interacao)
    nome_op = operator_truth.get("nome") or operador_resolvido.get("nome", "Nao Identificado")

    skip_reason = _should_skip_call(interacao, operador_resolvido)
    if skip_reason:
        _increment_skip_counter(delta, skip_reason)
        _debug_direction_skip(call_id, interacao, operador_resolvido, skip_reason)
        _register_direction_skip(call_id, interacao, operador_resolvido, skip_reason)
        return delta

    delta["tentativas_download"] += 1

    # Defesa contra Voice/{date}/ vazio (incidente upstream Huawei).
    obs_voice_dir_empty = False
    if obs_client is not None:
        voice_dates = HuaweiOBSClient._candidate_dates(interacao.get("beginTime"))
        if voice_dates:
            any_has_audio = False
            for voice_date in voice_dates:
                if await obs_client.voice_dir_has_objects(voice_date):
                    any_has_audio = True
                    break
            if not any_has_audio:
                obs_voice_dir_empty = True
                delta["obs_voice_dir_empty"] = 1

    try:
        download_ids = _download_id_candidates(interacao, call_id)
        # Prepara dados enriquecidos para a cadeia de download
        call_context = {
            **interacao,
            "callId": call_id,
            "agent_id": agent_id,
            "prefixes": _obs_prefix_candidates(interacao, agent_id),
            "extra_match_ids": _obs_match_ids(interacao, call_id),
            "download_ids": download_ids,
            "skip_obs_primary": False, # Desativado a pedido do usuario: sempre tentar OBS antes do FS
        }

        # Executa a cadeia de download (Chain of Responsibility)
        # Nova Ordem: OBS Direto -> URL Pre-assinada -> FS (CC-FS)
        result = await download_chain.download(call_context, client, obs_client)

        # Atualiza contadores de tentativa e IDs tentados para cada metodo
        # Importante: para testes antigos que esperam ordem FS -> URL, 
        # a nova ordem OBS -> URL -> FS pode causar disparidade nos contadores
        # de tentativa se o metodo de sucesso for o URL (pula o FS).
        for tried_method in result.methods_tried:
            delta[f"{tried_method}_tentativas"] = 1
            if f"{tried_method}_ids_tentados" in delta:
                delta[f"{tried_method}_ids_tentados"] = result.attempts_per_method.get(tried_method, 0)
            
            if tried_method == "obs_primary" and not interacao.get("recordId"):
                delta["obs_primary_sem_record_id_tentativas"] = 1

        if not result.success:
            # Marca misses para todos os metodos que foram tentados e falharam
            for tried_method in result.methods_tried:
                 delta[f"{tried_method}_misses"] = 1
            
            # Caso especial: se pulou o OBS por falta de recordId no manifesto
            if "obs_primary" not in result.methods_tried:
                is_from_manifest = "obs_contact_record" in str(interacao.get("source") or "")
                is_from_vdn = "vdn" in str(interacao.get("source") or "")
                if not interacao.get("recordId") and is_from_manifest and not is_from_vdn:
                    delta["obs_primary_pulado_sem_record_id"] = 1

            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                status='failed',
                failure_reason='audio_not_found',
                operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
            )
            return delta

        # Sucesso: marca hit para o metodo que funcionou e misses para os anteriores
        audio_bytes = result.audio_bytes
        method = result.method_used
        delta[f"{method}_hits"] = 1
        
        for tried_method in result.methods_tried:
            if tried_method != method:
                delta[f"{tried_method}_misses"] = 1

        if _cancel_requested(should_cancel):
            return delta

        # PRÉ-TRIAGEM GR (ATIVA VS RECEPTIVA)
        sector_id = operator_truth.get("setor_id") or ""
        automation_rule = AUTOMATION_RULES.get(sector_id, {})
        expected_direction = str(automation_rule.get("call_direction") or "").strip().upper()
        audio_direction_pre_triage = None
        
        # Apenas se o setor quer EXCLUSIVAMENTE ligações OUTBOUND (como áreas de risco)
        if expected_direction == "OUTBOUND" and sector_id in _AUDIO_DIRECTION_GATE_SECTORS:
            # Direcao resolvida pela CONSULTA VDN por callId (evidencia real,
            # custo Azure zero), com fallback nos metadados da interacao.
            # Substitui a antiga pre-triagem por audio (analyze_call_direction:
            # Whisper + GPT, 2 chamadas pagas por candidata — ver relatorio de
            # consumo de 10/06/2026). VDN vem primeiro porque o isCallIn dos
            # metadados pode ser rotulo sintetico derivado da direcao da query
            # (ver huawei_direction.resolve_huawei_is_call_in) — exatamente a
            # mentira que a pre-triagem por audio existia para pegar.
            # Semantica preservada: True=receptiva descarta, False=ativa segue,
            # None=indeterminada descarta (na duvida nao audita receptiva).
            # Defesa textual downstream: guardrail EFETUADA vs RECEPTIVA da
            # v1.3.73 segue ativo na avaliacao.
            is_inbound = None
            direcao_fonte = "indeterminada"
            try:
                vdn_direction = await client.consultar_direcao_chamada(call_id)
            except Exception:
                logger.warning(
                    "Consulta VDN de direção falhou para '%s'; caindo para metadados.",
                    call_id, exc_info=True,
                )
                vdn_direction = None
            if vdn_direction is True or vdn_direction is False:
                is_inbound = vdn_direction
                direcao_fonte = "vdn_api"
            else:
                metadata_direction = _resolve_huawei_is_call_in(interacao)
                if metadata_direction is not None:
                    is_inbound = metadata_direction
                    direcao_fonte = "metadata"

            if is_inbound is True:
                logger.info(
                    "Direção de '%s' = RECEPTIVA (fonte=%s). Descartando antes do enfileiramento.",
                    call_id, direcao_fonte,
                )
                audio_direction_pre_triage = "inbound_quarantine"
                delta["pretriagem_direcao_receptiva_descartadas"] += 1
                database.huawei_sync_log_registrar(
                    call_id=call_id,
                    agent_id=agent_id,
                    media_url=None,
                    status="skipped_direction",
                    failure_reason="receptiva_direcao_vdn",
                    operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                    huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
                )
                return delta
            elif is_inbound is False:
                audio_direction_pre_triage = "outbound"
                delta["pretriagem_direcao_ativa_aprovadas"] += 1
            else:
                # Direcao indeterminada em SETOR DE RISCO: descarta por seguranca.
                # Regra de negocio: na duvida, nao audita receptiva (so ativa).
                logger.warning(
                    "Direção de '%s' indeterminada via metadados e VDN (setor de risco %s); "
                    "DESCARTANDO antes do enfileiramento (na dúvida não audita receptiva).",
                    call_id,
                    sector_id,
                )
                audio_direction_pre_triage = "indeterminada_descartada"
                delta["pretriagem_direcao_indefinida"] += 1
                database.huawei_sync_log_registrar(
                    call_id=call_id,
                    agent_id=agent_id,
                    media_url=None,
                    status="skipped_direction",
                    failure_reason="direcao_indeterminada_setor_risco",
                    operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                    huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
                )
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
                "huawei_agent_id": interacao.get("agentId") or interacao.get("agent_id") or interacao.get("agentid"),
                "huawei_work_no": interacao.get("workNo"),
                "huawei_is_call_in": _resolve_huawei_is_call_in(interacao),
                "huawei_operator_name": interacao.get("operatorName"),
                "huawei_skill_id": interacao.get("skillId") or interacao.get("skill_id") or interacao.get("skillid"),
                "huawei_vdn": interacao.get("vdn"),
                "huawei_source": interacao.get("source"),
                **_huawei_call_reason_metadata(interacao),
                "huawei_obs_prefixes": _obs_prefix_candidates(interacao, agent_id),
                "huawei_obs_match_ids": _obs_match_ids(interacao, call_id),
                "huawei_download_id_candidates": download_ids,
                "audio_direction_pre_triage": audio_direction_pre_triage,
                "operator_name_real": operator_truth.get("nome"),
                "operator_sector_real": operator_truth.get("setor"),
                "operator_sector_id": operator_truth.get("setor_id"),
                "operator_escala": operator_truth.get("escala"),
                "operator_matricula": operator_truth.get("matricula"),
                "operator_id_huawei_real": operator_truth.get("id_huawei"),
            },
            is_manual=is_manual,
        )

        delta["baixadas"] += 1
        if resultado.get("status") == "queued":
            delta["enfileiradas"] += 1
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                media_url=resultado.get("filename"),
                operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
            )
        elif resultado.get("status") == "duplicate":
            delta["duplicadas"] += 1
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                media_url=resultado.get("filename"),
                operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
            )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao processar interacao %s do operador %s", call_id, nome_op)
        delta["erros"].append(f"Op {nome_op} Call {call_id}: {str(exc)}")
        try:
            database.huawei_sync_log_registrar(
                call_id,
                agent_id=agent_id,
                status='failed',
                failure_reason=f'exception: {str(exc)}',
                operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
            )
        except Exception:
            logger.exception("Falha tambem ao registrar erro no huawei_sync_logs")

    return delta


# Lock de execução do sync (table lock em `configuracoes.sync_lock`) movido para
# core/huawei/sync_lock.py. Reexport mantém compat (callers + patch
# huawei_sync._HuaweiSyncExecutionLock).
from core.huawei.sync_lock import _HuaweiSyncExecutionLock  # noqa: F401,E402

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
            call_key = HuaweiDiscoveryService.resolve_call_key(chamada)
            if not call_key:
                chamadas_sem_id.append(chamada)
                continue
            chamadas_por_id.setdefault(call_key, chamada)

    return list(chamadas_por_id.values()) + chamadas_sem_id

# Enfileiramento de midia movido para core/huawei/sync_enqueue.py. Reexports
# mantem compatibilidade com callers e testes que usam huawei_sync._nome /
# patch("core.huawei_sync.X").
from core.huawei.sync_enqueue import (  # noqa: F401,E402
    _enfileirar_audio,
    _enfileirar_classificado,
    _enfileirar_pdf,
)


_MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000  # 30 dias
# Classificacao automatica (Fase 2) movida para core/huawei/sync_classification.py.
# Reexports mantem compatibilidade com callers e testes que usam
# huawei_sync._nome / patch("core.huawei_sync.X").
from core.huawei.sync_classification import (  # noqa: F401,E402
    _aplicar_auto_classificacao,
    _automation_skip_pending_on_low_confidence_enabled,
    _classificar_audio_huawei,
    _classificar_pdf_huawei,
    _classificar_pendentes_async,
    _marcar_classificacao_status,
    _resolve_auto_classificacao_status,
)

# Triagem setorial movida para core/huawei/sync_triagem.py. Reexports mantem
# compatibilidade com callers e testes que usam huawei_sync._nome / patches.
from core.huawei.sync_triagem import (  # noqa: F401,E402
    _aplicar_triagem_setorial,
    _resolve_triagem_setor,
    _triagem_fallback,
)


def _selecionar_rodizio_por_setor(candidatas: list[dict], limite: int) -> list[dict]:
    """Seleciona ate `limite` candidatos fazendo rodizio entre setores.

    Agrupa por `_setor_rodizio` (setor do operador resolvido, anotado na selecao)
    preservando a ordem de prioridade ja aplicada dentro de cada setor, e pega 1
    de cada setor por vez ate atingir o limite. Evita que um setor de alto volume
    (ex. cadastro) ocupe todas as vagas do ciclo. Se houver <= `limite`
    candidatos, devolve a lista como esta (sem reordenar).
    """
    if limite <= 0 or len(candidatas) <= limite:
        return candidatas
    from collections import OrderedDict

    grupos: "OrderedDict[str, list[dict]]" = OrderedDict()
    for cand in candidatas:
        chave = str(cand.get("_setor_rodizio") or "_sem_setor")
        grupos.setdefault(chave, []).append(cand)

    selecionadas: list[dict] = []
    setores = list(grupos.keys())
    while len(selecionadas) < limite:
        progrediu = False
        for s in setores:
            if grupos[s]:
                selecionadas.append(grupos[s].pop(0))
                progrediu = True
                if len(selecionadas) >= limite:
                    break
        if not progrediu:
            break
    return selecionadas


async def executar_sync_huawei(
    horas_retroativas: float = 1.0,
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    should_pause: Optional[Callable[[], bool]] = None,
    begin_time_ms: Optional[int] = None,
    end_time_ms: Optional[int] = None,
    obs_only: bool = False,
    prefetched_obs_client: Optional[HuaweiOBSClient] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    is_manual: bool = False,
) -> Dict[str, Any]:
    """Funcao principal que baixa, tria e enfileira as ligacoes na revisao.

    Orquestra um ciclo completo de sincronizacao: adquire o lock de execucao,
    valida que o sync esta habilitado e que ha credenciais, descobre chamadas
    (VDN + manifesto OBS), filtra por elegibilidade/cota/duracao, baixa o audio
    (cadeia OBS/FS/URL) com concorrencia limitada e enfileira na fila de
    triagem. Opcionalmente roda a classificacao automatica (Fase 2) se
    habilitada por env.

    Params:
    - horas_retroativas: janela retroativa (em horas) quando nao ha intervalo
      explicito; default 1.0.
    - should_cancel / should_pause: callbacks opcionais consultados ao longo do
      loop para cancelar ou pausar a coleta.
    - begin_time_ms / end_time_ms: intervalo manual explicito em epoch ms;
      quando ambos sao informados o modo vira "manual_interval" (limite de
      30 dias) em vez de "retroactive".
    - obs_only: forca descoberta apenas pelo manifesto OBS (tambem ativavel via
      env HUAWEI_DISCOVERY_OBS_ONLY).
    - prefetched_obs_client: reaproveita um `HuaweiOBSClient` ja criado.
    - progress_callback: callback (fase, atual, total) para reportar progresso.
    - is_manual: marca os itens enfileirados como originados de acao manual.

    Retorna um dict de contadores/estatisticas do ciclo (status, baixadas,
    enfileiradas, duplicadas, ignoradas por varios motivos, etc.).

    Custo de API: o download em si nao chama Azure. A descoberta de direcao usa
    a consulta VDN (sem custo de IA). A Fase 2 de classificacao automatica, SE
    habilitada, dispara transcricao + GPT (chamadas pagas a Azure) — por padrao
    fica desligada. Sempre faz I/O de rede (Huawei/OBS) e banco (logs/fila).

    Efeitos colaterais: lock em `configuracoes`, gravacao de midia, registros em
    `huawei_sync_logs` e itens na fila de triagem.
    """
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
            logger.warning(
                "ENABLE_HUAWEI_SYNC=false; sincronizacao bloqueada por configuracao de ambiente. "
                "Defina ENABLE_HUAWEI_SYNC=true para habilitar."
            )
            return {
                "status": "disabled",
                "message": "Sincronizacao Huawei desligada por configuracao (ENABLE_HUAWEI_SYNC=false). Contate o administrador.",
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
        is_manual_interval = begin_time_ms is not None and end_time_ms is not None
        sync_mode = "manual_interval" if is_manual_interval else "retroactive"
        download_chain = HuaweiDownloadChain(mode=sync_mode)

        if is_manual_interval:
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
        obs_client: Optional[HuaweiOBSClient] = prefetched_obs_client
        if obs_client is None and cfg.get("obs_ak") and cfg.get("obs_sk"):
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
        elif obs_client:
            logger.info("Sync Huawei: usando prefetched OBS client.")
        else:
            logger.info(
                "Sync Huawei: credenciais OBS ausentes; fallback direto desabilitado.",
            )

        _notify_progress(progress_callback, "starting", 0, 0)

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
            "direcao_resolvida": 0,
            "direcao_inbound": 0,
            "direcao_outbound": 0,
            "direcao_desconhecida": 0,
            "ignoradas_direcao_incompativel": 0,
            "ignoradas_direcao_desconhecida": 0,
            "ignoradas_receptiva_setor_risco": 0,
            "ignoradas_receptiva_setor_desconhecido": 0,
            "ignoradas_setor_nao_telefonia": 0,
            "ignoradas_operador_huawei_nao_cadastrado": 0,
            "ignoradas_mondelez": 0,
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
        operadores = operators.listar_auditaveis_com_id_huawei(database.get_connection)
        contadores["operadores_considerados"] = len(operadores)
        operator_by_id, operator_by_name = _build_operator_indexes(operadores)
        call_directions = _required_query_directions_for_operators(operadores)
        contadores["direcoes_consulta_vdn"] = call_directions
        _notify_progress(progress_callback, "loading_operators", len(operadores), len(operadores))

        if _cancel_requested(should_cancel):
            contadores.update(
                {
                    "status": "cancelled",
                    "message": "Coleta de ligacoes cancelada antes da busca.",
                    "cancelado": True,
                }
            )
            return contadores

        await _wait_if_paused(should_pause, should_cancel)
        if _cancel_requested(should_cancel):
            contadores.update(
                {
                    "status": "cancelled",
                    "message": "Coleta cancelada durante pausa.",
                    "cancelado": True,
                }
            )
            return contadores

        # 2. Descobrir chamadas globalmente. A Huawei ignora/omite agentId no
        # querycalls, entao a coleta por operador pode retornar zero ou repetir
        # as mesmas linhas. O manifesto OBS entra como fallback independente da
        # VDN e costuma carregar workNo/countName/caller/called/recordId.
        obs_only_flag = obs_only or (os.getenv("HUAWEI_DISCOVERY_OBS_ONLY", "false").lower() == "true")
        interacoes, call_ids_vdn_unicos, call_ids_manifest_unicos, call_ids_descobertos_unicos = await HuaweiDiscoveryService.fetch_all(
            client,
            obs_client,
            begin_ms,
            end_ms,
            obs_only=obs_only_flag,
            call_directions=call_directions,
        )
        _notify_progress(progress_callback, "discovered", len(interacoes), len(interacoes))

        contadores["chamadas_na_vdn"] = len(call_ids_vdn_unicos)
        contadores["chamadas_no_manifest_obs"] = len(call_ids_manifest_unicos)
        contadores["chamadas_descobertas_total"] = len(call_ids_descobertos_unicos)

        for interacao in interacoes:
            direction = _resolve_huawei_is_call_in(interacao)
            if direction is True:
                contadores["direcao_resolvida"] += 1
                contadores["direcao_inbound"] += 1
            elif direction is False:
                contadores["direcao_resolvida"] += 1
                contadores["direcao_outbound"] += 1
            else:
                contadores["direcao_desconhecida"] += 1

        if not interacoes:
            logger.info("Sync Huawei: nenhuma chamada descoberta na VDN nem no manifesto OBS.")
            return contadores

        logger.info(
            "Sync Huawei descoberta: vdn=%s, manifest=%s, total=%s, direcao_resolvida=%s, direcao_desconhecida=%s, query_directions=%s",
            contadores["chamadas_na_vdn"],
            contadores["chamadas_no_manifest_obs"],
            contadores["chamadas_descobertas_total"],
            contadores["direcao_resolvida"],
            contadores["direcao_desconhecida"],
            ",".join(call_directions),
        )

        # 2.1 Pré-carga de cotas mensais (otimização D-1)
        unique_op_keys: list[tuple[str, str]] = []
        seen_op_keys_set: set[tuple[str, str]] = set()
        for interacao in interacoes:
            op = _resolve_operador_interacao(interacao, operator_by_id, operator_by_name)
            if _should_skip_call(interacao, op):
                continue
            name_norm = str(op.get("nome") or op.get("name") or "").strip().lower()
            id_norm = str(op.get("id_telefonia") or op.get("id_huawei") or "").strip().lower()
            key = (name_norm, id_norm)
            if (name_norm or id_norm) and key not in seen_op_keys_set:
                unique_op_keys.append((op.get("nome") or op.get("name") or "", op.get("id_telefonia") or op.get("id_huawei") or ""))
                seen_op_keys_set.add(key)
        
        from repositories.audits import get_operator_audit_counts_for_month_bulk
        hoje = datetime.now()
        quota_by_operator = get_operator_audit_counts_for_month_bulk(
            database.get_connection,
            unique_op_keys,
            hoje.year,
            hoje.month
        )

        min_duration_seconds = max(
            0,
            _runtime_int_config(
                "HUAWEI_SYNC_MIN_DURATION_SECONDS",
                ("huawei_sync_min_duration_seconds", "huawei_d1_min_duration_seconds"),
                DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS,
            ),
        )
        max_duration_seconds = max(
            0,
            _runtime_int_config(
                "HUAWEI_SYNC_MAX_DURATION_SECONDS",
                ("huawei_sync_max_duration_seconds", "huawei_d1_max_duration_seconds"),
                DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS,
            ),
        )
        max_download_attempts = _effective_download_attempt_limit()
        contadores["min_duracao_padrao_segundos"] = min_duration_seconds
        contadores["max_duracao_padrao_segundos"] = max_duration_seconds
        contadores["limite_tentativas_download"] = max_download_attempts
        contadores["limite_downloads"] = max_download_attempts

        candidatas: list[dict] = []
        por_setor_count: dict[str, int] = {}
        sorted_interacoes = sorted(interacoes, key=_download_candidate_sort_key, reverse=True)
        for index, interacao in enumerate(sorted_interacoes, start=1):
            if index == 1 or index % 250 == 0 or index == len(sorted_interacoes):
                _notify_progress(progress_callback, "selecting_candidates", index, len(sorted_interacoes))
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
            _inject_operator_truth(interacao, operador_resolvido)

            skip_reason = _should_skip_call(interacao, operador_resolvido)
            if skip_reason:
                _increment_skip_counter(contadores, skip_reason)
                _debug_direction_skip(call_id, interacao, operador_resolvido, skip_reason)
                _register_direction_skip(call_id, interacao, operador_resolvido, skip_reason)
                continue

            # Filtro de cota mensal pré-download
            op_name_norm = str(operador_resolvido.get("nome") or operador_resolvido.get("name") or "").strip().lower()
            op_id_norm = str(operador_resolvido.get("id_telefonia") or operador_resolvido.get("id_huawei") or "").strip().lower()
            op_key = (op_name_norm, op_id_norm)
            
            cota_max = max(
                1,
                _coerce_int(database.get_config_value("huawei_cota_max_por_operador_mes", "2"), 2),
            )
            current_quota = quota_by_operator.get(op_key, 0)
            
            if (op_name_norm or op_id_norm) and current_quota >= cota_max:
                contadores.setdefault("ignoradas_cota_mensal_pre_download", 0)
                contadores["ignoradas_cota_mensal_pre_download"] += 1
                database.huawei_sync_log_registrar(
                    call_id=call_id,
                    agent_id=op_id_norm or None,
                    media_url=None,
                    status="skipped_quota",
                    failure_reason="cota_mensal_atingida",
                    operator_name=_resolve_operator_name_from_interacao(interacao, operador_resolvido),
                    huawei_skill_id=_resolve_huawei_skill_id_field(interacao),
                )
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
            # Rodizio por setor: limita a coleta a `max_download_attempts` POR SETOR
            # (em vez de um teto global, que deixava setores de alto volume — ex.
            # cadastro — encher todas as vagas). A selecao final balanceada entre
            # setores e feita apos o loop (_selecionar_rodizio_por_setor).
            cand_setor = setor or "_sem_setor"
            if por_setor_count.get(cand_setor, 0) >= max_download_attempts:
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
            interacao["_setor_rodizio"] = cand_setor
            por_setor_count[cand_setor] = por_setor_count.get(cand_setor, 0) + 1
            call_ids_tentados_no_ciclo.add(call_id)
            # Incremento virtual da cota para candidatos do mesmo ciclo
            quota_by_operator[op_key] = current_quota + 1


        contadores["chamadas_validas_pos_filtro"] = len(call_ids_validos_unicos)
        # Balanceia as vagas do ciclo entre setores (rodizio) antes de baixar,
        # para um setor de alto volume nao monopolizar os downloads.
        candidatas = _selecionar_rodizio_por_setor(candidatas, max_download_attempts)
        contadores["candidatos_download"] = len(candidatas)
        _notify_progress(progress_callback, "candidates_selected", len(candidatas), len(candidatas))

        if contadores.get("status") == "cancelled":
            return contadores

        candidatos_pre_triagem = len(candidatas)
        candidatas = await _aplicar_triagem_setorial(candidatas, contadores)
        contadores["candidatos_pos_triagem"] = len(candidatas)
        contadores["triagem_descartados"] = candidatos_pre_triagem - len(candidatas)
        _notify_progress(progress_callback, "triaged", len(candidatas), candidatos_pre_triagem)
        if candidatos_pre_triagem:
            logger.info(
                "Triagem setorial: %d -> %d (descartados=%d).",
                candidatos_pre_triagem,
                len(candidatas),
                candidatos_pre_triagem - len(candidatas),
            )

        concurrency = max(
            1,
            _coerce_int(
                os.getenv("HUAWEI_SYNC_DOWNLOAD_CONCURRENCY"),
                DEFAULT_HUAWEI_SYNC_DOWNLOAD_CONCURRENCY,
            ),
        )
        contadores["concurrency_downloads"] = concurrency
        semaforo = asyncio.Semaphore(concurrency)
        downloads_concluidos = 0

        async def _wrap(interacao: dict) -> Dict[str, Any]:
            nonlocal downloads_concluidos
            async with semaforo:
                try:
                    return await _processar_candidato(
                        interacao,
                        client=client,
                        obs_client=obs_client,
                        download_chain=download_chain,
                        operator_by_id=operator_by_id,
                        operator_by_name=operator_by_name,
                        should_cancel=should_cancel,
                        is_manual=is_manual,
                    )
                finally:
                    downloads_concluidos += 1
                    _notify_progress(progress_callback, "downloading", downloads_concluidos, len(candidatas))

        if candidatas:
            await _wait_if_paused(should_pause, should_cancel)
            if _cancel_requested(should_cancel) and contadores.get("status") != "cancelled":
                contadores.update(
                    {
                        "status": "cancelled",
                        "message": "Coleta cancelada antes de iniciar downloads.",
                        "cancelado": True,
                    }
                )
                return contadores
            logger.info(
                "Sync Huawei: %d candidatos sendo processados em paralelo (concurrency=%d).",
                len(candidatas),
                concurrency,
            )
            _notify_progress(progress_callback, "downloading", 0, len(candidatas))
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
        # Por padrao fica desligada: Telefonia baixa/enfileira e a triagem decide
        # alerta/setor com contexto proprio. Reative temporariamente com
        # HUAWEI_SYNC_ENABLE_CLASSIFY=true se precisar do comportamento legado.
        if contadores.get("status") != "cancelled" and _should_run_auto_classification_after_sync():
            classify_stats = await _classificar_pendentes_async(
                concurrency=_coerce_int(
                    os.getenv("HUAWEI_SYNC_CLASSIFY_CONCURRENCY"),
                    DEFAULT_HUAWEI_SYNC_CLASSIFY_CONCURRENCY,
                ),
                operator_by_id=operator_by_id,
                operator_by_name=operator_by_name,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
            contadores["classificadas"] = classify_stats.get("classificadas", 0)
            contadores["erros_classificacao"] = classify_stats.get("erros", 0)
            contadores["pendentes_classificacao"] = classify_stats.get("pendentes_restantes", 0)
            contadores["classificacao_automatica"] = "enabled"
        else:
            contadores["classificadas"] = 0
            contadores["erros_classificacao"] = 0
            contadores["pendentes_classificacao"] = contadores.get("enfileiradas", 0)
            contadores["classificacao_automatica"] = "disabled"

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


                logger.exception("Falha ao fechar httpx.AsyncClient compartilhado do OBS.")

