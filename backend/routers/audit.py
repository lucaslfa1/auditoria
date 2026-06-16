"""Router de auditoria manual — upload, rascunhos, ciclo de vida e exportacoes.

Concentra as rotas do fluxo de auditoria acionado pelo usuario (upload de audio/PDF
para avaliacao pela IA), o gerenciamento de rascunhos por usuario, as transicoes de
status de uma auditoria (descartar/restaurar/promover), a re-avaliacao e a regeracao
de resumo, alem dos endpoints de exportacao (Excel/DOCX/PDF de relatorio e
transcricao) e o download do audio salvo.

CUSTO DE API (Azure): `POST /api/audit` e `POST /api/audit/reevaluate` disparam o
pipeline pago — transcricao (Azure Speech) e/ou avaliacao (Azure OpenAI GPT-4o) — via
`services.process_audit_with_ai` / `process_pdf_audit` / `reevaluate_audit`.
`POST /api/audit/regenerate-summary` tambem chama o modelo (resumo + feedback). As
demais rotas (rascunhos, descarte/restauracao/promocao, exportacoes, download de audio)
nao tem custo de API — so banco/CPU/arquivo.

Antes de processar um upload novo, `run_audit` valida a cota mensal por operador e so
prossegue se houver espaco (ou `force_override=True`). Todas as rotas exigem usuario
autenticado; o descarte exige perfil admin.
"""

import asyncio
from datetime import datetime
import json
import logging
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from storage.audit_storage import resolve_stored_audit_audio_path
import db.database as database
from repositories import audits
from repositories import operators
from db.domain_constants import AUDIT_STATUS_AWAITING_PAIR, USER_ROLE_ADMIN
from core.runtime_flags import allow_official_criteria_test_fallback
from repositories.audits import (
    get_operator_audit_count_for_month,
    promote_audit_to_pending_approval,
)
from routers.auth import require_authenticated_user
from core.audit_pipeline import build_manual_upload_context

logger = logging.getLogger(__name__)
from routers.common import (
    _safe_filename,
    ensure_supported_upload,
    estimate_stream_size,
    get_supervisor_audit_for_user,
    safe_log_report_export,
)
from schemas import AuditAlert, AuditResult, ReevaluateRequest, RegenerateSummaryRequest
from services import (
    generate_docx_report,
    generate_docx_transcription,
    generate_excel_report,
    generate_pdf_report,
    generate_pdf_transcription,
    process_audit_with_ai,
    process_pdf_audit,
    reevaluate_audit,
)


def _resolve_existing_audit_audio_path(
    audit_id: int,
    media_record: dict | None,
    audit: dict | None = None,
):
    """Resolve o caminho do arquivo de audio de uma auditoria, se ja existir em disco.

    Le `audio_storage_path` do `media_record` e devolve o Path correspondente apenas
    quando o arquivo existe; caso contrario retorna None (o chamador tenta entao
    recuperar o audio da fila de classificados).
    """
    if media_record is None or not media_record.get("audio_storage_path"):
        return None
    audio_path = resolve_stored_audit_audio_path(media_record.get("audio_storage_path"))
    if audio_path is not None and audio_path.exists():
        return audio_path
    return None


def _recover_audit_audio_from_classified_queue(
    audit_id: int,
    audit: dict,
    media_record: dict | None,
) -> dict | None:
    return database.recover_audit_audio_from_classified_queue(audit_id, audit, media_record)


router = APIRouter(tags=["audit"])

# Ativação experimental da análise de sentimento (expansão futura planejada)
SENTIMENT_ANALYSIS_ENABLED = os.getenv("ENABLE_SENTIMENT_ANALYSIS", "false").lower() in ("1", "true", "yes", "on")


def _resolve_quota_reference_date(audio_date: str | None) -> datetime:
    """Determina o mes/ano usado na checagem de cota a partir da data do audio.

    Usa os 10 primeiros caracteres de `audio_date` no formato AAAA-MM-DD; quando
    ausente/vazio cai para `datetime.now()`. Levanta HTTP 400 se a data vier num
    formato invalido.
    """
    if not isinstance(audio_date, str):
        return datetime.now()
    normalized = str(audio_date or "").strip()
    if not normalized:
        return datetime.now()
    try:
        return datetime.strptime(normalized[:10], "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Data do audio invalida. Use o formato AAAA-MM-DD.")


def _safe_persist(result, **kwargs):
    """Persist audit artifacts and make storage failures visible to the caller."""
    try:
        database.persist_audit_artifacts(result, **kwargs)
    except Exception as exc:
        logger.error("Audit artifact persist failed for hash=%s: %s", kwargs.get("input_hash"), exc)
        raise


def _draft_user_id(user: dict) -> str:
    return str(user.get("username") or user.get("sub") or user.get("id") or "0").strip() or "0"


def _coerce_draft_json(payload: dict, json_key: str, object_key: str) -> str:
    """Normaliza um campo do rascunho para uma string JSON valida.

    Aceita o valor ja serializado (em `json_key`) ou o objeto bruto (em `object_key`),
    serializando-o quando necessario (default `[]`). Valida que o resultado e JSON
    parseavel; senao levanta HTTP 400. Retorna a string JSON pronta para persistir.
    """
    value = payload.get(json_key)
    if value is None:
        value = payload.get(object_key, [])

    if isinstance(value, str):
        candidate = value.strip() or "[]"
    else:
        candidate = json.dumps(value if value is not None else [], ensure_ascii=False)

    try:
        json.loads(candidate)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Campo {json_key} deve conter JSON valido.")
    return candidate


def _resolve_required_auditable_operator(
    operator_name: str,
    operator_id: str | None,
    sector_id: str | None,
) -> dict:
    """Resolve o colaborador auditavel correspondente ao operador informado.

    Consulta `operators.resolve_auditable_colaborador` no banco. Se nenhum
    colaborador ativo/auditavel casar com nome/id/setor, levanta HTTP 400 — o upload
    so prossegue para operadores cadastrados como auditaveis.
    """
    colab = operators.resolve_auditable_colaborador(database.get_connection, operator_name, operator_id, sector_id)
    if colab:
        return colab
    raise HTTPException(
        status_code=400,
        detail=(
            "Operador nao auditavel. Selecione um operador ativo do modulo Operadores "
            "para o setor/processo escolhido."
        ),
    )


def _get_configured_monthly_audit_quota() -> int:
    """Retorna a cota mensal de auditorias por operador configurada.

    Delega para `core.automation._get_monthly_audit_quota`; se a leitura falhar,
    cai para o default 2 (e loga o aviso).
    """
    try:
        from core.automation import _get_monthly_audit_quota

        return _get_monthly_audit_quota()
    except Exception as exc:
        logger.warning("Falha ao carregar cota mensal configurada; usando 2: %s", exc)
        return 2


def _resolve_manual_upload_alert(alert: AuditAlert, sector_id: str | None) -> AuditAlert:
    """Revalida o alerta do upload manual contra os criterios oficiais do catalogo.

    Reconstroi o alerta a partir do catalogo (`_build_alert_from_classification`) para
    garantir que a IA use os criterios oficiais do setor — nao os que vieram do
    frontend. Regras:
    - sem `sector_id` ou sem `alert.id`: devolve o alerta como veio.
    - alerta sem criterios oficiais (`AlertWithoutOfficialCriteriaError`): HTTP 400.
    - falha generica na revalidacao: HTTP 503, salvo quando o fallback de teste de
      criterios oficiais esta habilitado (`allow_official_criteria_test_fallback`),
      caso em que mantem o payload do frontend.
    - catalogo sem criterios para o alerta: HTTP 400, exceto sob o mesmo fallback de
      teste (mantem os criterios enviados).
    """
    if not sector_id or not getattr(alert, "id", None):
        return alert

    try:
        from core.automation import AlertWithoutOfficialCriteriaError, _build_alert_from_classification

        canonical_alert = _build_alert_from_classification(sector_id, alert.id)
    except AlertWithoutOfficialCriteriaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        if not allow_official_criteria_test_fallback():
            logger.exception("Falha ao revalidar criterios do alerta manual %s/%s", sector_id, alert.id)
            raise HTTPException(
                status_code=503,
                detail="Falha ao validar criterios oficiais do alerta.",
            )
        logger.warning(
            "Falha ao revalidar criterios do alerta manual %s/%s; mantendo payload do frontend: %s",
            sector_id,
            alert.id,
            exc,
        )
        return alert

    if canonical_alert.criteria:
        return canonical_alert
    if allow_official_criteria_test_fallback() and alert.criteria:
        logger.warning(
            "Alerta manual %s/%s sem criterios no catalogo; mantendo criterios enviados pelo frontend.",
            sector_id,
            alert.id,
        )
        return alert
    raise HTTPException(
        status_code=400,
        detail=f"Alerta '{alert.id}' nao possui criterios cadastrados para o setor '{sector_id}'.",
    )


@router.put("/api/audit/draft/{input_hash}")
async def save_audit_draft(
    input_hash: str,
    draft: dict,
    user: dict = Depends(require_authenticated_user)
):
    """Salva (upsert) o rascunho de uma auditoria para o usuario atual.

    Identificado por `input_hash` (hash do conteudo auditado) + id do usuario. O
    `draft` traz `details`/`details_json` e `transcription`/`transcription_json`,
    normalizados para JSON valido antes de gravar. Efeito: escreve em banco
    (audit_drafts). Retorna `{"ok": True}`. Sem custo de API.
    """
    from repositories.audits import upsert_audit_draft
    details_json = _coerce_draft_json(draft, "details_json", "details")
    transcription_json = _coerce_draft_json(draft, "transcription_json", "transcription")
    upsert_audit_draft(database.get_connection, input_hash, _draft_user_id(user), details_json, transcription_json)
    return {"ok": True}

@router.get("/api/audit/draft/{input_hash}")
async def get_audit_draft(
    input_hash: str,
    user: dict = Depends(require_authenticated_user)
):
    """Recupera o rascunho do usuario atual para um `input_hash`.

    Retorna `{"ok": True, "draft": None}` quando nao ha rascunho, ou os campos
    `details_json`/`transcription_json`/`updated_at` quando existe. Sem custo de API.
    """
    from repositories.audits import get_audit_draft as get_draft
    row = get_draft(database.get_connection, input_hash, _draft_user_id(user))
    if not row:
        return {"ok": True, "draft": None}
    return {
        "ok": True,
        "draft": {
            "details_json": row.get("details_json") or "[]",
            "transcription_json": row.get("transcription_json") or "[]",
            "updated_at": row.get("updated_at"),
        },
    }

@router.post("/api/audit", response_model=AuditResult)
async def run_audit(
    _user: dict = Depends(require_authenticated_user),
    file: UploadFile = File(...),
    alert_json: str = Form(...),
    operator_name: str = Form(None),
    operator_id: str = Form(None),
    sector_id: str = Form(None),
    audio_date: str = Form(None),
    force_override: bool = Form(False),
):
    """Processa um upload manual (audio ou PDF) e devolve o resultado da auditoria.

    Fluxo: valida o JSON do alerta e o operador, resolve o operador para um
    colaborador auditavel, checa a cota mensal (HTTP 429 se excedida, salvo
    `force_override=True`), valida tamanho do upload (max 50 MB, HTTP 413),
    revalida os criterios do alerta contra o catalogo oficial e entao chama o
    pipeline de IA (`process_pdf_audit` para PDF, `process_audit_with_ai` para audio).
    Opcionalmente roda analise de sentimento se `ENABLE_SENTIMENT_ANALYSIS` estiver
    ligado. Persiste o resultado em cache/banco com status `awaiting_pair`.

    Params (multipart form): `file` (audio/PDF), `alert_json` (alerta serializado),
    `operator_name` (obrigatorio para a cota), `operator_id`, `sector_id`,
    `audio_date` (AAAA-MM-DD, referencia da cota), `force_override` (ignora a cota).

    CUSTO DE API: SIM — dispara transcricao (Azure Speech) e/ou avaliacao
    (Azure OpenAI). Efeitos colaterais: le o arquivo enviado, grava artefatos e audio
    no storage/banco. Retorna `AuditResult`.
    """
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
    try:
        try:
            alert_data = json.loads(alert_json)
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="JSON do alerta inválido.")

        operator_name = str(operator_name or "").strip()
        operator_id = str(operator_id or "").strip() or None
        sector_id = str(sector_id or "").strip() or None

        if not operator_name:
            raise HTTPException(status_code=400, detail="O nome do operador é obrigatório para validação da cota.")

        alert = AuditAlert(**alert_data)
        mime_type = ensure_supported_upload(file, allow_pdf=True)
        quota_date = _resolve_quota_reference_date(audio_date)
        resolved_operator = await asyncio.to_thread(
            _resolve_required_auditable_operator,
            operator_name,
            operator_id,
            sector_id,
        )
        operator_name = resolved_operator.get("name") or operator_name
        operator_id = (
            resolved_operator.get("matricula")
            or resolved_operator.get("preferredId")
            or operator_id
        )

        count = await asyncio.to_thread(
            get_operator_audit_count_for_month,
            database.get_connection,
            operator_name,
            quota_date.year,
            quota_date.month,
            operator_id=operator_id,
        )
        monthly_quota = _get_configured_monthly_audit_quota()
        if count >= monthly_quota:
            if not force_override:
                raise HTTPException(
                    status_code=429,
                    detail=f"Limite mensal excedido: O operador {operator_name} já possui {count} auditorias no mês {quota_date.month:02d}/{quota_date.year} (máximo de {monthly_quota} permitidas).",
                    headers={"X-Audit-Count": str(count)},
                )
            logger.warning(
                "[quota-override] Processando auditoria extra para %s (ja tem %d no mes %02d/%d; limite=%d). force_override=True.",
                operator_name, count, quota_date.month, quota_date.year, monthly_quota,
            )

        content = await file.read()
        if len(content) > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="Arquivo excede o limite de 50 MB.")

        alert = _resolve_manual_upload_alert(alert, sector_id)

        pipeline_context = build_manual_upload_context(
            filename=file.filename or "upload",
            source_type=mime_type,
            sector_id=sector_id,
            alert_id=alert.id,
            alert_label=alert.label,
            operator_name=operator_name,
            operator_id=operator_id,
        )

        if mime_type == "application/pdf":
            result, input_hash, from_cache = await process_pdf_audit(
                content,
                mime_type,
                alert,
                operator_name,
                operator_id,
                sector_id,
                pipeline_context=pipeline_context,
            )
        else:
            result, input_hash, from_cache = await process_audit_with_ai(
                content,
                mime_type,
                alert,
                operator_name,
                operator_id,
                sector_id,
                pipeline_context=pipeline_context,
            )

        result.sentiment = None
        result.input_hash = input_hash
        if audio_date:
            result.audio_date = audio_date
        if SENTIMENT_ANALYSIS_ENABLED:
            try:
                from core.sentiment import analyze_sentiment

                transcription_text = " ".join(seg.text for seg in result.transcription if seg.text).strip()
                if transcription_text and len(transcription_text) > 20:
                    sentiment_result = await analyze_sentiment(transcription_text)
                    if sentiment_result:
                        result.sentiment = sentiment_result
                        logger.info("Sentiment: %s", sentiment_result.get("overall", "N/A"))
            except Exception as exc:
                logger.warning("Sentiment analysis skipped: %s", exc)

        # Persist to cache so identical inputs yield identical results
        if input_hash:
            await asyncio.to_thread(
                _safe_persist,
                result,
                from_cache=from_cache,
                input_hash=input_hash,
                alert_id=alert.id,
                alert_label=alert.label,
                operator_id=operator_id,
                sector_id=sector_id,
                audio_bytes=content if mime_type != "application/pdf" else None,
                audio_mime_type=mime_type if mime_type != "application/pdf" else None,
                original_filename=file.filename,
                status=AUDIT_STATUS_AWAITING_PAIR,
                criado_por=_user.get("username") or "manual",
            )

        return result
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.warning("Falha critica capturada na lógica de negócio IA: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Erro ao processar auditoria: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno grave ao processar auditoria.")


@router.get("/api/audit/{audit_id}/audio")
def get_saved_audit_audio(
    audit_id: int,
    user: dict = Depends(require_authenticated_user),
):
    """Faz streaming/download do audio de uma auditoria ja salva.

    Aplica o escopo do usuario via `get_supervisor_audit_for_user` (supervisor so ve
    o proprio setor). Tenta resolver o arquivo a partir do `media_record`; se nao
    achar, tenta recuperar da fila de classificados. HTTP 404 se nao houver registro
    de midia ou o arquivo nao existir. Devolve o conteudo inline com o MIME e nome de
    arquivo originais. Sem custo de API (so leitura de arquivo/banco).
    """
    from routers.common import _safe_filename
    audit = get_supervisor_audit_for_user(user, audit_id)
    media_record = database.get_audit_media_record(audit_id)
    audio_path = _resolve_existing_audit_audio_path(audit_id, media_record, audit)
    if audio_path is None:
        media_record = _recover_audit_audio_from_classified_queue(audit_id, audit, media_record)
        audio_path = _resolve_existing_audit_audio_path(audit_id, media_record, audit)

    if media_record is None or not media_record.get("audio_storage_path"):
        raise HTTPException(status_code=404, detail="Audio da auditoria nao encontrado.")

    if audio_path is None:
        raise HTTPException(status_code=404, detail="Arquivo de audio da auditoria nao encontrado.")

    from fastapi.responses import Response
    from pathlib import Path

    filename = media_record.get("audio_original_filename") or audio_path.name
    safe_name = _safe_filename(filename, fallback=audio_path.name)
    mime_type = media_record.get("audio_mime_type") or "application/octet-stream"

    if hasattr(audio_path, "read_bytes") and not isinstance(audio_path, Path):
        return Response(
            content=audio_path.read_bytes(),
            media_type=mime_type,
            headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
        )

    return FileResponse(
        audio_path,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


class DiscardAuditRequest(BaseModel):
    reason: str | None = None


@router.post("/api/audit/{audit_id}/discard")
async def discard_audit_endpoint(
    audit_id: int,
    payload: DiscardAuditRequest | None = None,
    user: dict = Depends(require_authenticated_user),
):
    """Marca uma auditoria como descartada (soft-delete).

    Apenas administradores podem descartar auditorias. Supervisores não possuem
    esta permissão (regra de negócio 2026-05-27), podendo apenas contestar.
    Descartadas saem da cota mensal, do dashboard e do painel do supervisor.
    """
    if user.get("role") != USER_ROLE_ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Apenas administradores podem descartar auditorias."
        )

    audit = get_supervisor_audit_for_user(user, audit_id)
    reason = (payload.reason if payload else None) or None
    try:
        result = await asyncio.to_thread(
            database.discard_audit,
            audit_id,
            discarded_by=user.get("username") or "Auditoria",
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Erro ao descartar auditoria %s: %s", audit_id, exc)
        raise HTTPException(status_code=500, detail="Erro interno ao descartar auditoria.")

    logger.info(
        "[discard] audit_id=%s operator=%s por=%s motivo=%r",
        audit_id,
        audit.get("operator_name"),
        user.get("username"),
        reason,
    )
    return {"success": True, **result}


@router.post("/api/audit/{audit_id}/restore")
async def restore_audit_endpoint(
    audit_id: int,
    user: dict = Depends(require_authenticated_user),
):
    """Reverte o soft-delete de uma auditoria previamente descartada.

    Autorizacao simetrica ao discard: admin pode restaurar qualquer auditoria;
    supervisor apenas auditorias do proprio setor (reaproveita
    `get_supervisor_audit_for_user`). A auditoria volta ao status anterior
    (armazenado em `pre_discard_status`), re-entra na cota mensal e reaparece
    no painel. A fila pareada e rebalanceada para acomodar o retorno.
    """
    audit = get_supervisor_audit_for_user(user, audit_id)
    try:
        result = await asyncio.to_thread(
            database.restore_audit,
            audit_id,
            restored_by=user.get("username") or "Auditoria",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Erro ao restaurar auditoria %s: %s", audit_id, exc)
        raise HTTPException(status_code=500, detail="Erro interno ao restaurar auditoria.")

    logger.info(
        "[restore] audit_id=%s operator=%s por=%s novo_status=%s",
        audit_id,
        audit.get("operator_name"),
        user.get("username"),
        result.get("status"),
    )
    return {"success": True, **result}


@router.post("/api/audit/{audit_id}/promote-to-pending-approval")
async def promote_audit_endpoint(
    audit_id: int,
    user: dict = Depends(require_authenticated_user),
):
    """Promove manualmente uma auditoria de 'awaiting_pair' para 'pending_approval'.

    Esta promocao deve ser sempre manual (acionada pelo auditor). Auditorias geradas
    automaticamente entram em 'awaiting_pair' e ficam la ate o auditor decidir envia-las
    para a fila de revisao do supervisor via este endpoint.
    """
    audit = get_supervisor_audit_for_user(user, audit_id)
    
    operator_name = audit.get("operator_name")
    operator_id = audit.get("operator_id")
    if operator_name:
        from datetime import datetime
        from core.automation import _get_monthly_audit_quota
        from repositories.audits import get_supervisor_audit_count_for_month
        
        now = datetime.now()
        cota_max = _get_monthly_audit_quota()
        count = await asyncio.to_thread(
            get_supervisor_audit_count_for_month,
            database.get_connection, 
            operator_name, 
            now.year, 
            now.month, 
            operator_id
        )
        
        if count >= cota_max:
            raise HTTPException(
                status_code=400,
                detail=f"Limite de {cota_max} auditorias mensais atingido no painel do supervisor para este operador. Delete uma auditoria existente para liberar espaço."
            )

    try:
        result = await asyncio.to_thread(
            promote_audit_to_pending_approval,
            database.get_connection,
            audit_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Erro ao promover auditoria %s: %s", audit_id, exc)
        raise HTTPException(status_code=500, detail="Erro interno ao promover auditoria.")

    logger.info(
        "[promote] audit_id=%s operator=%s por=%s novo_status=%s",
        audit_id,
        audit.get("operator_name"),
        user.get("username"),
        result.get("status"),
    )
    return {"success": True, **result}


@router.post("/api/audit/reevaluate", response_model=AuditResult)
async def run_reevaluate_audit(
    req: ReevaluateRequest,
    _user: dict = Depends(require_authenticated_user),
):
    """Re-avalia uma auditoria a partir da transcricao (possivelmente editada).

    Reexecuta a avaliacao da IA sobre `req.transcription` + alerta/operador/setor sem
    refazer a transcricao. Se `req.input_hash` for informado, localiza a auditoria
    correspondente (respeitando o escopo do usuario) e atualiza o resultado salvo no
    banco; falha de persistencia e apenas logada, nao quebra o response.

    CUSTO DE API: SIM — chama o modelo de avaliacao (Azure OpenAI). Retorna o novo
    `AuditResult`.
    """
    try:
        user = _user
        target_audit_id = None
        if req.input_hash:
            target_audit_id = await asyncio.to_thread(
                database.get_latest_audit_id_by_input_hash,
                req.input_hash,
            )
            if target_audit_id is not None:
                await asyncio.to_thread(get_supervisor_audit_for_user, user, target_audit_id)

        result = await reevaluate_audit(
            [item.model_dump() for item in req.transcription],
            req.alert,
            req.operator_name,
            req.operator_id,
            req.sector_id,
            req.source_type,
            req.audio_quality,
        )

        if req.input_hash:
            result.input_hash = req.input_hash

        if req.input_hash and target_audit_id is not None:
            try:
                await asyncio.to_thread(
                    database.update_audit_result_by_id,
                    target_audit_id, result, ai_feedback=result.ai_feedback
                )
            except Exception as persist_exc:
                logger.warning("Reevaluate persist warning: %s", persist_exc)

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Erro na re-auditoria: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno ao re-avaliar auditoria.")


@router.post("/api/audit/regenerate-summary")
async def run_regenerate_summary(
    req: RegenerateSummaryRequest,
    _user: dict = Depends(require_authenticated_user),
):
    """Regera apenas o resumo e o feedback da IA para uma auditoria.

    Usa transcricao + alerta + detalhes (criterios ja avaliados) + nome do operador
    para produzir novo texto de resumo/feedback, sem reavaliar os criterios nem
    refazer a transcricao. Nao persiste — so devolve o resultado.

    CUSTO DE API: SIM — chama o modelo de geracao de texto (Azure OpenAI).
    """
    try:
        from core.summary_regeneration import regenerate_summary_and_feedback
        result = await regenerate_summary_and_feedback(
            transcription=req.transcription,
            alert=req.alert,
            details=req.details,
            operator_name=req.operator_name
        )
        return result
    except Exception as exc:
        logger.exception("Erro ao regerar resumo: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno ao regerar resumo.")

@router.post("/api/export/excel")
def export_excel(result: AuditResult, user: dict = Depends(require_authenticated_user)):
    """Gera e devolve o relatorio da auditoria em Excel (.xlsx) como download.

    Recebe o `AuditResult` no corpo, monta a planilha em memoria e a retorna via
    StreamingResponse. Registra o export no log (`safe_log_report_export`). Sem custo
    de API.
    """
    try:
        excel_file = generate_excel_report(result)
        filename = f"auditoria_{_safe_filename(result.timestamp, 'audit')}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        safe_log_report_export(
            report_kind="audit_report",
            file_format="xlsx",
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            user=user,
            result=result,
            file_size_bytes=estimate_stream_size(excel_file),
        )
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("Erro ao exportar Excel: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar relatório Excel.")


@router.post("/api/export/report/docx")
def export_report_docx(result: AuditResult, user: dict = Depends(require_authenticated_user)):
    """Gera e devolve o relatorio da auditoria em Word (.docx) como download.

    Recebe o `AuditResult` no corpo e retorna o documento via StreamingResponse.
    Registra o export no log. Sem custo de API.
    """
    try:
        docx_file = generate_docx_report(result)
        filename = f"auditoria_{_safe_filename(result.timestamp, 'audit')}.docx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        safe_log_report_export(
            report_kind="audit_report",
            file_format="docx",
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            user=user,
            result=result,
            file_size_bytes=estimate_stream_size(docx_file),
        )
        return StreamingResponse(
            docx_file,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("Erro ao exportar DOCX report: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar relatório DOCX.")


@router.post("/api/export/report/pdf")
def export_report_pdf(result: AuditResult, user: dict = Depends(require_authenticated_user)):
    """Gera e devolve o relatorio da auditoria em PDF como download.

    Recebe o `AuditResult` no corpo e retorna o PDF via StreamingResponse. Registra o
    export no log. Sem custo de API.
    """
    try:
        pdf_file = generate_pdf_report(result)
        filename = f"auditoria_{_safe_filename(result.timestamp, 'audit')}.pdf"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        safe_log_report_export(
            report_kind="audit_report",
            file_format="pdf",
            filename=filename,
            media_type="application/pdf",
            user=user,
            result=result,
            file_size_bytes=estimate_stream_size(pdf_file),
        )
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("Erro ao exportar PDF report: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar relatório PDF.")


@router.post("/api/export/transcription/docx")
def export_transcription_docx(result: AuditResult, user: dict = Depends(require_authenticated_user)):
    """Gera e devolve a transcricao da auditoria em Word (.docx) como download.

    Recebe o `AuditResult` no corpo e retorna o documento via StreamingResponse.
    Registra o export no log. Sem custo de API.
    """
    try:
        docx_file = generate_docx_transcription(result)
        filename = f"transcricao_{_safe_filename(result.timestamp, 'transcricao')}.docx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        safe_log_report_export(
            report_kind="transcription",
            file_format="docx",
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            user=user,
            result=result,
            file_size_bytes=estimate_stream_size(docx_file),
        )
        return StreamingResponse(
            docx_file,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("Erro ao exportar DOCX transcricao: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar transcrição DOCX.")


@router.post("/api/export/transcription/pdf")
def export_transcription_pdf(result: AuditResult, user: dict = Depends(require_authenticated_user)):
    """Gera e devolve a transcricao da auditoria em PDF como download.

    Recebe o `AuditResult` no corpo e retorna o PDF via StreamingResponse. Registra o
    export no log. Sem custo de API.
    """
    try:
        pdf_file = generate_pdf_transcription(result)
        filename = f"transcricao_{_safe_filename(result.timestamp, 'transcricao')}.pdf"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        safe_log_report_export(
            report_kind="transcription",
            file_format="pdf",
            filename=filename,
            media_type="application/pdf",
            user=user,
            result=result,
            file_size_bytes=estimate_stream_size(pdf_file),
        )
        return StreamingResponse(
            pdf_file,
            media_type="application/pdf",
            headers=headers,
        )
    except Exception as exc:
        logger.exception("Erro ao exportar PDF transcricao: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao gerar transcrição PDF.")
