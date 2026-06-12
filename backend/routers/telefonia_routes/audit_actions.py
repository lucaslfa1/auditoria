"""Endpoints de ações por gravação da Telefonia: triagem, classificação e auditoria.

Movidos de routers/telefonia.py sem mudança de comportamento: helpers,
constantes e estado compartilhado (tasks ativas, semáforo de classificação)
continuam no orquestrador e são acessados em runtime via `tf.<nome>`.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db.database as database
from db.domain_constants import (
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_REVIEWED,
)
from repositories import classification_review
from routers import telefonia as tf
from routers.auth import require_admin

router = APIRouter()


@router.post("/recordings/{input_hash}/triage")
def enviar_gravacao_para_triagem(
    input_hash: str,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Coloca uma gravacao Huawei na triagem manual."""
    item = tf._get_huawei_queue_item_or_404(input_hash)
    status = str(item.get("status") or "").strip()

    if status in {
        REVIEW_QUEUE_STATUS_REVIEWED,
        REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
        REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    }:
        return {
            "success": True,
            "status": status,
            "message": "Gravacao ja esta na triagem manual.",
        }
    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(
            status_code=409,
            detail="Gravacao nao pode voltar para triagem a partir do status atual.",
        )
    tf._raise_if_huawei_direction_blocked(item)

    updated = classification_review.atualizar_status_fila_revisao_classificacao(database.get_connection,
        input_hash,
        status=REVIEW_QUEUE_STATUS_PENDING,
        motivos_revisao_append=[tf.TELEFONIA_TRIAGE_REASON],
        metadata_merge={
            "telefonia_triage_requested_at": datetime.now(timezone.utc).isoformat(),
            "telefonia_triage_requested_by": user.get("username") or user.get("sub") or "admin",
            "is_manual": True,
        },
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Gravacao Huawei nao encontrada.")

    return {
        "success": True,
        "status": REVIEW_QUEUE_STATUS_PENDING,
        "message": "Gravacao enviada para triagem manual.",
    }


@router.post("/recordings/{input_hash}/classify")
async def classificar_gravacao_manual(
    input_hash: str,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Roda a classificacao IA (setor/alerta) em um audio ja baixado da Huawei."""
    item = tf._get_huawei_queue_item_or_404(input_hash)
    status = str(item.get("status") or "").strip()

    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(status_code=409, detail="Gravacao ja foi auditada.")
    tf._raise_if_huawei_direction_blocked(item)

    metadata = tf._queue_metadata(item)
    media_path = metadata.get("classified_audio_path") or metadata.get("classified_file_path")
    if not media_path:
        raise HTTPException(status_code=404, detail="Caminho de audio ausente.")

    from core.automation import load_classified_audio
    audio_bytes = load_classified_audio(media_path, input_hash=input_hash)
    if not audio_bytes:
        raise HTTPException(status_code=404, detail="Arquivo de audio indisponivel.")

    filename = str(item.get("nome_arquivo") or "gravacao.wav")

    # Montar operador
    operator_id = str(metadata.get("operator_id") or metadata.get("id_huawei") or "").strip()
    operator_name = str(metadata.get("operator_name") or item.get("operador_previsto") or "").strip()
    operador = tf._resolve_registered_huawei_operator(metadata, item)
    if operador is None:
        huawei_id_hint = (
            operator_id
            or str(metadata.get("huawei_agent_id") or "").strip()
            or str(metadata.get("huawei_work_no") or "").strip()
        )
        detail = (
            "Operador Huawei nao cadastrado ou nao auditavel. "
            "Cadastre o operador com ID Huawei no modulo Operadores antes de classificar."
        )
        if huawei_id_hint:
            raise HTTPException(status_code=400, detail=detail)
        raise HTTPException(
            status_code=400,
            detail=(
                "Gravacao Huawei sem ID Huawei na metadata. "
                "Reprocesse a sincronizacao D-1 antes de classificar."
            ),
        )

    from core.huawei_sync import _classificar_audio_huawei, _aplicar_auto_classificacao, _marcar_classificacao_status, _operator_truth_snapshot
    operator_truth = _operator_truth_snapshot(operador)

    try:
        async with tf._get_classify_semaphore():
            result = await _classificar_audio_huawei(
                audio_bytes,
                filename,
                operador,
                native_call_reason=str(metadata.get("huawei_call_reason") or "").strip() or None,
                native_call_reason_code=str(metadata.get("huawei_call_reason_code") or "").strip() or None,
            )
    except Exception as exc:
        _marcar_classificacao_status(input_hash, status="error", erro=str(exc))
        raise HTTPException(status_code=500, detail=f"Erro na classificacao: {exc}")

    sector_id = metadata.get("operator_sector_id") or operator_truth.get("setor_id") or getattr(result, "sector_id", None) or "desconhecido"
    alert_id = getattr(result, "alert_id", None) or "desconhecido"
    confidence = getattr(result, "confidence", 0.0) or 0.0

    _aplicar_auto_classificacao(
        input_hash,
        sector_id=sector_id,
        alert_id=alert_id,
        operator_name=operator_truth.get("nome") or getattr(result, "operator_name", None) or operator_name or None,
        confianca=confidence,
        needs_review=True,  # Força needs_review=True para manter o status='pending' na tela de Triagem
        review_reasons=list(getattr(result, "review_reasons", []) or []),
        review_priority=str(getattr(result, "review_priority", "low") or "low"),
        erro=getattr(result, "error", None),
        id_huawei=getattr(result, "id_huawei", None) or operator_truth.get("id_huawei"),
        matricula=getattr(result, "matricula", None) or operator_truth.get("matricula"),
    )

    return {
        "success": True,
        "message": "Classificacao concluida.",
        "sector_id": sector_id,
        "alert_id": alert_id,
    }


class AuditRecordingRequest(BaseModel):
    """Payload do POST /recordings/{hash}/audit."""

    force: bool = False  # True = re-audita mesmo que já exista auditoria para o hash


@router.post("/recordings/{input_hash}/audit", status_code=202)
async def auditar_instantaneamente_gravacao(
    input_hash: str,
    payload: AuditRecordingRequest | None = None,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Agenda auditoria em background e retorna 202 imediatamente.

    O frontend deve consultar GET /recordings/{hash}/audit-status para acompanhar.
    Padrao classico de long-running task: validacoes rapidas + agendamento + polling.

    Body opcional `{"force": true}` (v1.3.88): permite ao auditor forcar o envio
    sobrescrevendo gates de needs_manual_triage e direction guardrail. NAO
    sobrescreve `blocked_operator` (operador sem cadastro falha mesmo) nem
    auditorias ja concluidas/em cota mensal. A automacao (ciclo) nunca passa
    por aqui — ela so processa itens em ready_for_audit.
    """
    force = bool(payload.force) if payload is not None else False
    item = tf._get_recording_queue_item_or_404(input_hash)
    status_atual = str(item.get("status") or "").strip()

    if status_atual in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(status_code=409, detail="Gravacao ja foi auditada.")
    if status_atual == REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR:
        # Force nao supera operador inexistente: o pipeline vai falhar ao
        # resolver o colaborador. Resposta clara em vez de deixar quebrar adiante.
        raise HTTPException(
            status_code=409,
            detail="Operador nao cadastrado. Cadastre no modulo Operadores antes de auditar.",
        )
    if status_atual == REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE and not force:
        # v1.3.87: motivos apenas de transcricao liberam audit automaticamente.
        # Outros motivos exigem force=true (v1.3.88) — auditor decide com base
        # no que ele ve na fila e assume a responsabilidade.
        motivos = item.get("motivos_revisao") or []
        if not isinstance(motivos, list):
            motivos = []
        only_transcription = bool(motivos) and all(
            str(m).strip().lower().startswith("transcricao_")
            for m in motivos
            if str(m).strip()
        )
        if not only_transcription:
            raise HTTPException(
                status_code=409,
                detail="Gravacao precisa de correcao manual antes da auditoria.",
            )
    if not force:
        tf._raise_if_huawei_direction_blocked(item)

    metadata = tf._queue_metadata(item)
    audit_task_status = str(metadata.get("audit_task_status") or "").strip().lower()
    if audit_task_status == "processing":
        started_at = tf._parse_iso_to_aware(metadata.get("audit_task_started_at"))
        if started_at and (datetime.now(timezone.utc) - started_at) < tf.AUDIT_TASK_INFLIGHT_TIMEOUT:
            raise HTTPException(
                status_code=409,
                detail="Auditoria ja em processamento. Aguarde a conclusao ou refresh do status.",
            )

    ctx = tf._extract_audit_context(item)
    ctx = tf._validate_audit_context_or_raise(ctx, item)
    pipeline_context = tf.coerce_pipeline_context(ctx.get("pipeline_context"))

    audit_requested_by = user.get("username") or user.get("sub") or "telefonia_manual"
    criado_por = tf._resolve_audit_created_by_for_queue_item(item, user)
    started_at = tf._utc_now_iso()
    metadata_merge: Dict[str, Any] = {
        "audit_task_status": "processing",
        "audit_task_started_at": started_at,
        "audit_task_requested_by": audit_requested_by,
        "audit_task_error": None,
    }
    if force:
        metadata_merge["audit_forced"] = True
        metadata_merge["audit_forced_by"] = audit_requested_by
        metadata_merge["audit_forced_at"] = started_at
    claim = classification_review.tentar_iniciar_processamento_auditoria(
        database.get_connection,
        input_hash,
        status=status_atual or REVIEW_QUEUE_STATUS_PENDING,
        metadata_merge=metadata_merge,
        inflight_timeout_seconds=int(tf.AUDIT_TASK_INFLIGHT_TIMEOUT.total_seconds()),
        ignore_status_block=force,
    )
    if not claim.get("started"):
        reason = str(claim.get("reason") or "")
        if reason == "processing":
            raise HTTPException(
                status_code=409,
                detail="Auditoria ja em processamento. Aguarde a conclusao ou refresh do status.",
            )
        if reason == "blocked_status":
            raise HTTPException(status_code=409, detail="Gravacao nao pode ser auditada a partir do status atual.")
        raise HTTPException(status_code=404, detail="Gravacao nao encontrada para iniciar auditoria.")

    tf._start_audit_task(
        input_hash,
        sector_id=ctx["sector_id"],
        alert_id=ctx["alert_id"],
        operator_name=ctx["operator_name"],
        operator_id=ctx["operator_id"],
        source_type=ctx["source_type"],
        filename=ctx["filename"],
        media_path=ctx["media_path"],
        criado_por=criado_por,
        audit_requested_by=audit_requested_by,
        pipeline_context=pipeline_context.to_audit_metadata() if pipeline_context else None,
    )

    return {
        "success": True,
        "status": "processing",
        "input_hash": input_hash,
        "started_at": started_at,
        "message": "Auditoria iniciada em background. Acompanhe via /audit-status.",
    }

@router.get("/recordings/{input_hash}/audit-status")
async def consultar_status_auditoria(
    input_hash: str,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Retorna o estado atual do background task de auditoria para um item da fila.

    Estados: 'idle' (nenhum task), 'processing', 'completed', 'failed'.
    Frontend deve fazer polling enquanto status == 'processing'.
    """
    item = tf._get_recording_queue_item_or_404(input_hash, require_audio=False)
    metadata = tf._queue_metadata(item)
    fila_status = str(item.get("status") or "").strip()
    task_status = str(metadata.get("audit_task_status") or "").strip().lower()

    if fila_status == REVIEW_QUEUE_STATUS_AUDITED:
        return {
            "status": "completed",
            "audit_id": metadata.get("audit_id"),
            "saved_file_available": bool(metadata.get("audit_task_saved_file_available", True)),
            "completed_at": metadata.get("audit_task_completed_at"),
        }

    if task_status == "failed":
        return {
            "status": "failed",
            "error_message": metadata.get("audit_task_error") or "Erro desconhecido.",
            "failed_at": metadata.get("audit_task_failed_at"),
        }

    if task_status == "processing":
        started_at = tf._parse_iso_to_aware(metadata.get("audit_task_started_at"))
        is_stale = (
            started_at is not None
            and (datetime.now(timezone.utc) - started_at) >= tf.AUDIT_TASK_INFLIGHT_TIMEOUT
        )
        return {
            "status": "stale" if is_stale else "processing",
            "started_at": metadata.get("audit_task_started_at"),
        }

    return {"status": "idle"}


@router.delete("/recordings/{input_hash}/audit")
async def cancelar_auditoria(
    input_hash: str,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Cancela a execução atual de uma auditoria em background, voltando ao status pendente."""
    item = tf._get_recording_queue_item_or_404(input_hash, require_audio=False)
    metadata = tf._queue_metadata(item)
    task_status = str(metadata.get("audit_task_status") or "").strip().lower()

    if task_status not in ("processing", "stale", "failed"):
        raise HTTPException(
            status_code=400,
            detail="Auditoria não está em andamento ou falha para ser cancelada."
        )

    classification_review.atualizar_status_fila_revisao_classificacao(
        database.get_connection,
        input_hash,
        status=REVIEW_QUEUE_STATUS_PENDING,
        metadata_merge={
            "audit_task_status": "canceled",
            "audit_task_started_at": None,
            "audit_task_error": "Cancelada manualmente pelo usuário.",
        },
    )

    task_cancel_requested = False
    task = tf._ACTIVE_AUDIT_TASKS.get(input_hash)
    if task is not None and not task.done():
        task.cancel()
        task_cancel_requested = True

    return {
        "success": True,
        "message": "Auditoria cancelada e restaurada para pendente.",
        "task_cancel_requested": task_cancel_requested,
    }
