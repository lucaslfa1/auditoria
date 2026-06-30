"""Busca direcionada de ligações para completar cobertura mensal por operador.

A regra de negócio é da automação: identificar operadores abaixo da cobertura
mínima e pedir ao sync Huawei uma busca focada neles. O sync continua sendo o
responsável por descobrir, validar e baixar as chamadas; este módulo só monta o
plano e limita a execução para não transformar cobertura em varredura ilimitada.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional
from zoneinfo import ZoneInfo

import db.database as database
from core.automation_config import (
    _automation_coverage_backfill_enabled,
    _get_automation_coverage_backfill_lookback_days,
    _get_automation_coverage_backfill_max_operators,
)
from core.huawei.automation_config import _initial_quota_coverage_min_per_operator
from core.huawei.cobertura_operador import (
    calcular_dividas_cobertura,
    chave_operador_cobertura,
    chaves_operadores_cobertura,
)
from core.huawei.download_candidates import _clean_huawei_operator_id, _normalize_identity_text
from repositories import audits, operators

_SP_TZ = ZoneInfo("America/Sao_Paulo")
SyncCallable = Callable[..., Awaitable[dict[str, Any]]]


def _epoch_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _operator_summary(operador: dict) -> dict[str, str]:
    return {
        "id": str(operador.get("id") or ""),
        "nome": str(operador.get("nome") or operador.get("name") or "").strip(),
        "matricula": str(operador.get("matricula") or "").strip(),
        "id_huawei": str(operador.get("id_huawei") or operador.get("idHuawei") or "").strip(),
        "id_telefonia": str(operador.get("id_telefonia") or operador.get("idTelefonia") or "").strip(),
        "setor": str(operador.get("setor") or "").strip(),
    }


def _operator_target_ids(operador: dict) -> set[str]:
    values = (
        operador.get("id_huawei"),
        operador.get("idHuawei"),
        operador.get("id_telefonia"),
        operador.get("idTelefonia"),
    )
    return {text.lower() for text in (_clean_huawei_operator_id(value) for value in values) if text}


def _operator_matches_lookup(operador: dict, *, operator_id: str = "", operator_name: str = "") -> bool:
    normalized_id = _clean_huawei_operator_id(operator_id).lower() if operator_id else ""
    normalized_name = _normalize_identity_text(operator_name) if operator_name else ""
    if normalized_id:
        candidate_ids = _operator_target_ids(operador)
        matricula = str(operador.get("matricula") or "").strip().lower()
        if normalized_id in candidate_ids or normalized_id == matricula:
            return True
    if normalized_name:
        return normalized_name == _normalize_identity_text(operador.get("nome") or operador.get("name"))
    return False


def build_operator_coverage_backfill_plan(
    get_connection: Callable[[], Any] = database.get_connection,
    *,
    agora: Optional[datetime] = None,
    minimo_por_operador: Optional[int] = None,
) -> dict[str, Any]:
    """Calcula operadores que ainda precisam de ligações para completar cobertura."""

    agora = agora or datetime.now(_SP_TZ)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=_SP_TZ)
    minimo = max(1, int(minimo_por_operador or _initial_quota_coverage_min_per_operator()))

    roster = operators.listar_auditaveis_com_id_huawei(get_connection)
    keys = chaves_operadores_cobertura(roster)
    counts = (
        audits.get_operator_audit_counts_for_month_bulk(get_connection, keys, agora.year, agora.month)
        if keys
        else {}
    )
    debts = calcular_dividas_cobertura(roster, counts, minimo_por_operador=minimo)

    pending: list[dict[str, Any]] = []
    for operador in roster:
        chave = chave_operador_cobertura(operador)
        faltantes = int(debts.get(chave, 0) or 0)
        if faltantes <= 0:
            continue
        auditorias_mes = max(0, minimo - faltantes)
        pending.append(
            {
                "operator": operador,
                "summary": _operator_summary(operador),
                "auditorias_mes": auditorias_mes,
                "faltantes": faltantes,
            }
        )

    pending.sort(key=lambda item: (-int(item["faltantes"]), item["summary"]["nome"].lower()))
    return {
        "status": "ok",
        "mes": f"{agora.year:04d}-{agora.month:02d}",
        "minimo_por_operador": minimo,
        "operadores_considerados": len(roster),
        "operadores_pendentes": len(pending),
        "operadores": pending,
    }


def _resolve_sync_func(sync_func: Optional[SyncCallable]) -> SyncCallable:
    if sync_func is not None:
        return sync_func
    from core.huawei_sync import executar_sync_huawei

    return executar_sync_huawei


async def _run_sync_for_operator(
    item: dict[str, Any],
    *,
    begin_ms: int,
    end_ms: int,
    sync_func: Optional[SyncCallable] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> dict[str, Any]:
    operador = item["operator"]
    summary = item["summary"]
    faltantes = max(1, int(item.get("faltantes") or 1))
    target_ids = _operator_target_ids(operador)
    target_names = {summary["nome"]} if summary.get("nome") else set()
    sync = _resolve_sync_func(sync_func)

    def _progress(stage: str, current: int, total: int) -> None:
        if progress_callback is not None:
            label = summary.get("nome") or summary.get("id_huawei") or "operador"
            progress_callback(f"{label}:{stage}", current, total)

    result = await sync(
        begin_time_ms=begin_ms,
        end_time_ms=end_ms,
        target_operator_ids=target_ids,
        target_operator_names=target_names,
        max_download_attempts_override=faltantes,
        should_cancel=should_cancel,
        progress_callback=_progress,
    )
    return {
        "operator": summary,
        "faltantes": faltantes,
        "status": result.get("status", "unknown"),
        "baixadas": int(result.get("baixadas", 0) or 0),
        "enfileiradas": int(result.get("enfileiradas", 0) or 0),
        "candidatos_download": int(result.get("candidatos_download", 0) or 0),
        "ignoradas_operador_fora_alvo": int(result.get("ignoradas_operador_fora_alvo", 0) or 0),
        "sync": result,
    }


async def run_operator_coverage_backfill(
    get_connection: Callable[[], Any] = database.get_connection,
    *,
    agora: Optional[datetime] = None,
    max_operators: Optional[int] = None,
    lookback_days: Optional[int] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    sync_func: Optional[SyncCallable] = None,
) -> dict[str, Any]:
    """Executa busca direcionada para operadores abaixo da cobertura mensal."""

    if not _automation_coverage_backfill_enabled():
        return {"status": "disabled", "message": "Backfill de cobertura desligado."}

    agora = agora or datetime.now(_SP_TZ)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=_SP_TZ)
    limit = max(1, int(max_operators or _get_automation_coverage_backfill_max_operators()))
    lookback = max(1, min(int(lookback_days or _get_automation_coverage_backfill_lookback_days()), 30))

    plan = build_operator_coverage_backfill_plan(get_connection, agora=agora)
    selected = plan["operadores"][:limit]
    if not selected:
        return {
            **{key: value for key, value in plan.items() if key != "operadores"},
            "status": "ok",
            "message": "Nenhum operador abaixo da cobertura.",
            "lookback_dias": lookback,
            "executados": [],
            "baixadas": 0,
            "enfileiradas": 0,
        }

    begin_ms = _epoch_ms(agora - timedelta(days=lookback))
    end_ms = _epoch_ms(agora)
    executed: list[dict[str, Any]] = []
    for index, item in enumerate(selected, start=1):
        if should_cancel is not None and should_cancel():
            return {
                **{key: value for key, value in plan.items() if key != "operadores"},
                "status": "cancelled",
                "message": "Backfill cancelado.",
                "lookback_dias": lookback,
                "executados": executed,
                "baixadas": sum(int(row.get("baixadas", 0) or 0) for row in executed),
                "enfileiradas": sum(int(row.get("enfileiradas", 0) or 0) for row in executed),
            }
        if progress_callback is not None:
            progress_callback("coverage_backfill_operator", index, len(selected))
        executed.append(
            await _run_sync_for_operator(
                item,
                begin_ms=begin_ms,
                end_ms=end_ms,
                sync_func=sync_func,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
            )
        )

    return {
        **{key: value for key, value in plan.items() if key != "operadores"},
        "status": "ok",
        "message": "Backfill de cobertura executado.",
        "lookback_dias": lookback,
        "operadores_executados": len(executed),
        "executados": executed,
        "baixadas": sum(int(row.get("baixadas", 0) or 0) for row in executed),
        "enfileiradas": sum(int(row.get("enfileiradas", 0) or 0) for row in executed),
    }


async def buscar_auditorias_faltantes_operador(
    get_connection: Callable[[], Any] = database.get_connection,
    *,
    operator_id: str = "",
    operator_name: str = "",
    agora: Optional[datetime] = None,
    lookback_days: Optional[int] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    sync_func: Optional[SyncCallable] = None,
) -> dict[str, Any]:
    """Busca ativa para um operador específico identificado por id ou nome."""

    if not operator_id and not operator_name:
        return {"status": "invalid_request", "message": "Informe operator_id ou operator_name."}

    agora = agora or datetime.now(_SP_TZ)
    if agora.tzinfo is None:
        agora = agora.replace(tzinfo=_SP_TZ)
    lookback = max(1, min(int(lookback_days or _get_automation_coverage_backfill_lookback_days()), 30))
    plan = build_operator_coverage_backfill_plan(get_connection, agora=agora)
    match = next(
        (
            item
            for item in plan["operadores"]
            if _operator_matches_lookup(item["operator"], operator_id=operator_id, operator_name=operator_name)
        ),
        None,
    )
    if match is None:
        roster = operators.listar_auditaveis_com_id_huawei(get_connection)
        exists = any(_operator_matches_lookup(op, operator_id=operator_id, operator_name=operator_name) for op in roster)
        return {
            "status": "already_complete" if exists else "not_found",
            "message": "Operador sem pendencia de cobertura." if exists else "Operador auditavel nao encontrado.",
            "mes": plan.get("mes"),
        }

    begin_ms = _epoch_ms(agora - timedelta(days=lookback))
    end_ms = _epoch_ms(agora)
    executed = await _run_sync_for_operator(
        match,
        begin_ms=begin_ms,
        end_ms=end_ms,
        sync_func=sync_func,
        should_cancel=should_cancel,
        progress_callback=progress_callback,
    )
    return {
        "status": executed.get("status", "unknown"),
        "message": "Busca direcionada do operador executada.",
        "mes": plan.get("mes"),
        "lookback_dias": lookback,
        **executed,
    }
