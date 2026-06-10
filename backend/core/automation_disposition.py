"""Camada central de disposicao da esteira de automacao.

No modo automacao, todo item termina em UM de dois estados terminais: AUDITADO
(audits.status=awaiting_pair, chega ao auditor em Arquivos Salvos) ou DESCARTADO.
Nada fica preso em needs_manual_triage/blocked_operator/monthly_capped.

Este modulo centraliza o EFEITO do descarte (tombstone, contador anti-loop, log
padronizado). A CLASSIFICACAO (qual disposicao cada item recebe) permanece em cada
gate, que tem o contexto de negocio — aqui so executamos a decisao.
"""
from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Disposition(str, Enum):
    PROCEED = "proceed"                            # segue e e auditado
    DISCARD_IMPOSSIBLE = "discard_impossible"      # nunca vira auditavel -> tombstone permanente
    DISCARD_RECOVERABLE = "discard_recoverable"    # pode voltar num proximo sync -> anti-loop
    RETRY = "retry"                                # transitorio: volta a pending ate esgotar


def _discard_loop_limit() -> int:
    """Quantos descartes recuperaveis do mesmo call_id antes de virar tombstone."""
    raw = os.getenv("AUTOMATION_DISCARD_LOOP_LIMIT", "3")
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 3


def _transient_retry_limit() -> int:
    """Quantas tentativas de auditoria para erros transitorios (timeout/audio ausente).

    Default 1 = SEM re-tentativa (uma passada so). Politica: 'auditar e so uma
    vez; se falhar, vai para triagem manual e o humano edita'. Com limite 1, a
    falha de transcricao cai direto em needs_manual_triage (nao re-transcreve =
    nao gasta Azure de novo); falha de infra (timeout/audio ausente) e descartada
    recuperavel. Reversivel via env (AUTOMATION_TRANSIENT_RETRY_LIMIT=3 restaura o
    retry anterior). Ver logs/versions/1.3.111.
    """
    raw = os.getenv("AUTOMATION_TRANSIENT_RETRY_LIMIT", "1")
    try:
        return max(1, int(str(raw).strip()))
    except (TypeError, ValueError):
        return 1


def transient_retry_state(
    metadata: Optional[dict],
    *,
    retry_limit: Optional[int] = None,
) -> tuple[bool, int]:
    """Para um erro transitorio, decide se re-tenta (volta a pending) ou esgotou (descartar).

    Retorna (should_retry, next_attempt_count). O contador vive em
    metadata['automation_transient_retries']. Acaba a "automacao zumbi": apos
    AUTOMATION_TRANSIENT_RETRY_LIMIT tentativas, o item e descartado em vez de
    reentrar em loop.
    """
    if retry_limit is None:
        retry_limit = _transient_retry_limit()
    metadata = metadata if isinstance(metadata, dict) else {}
    try:
        current = int(metadata.get("automation_transient_retries") or 0)
    except (TypeError, ValueError):
        current = 0
    next_count = current + 1
    return (next_count < retry_limit, next_count)


def execute_discard(
    item: Optional[dict],
    disposition: Disposition,
    *,
    motivo: str,
    status_result: str,
    queue_input_hash: str,
    filename: str = "",
    sector_id: Optional[str] = None,
    operator_name: Optional[str] = None,
    operator_id: Optional[Any] = None,
    metadata: Optional[dict] = None,
    loop_limit: Optional[int] = None,
) -> dict:
    """Executa o descarte de um item da fila no modo automacao e devolve o dict de
    status para _audit_single_item. `status_result` DEVE comecar com 'discarded'
    (a telemetria do lote soma por startswith('discarded')).

    DISCARD_IMPOSSIBLE  -> descartar_item_automacao(tombstone=True)  — nunca rebaixa.
    DISCARD_RECOVERABLE -> descartar_item_automacao(tombstone=False) — rebaixa ate o
                           limite anti-loop por call_id, quando vira tombstone.
    """
    if disposition not in (Disposition.DISCARD_IMPOSSIBLE, Disposition.DISCARD_RECOVERABLE):
        raise ValueError(f"execute_discard nao aceita disposition={disposition!r}")

    from db import database

    item = item if isinstance(item, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    if loop_limit is None:
        loop_limit = _discard_loop_limit()
    tombstone = disposition == Disposition.DISCARD_IMPOSSIBLE

    log_fields = {
        "nome_arquivo": filename,
        "setor_previsto": sector_id,
        "operador_previsto": operator_name,
        "huawei_call_id": metadata.get("huawei_call_id"),
        "confidence": item.get("confianca"),
        "disposition": disposition.value,
        "metadata_snapshot": {
            "operator_id": operator_id,
            "ai_sector_id": sector_id,
            "review_reasons": metadata.get("review_reasons"),
        },
    }
    result = database.descartar_item_automacao(
        queue_input_hash,
        motivo=motivo,
        tombstone=tombstone,
        tombstone_motivo=motivo,
        loop_limit=loop_limit,
        log_fields=log_fields,
    )
    logger.info(
        "Automacao: '%s' DESCARTADO (%s; motivo=%s; tombstone=%s; sync_status=%s; attempts=%s).",
        filename,
        disposition.value,
        motivo,
        tombstone,
        (result or {}).get("tombstone"),
        (result or {}).get("attempts"),
    )
    return {"status": status_result, "discard": result}
