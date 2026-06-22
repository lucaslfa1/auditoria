"""Router dos Arquivos Salvos (``/api/salvos``) — CRUD de itens salvos da auditoria.

Gerencia os "arquivos salvos" que o auditor guarda para revisar/promover depois:
podem ser conteúdo livre OU uma auditoria vinculada (``tipo == "auditoria"`` com
``audit_id``). Quando o item está vinculado a uma auditoria, o PUT propaga as
alterações para a própria auditoria (em ``audits``) em vez de só atualizar o item
salvo.

Todos os endpoints exigem admin. Sem custo de API paga em linha: o save é só banco;
o feedback RAG (que faz embedding pago no Azure) é disparado em BackgroundTasks
DEPOIS da resposta HTTP, para não travar o PUT (v1.3.90).
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

import db.database as database
from repositories import audits
from db.domain_constants import DEFAULT_SOURCE_TYPE, SOURCE_TYPES
from routers.auth import require_admin
from schemas import AuditResult, AuditResultDetail, TranscriptionSegment

logger = logging.getLogger(__name__)


def _run_rag_feedback_background(payload: dict) -> None:
    """Wrapper para BackgroundTasks chamar salvar_feedback_rag_sync de forma resiliente.

    v1.3.90: roda depois do response HTTP para o save audit nao ficar travado
    esperando o embedding do Azure (~200ms-vários segundos sob throttling).
    """
    try:
        from core.rag_triagem import salvar_feedback_rag_sync

        salvar_feedback_rag_sync(**payload)
    except Exception:
        logger.warning("Falha ao registrar feedback RAG em background.", exc_info=True)


router = APIRouter(prefix="/api/salvos", tags=["saved-files"])


class ArquivoSalvoRequest(BaseModel):
    """Payload de criação de um arquivo salvo.

    ``tipo`` classifica o item (ex.: "auditoria"); ``audit_id`` vincula a uma
    auditoria existente quando aplicável. Os demais campos são metadados
    descritivos (operador, setor, alerta, score) e o conteúdo em si.
    """

    tipo: str
    conteudo: str
    arquivo: str = ""
    audit_id: int | None = None
    operator_name: str = ""
    sector_id: str = ""
    alert_label: str = ""
    score: float | None = None
    metadata: dict | None = None


class ArquivoSalvoUpdate(BaseModel):
    """Payload de atualização de um arquivo salvo (conteúdo, score e metadados).

    `alert_id`/`alert_label` (opcionais) permitem corrigir o TIPO de alerta de uma
    auditoria salva — usados após "Reavaliar". Quando informados, são persistidos
    no arquivo salvo e, se vinculado, também na auditoria (`audits`). `None` =
    não mexe no alerta (mantém o comportamento legado).
    """

    conteudo: str
    score: float | None = None
    metadata: dict | None = None
    alert_id: str | None = None
    alert_label: str | None = None


def _is_linked_audit_file(item: dict) -> bool:
    return str(item.get("tipo") or "").strip().lower() == "auditoria" and bool(item.get("audit_id"))


def _read_metadata_text(metadata: dict, *keys: str) -> str:
    if not isinstance(metadata, dict):
        return ""
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _read_metadata_number(metadata: dict, key: str, fallback: float | None = None) -> float | None:
    value = metadata.get(key) if isinstance(metadata, dict) else None
    if value is None:
        return fallback
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_source_type(value: str | None) -> str:
    normalized = str(value or DEFAULT_SOURCE_TYPE).strip().lower()
    return normalized if normalized in SOURCE_TYPES else DEFAULT_SOURCE_TYPE


def _build_audit_result_from_saved_update(
    *,
    audit: dict,
    payload: ArquivoSalvoUpdate,
) -> AuditResult:
    """Reconstrói um ``AuditResult`` mesclando a auditoria atual com a edição salva.

    Usado no PUT de um arquivo salvo vinculado a uma auditoria: cada campo é
    resolvido dando precedência ao que veio no ``payload.metadata`` (details,
    transcription, summary, score, operador, etc.), caindo para os valores já
    persistidos em ``audit`` quando o metadata não traz o campo. Transcrições com
    texto vazio são descartadas e o ``source_type`` é normalizado.

    Pode levantar ValueError/ValidationError do Pydantic se os dados forem
    inválidos. Sem efeito colateral (só constrói o objeto).
    """
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    raw_details = metadata.get("details") if isinstance(metadata.get("details"), list) else audit.get("details") or []
    raw_transcription = (
        metadata.get("transcription")
        if isinstance(metadata.get("transcription"), list)
        else audit.get("transcription") or []
    )
    details = [AuditResultDetail(**dict(item)) for item in raw_details if isinstance(item, dict)]
    transcription = [
        TranscriptionSegment(**dict(item))
        for item in raw_transcription
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    summary = _read_metadata_text(metadata, "summary") or payload.conteudo or audit.get("summary") or ""
    ai_feedback = _read_metadata_text(metadata, "ai_feedback") or audit.get("ai_feedback")
    score = payload.score
    if score is None:
        score = _read_metadata_number(metadata, "score", audit.get("score"))
    max_score = _read_metadata_number(metadata, "maxPossibleScore", audit.get("max_score"))
    source_type = _normalize_source_type(_read_metadata_text(metadata, "source_type") or audit.get("source_type"))

    return AuditResult(
        score=float(score if score is not None else 0.0),
        maxPossibleScore=float(max_score if max_score is not None else 0.0),
        summary=summary,
        ai_feedback=ai_feedback,
        details=details,
        transcription=transcription,
        operatorName=_read_metadata_text(metadata, "operator_name", "operatorName") or audit.get("operator_name") or "",
        operatorId=_read_metadata_text(metadata, "operator_id", "operatorId", "id_huawei", "idHuawei") or audit.get("operator_id") or "",
        timestamp=_read_metadata_text(metadata, "timestamp") or audit.get("timestamp"),
        input_hash=audit.get("input_hash") or None,
        source_type=source_type,
        audit_scope=audit.get("audit_scope") or "call_quality",
        audio_quality=audit.get("audio_quality"),
        audio_date=_read_metadata_text(metadata, "audio_date", "audioDate") or audit.get("audio_date"),
    )


@router.post("")
def salvar_arquivo(payload: ArquivoSalvoRequest, user: dict = Depends(require_admin)):
    """Cria um novo arquivo salvo e retorna o id gerado.

    Persiste via ``database.save_arquivo`` registrando o autor (username). Só
    admin. Efeito: escrita no banco. Retorna ``{"id", "message"}``.
    """
    new_id = database.save_arquivo(
        tipo=payload.tipo,
        conteudo=payload.conteudo,
        arquivo=payload.arquivo,
        audit_id=payload.audit_id,
        operator_name=payload.operator_name,
        sector_id=payload.sector_id,
        alert_label=payload.alert_label,
        score=payload.score,
        metadata=payload.metadata,
        criado_por=user.get("username", ""),
    )
    return {"id": new_id, "message": "Arquivo salvo com sucesso."}


@router.get("")
def listar_salvos(
    limit: int = 100,
    offset: int = 0,
    tipo: str | None = None,
    include_audits: bool = True,
    _user: dict = Depends(require_admin),
):
    """Lista os arquivos salvos paginados, com total.

    Filtra por ``tipo`` opcional e, quando ``include_audits=True``, inclui as
    auditorias vinculadas. Só admin. Em caso de erro retorna HTTP 500 com mensagem
    e traceback no corpo JSON. Efeito: leitura no banco. Retorna
    ``{"items": [...], "total": <int>}``.
    """
    try:
        items = database.list_arquivos_salvos(
            limit=limit,
            offset=offset,
            tipo=tipo,
            include_audits=include_audits,
        )
        total = database.count_arquivos_salvos(tipo=tipo, include_audits=include_audits)
        return {"items": items, "total": total}
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})


@router.get("/{arquivo_id}")
def buscar_salvo(arquivo_id: int, _user: dict = Depends(require_admin)):
    """Busca um arquivo salvo pelo id (HTTP 404 se não existir). Só admin."""
    item = database.get_arquivo_salvo(arquivo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return item


@router.put("/{arquivo_id}")
def atualizar_salvo(
    arquivo_id: int,
    payload: ArquivoSalvoUpdate,
    background_tasks: BackgroundTasks,
    _user: dict = Depends(require_admin),
):
    """Atualiza um arquivo salvo; se vinculado a auditoria, propaga para ela.

    Carrega o item (HTTP 404 se inexistente). Para item vinculado a auditoria
    (``tipo == "auditoria"`` com ``audit_id``): reconstrói o ``AuditResult`` a
    partir da edição e atualiza a auditoria em ``audits`` (HTTP 400 em dados
    inválidos; HTTP 404 se a auditoria sumiu); o feedback RAG resultante é agendado
    em BackgroundTasks (embedding pago no Azure, fora do caminho da resposta).
    Para item comum: atualiza só conteúdo/score/metadata do arquivo salvo.

    Só admin. Efeito: escrita no banco (+ possível chamada paga de RAG em background).
    """
    item = database.get_arquivo_salvo(arquivo_id)
    if not item:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

    if _is_linked_audit_file(item):
        audit_id = int(item["audit_id"])
        audit = audits.get_audit_by_id(database.get_connection, audit_id)
        if not audit:
            raise HTTPException(status_code=404, detail="Auditoria vinculada não encontrada.")
        try:
            result = _build_audit_result_from_saved_update(audit=audit, payload=payload)
            # Corrigir o tipo de alerta (quando informado) ANTES do update do
            # resultado: assim o espelhamento disparado por update_audit_by_id
            # já parte da auditoria com o alerta novo. O score/detalhes vêm do
            # result (reavaliado pelo front via /api/audit/reevaluate).
            if payload.alert_id is not None or payload.alert_label is not None:
                database.update_audit_alert(audit_id, payload.alert_id, payload.alert_label)
            outcome = database.update_audit_by_id(
                audit_id,
                result,
                ai_feedback=result.ai_feedback,
            )
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not outcome or not outcome.get("updated"):
            raise HTTPException(status_code=404, detail="Auditoria vinculada não encontrada.")
        # O espelhamento (update) não copia alert_label do audit; refletir aqui.
        if payload.alert_label is not None:
            database.update_arquivo_alert_label(arquivo_id, payload.alert_label)
        # v1.3.90: feedback RAG vai pra background pra nao travar o response do PUT.
        rag_payload = outcome.get("rag_payload")
        if rag_payload:
            background_tasks.add_task(_run_rag_feedback_background, rag_payload)
        return {"success": True, "message": "Auditoria atualizada com sucesso.", "audit_id": audit_id}

    content = payload.conteudo
    score = payload.score
    metadata = payload.metadata
    updated = database.update_arquivo_salvo(
        arquivo_id, content, score=score, metadata=metadata
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    if payload.alert_label is not None:
        database.update_arquivo_alert_label(arquivo_id, payload.alert_label)
    return {"success": True, "message": "Arquivo atualizado com sucesso."}


@router.delete("/{arquivo_id}")
def deletar_salvo(arquivo_id: int, _user: dict = Depends(require_admin)):
    """Exclui um arquivo salvo pelo id (HTTP 404 se não existir).

    Só admin. Efeito: DELETE no banco.
    """
    deleted = database.delete_arquivo_salvo(arquivo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return {"success": True, "message": "Arquivo excluído com sucesso."}
