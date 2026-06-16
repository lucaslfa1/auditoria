"""AI Feedback router — CRUD endpoints for auditor calibration feedback.

Os feedbacks sao correcoes/observacoes que os auditores humanos registram para
calibrar as avaliacoes da IA (ex.: "a IA marcou X como reprovado, mas o correto era
aprovado"). Esses registros viram referencia consultada pelo pipeline de auditoria
nas proximas avaliacoes.

Sem custo de API nestas rotas: apenas leitura/gravacao no banco via `core.ai_feedback`.
A unica chamada externa e o envio de e-mail de notificacao (`send_new_feedback_email`)
ao criar um feedback avulso — feito de forma sincrona porque no Cloud Run a CPU congela
apos o response e BackgroundTasks morreriam. Todas as rotas exigem usuario autenticado.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.ai_feedback import (
    list_feedback,
    get_feedback_by_id,
    add_feedback,
    update_feedback,
    toggle_feedback,
    delete_feedback,
    VALID_TIPOS,
)
from core.email_utils import send_new_feedback_email
from routers.auth import require_authenticated_user

router = APIRouter(prefix="/api/ai-feedback", tags=["ai-feedback"])


class FeedbackCreate(BaseModel):
    tipo: str
    situacao: str
    correcao: str
    justificativa: str
    setor: Optional[str] = None
    criterio_id: Optional[str] = None
    exemplo_transcricao: Optional[str] = None


class FeedbackUpdate(BaseModel):
    situacao: Optional[str] = None
    correcao: Optional[str] = None
    justificativa: Optional[str] = None
    setor: Optional[str] = None
    criterio_id: Optional[str] = None
    exemplo_transcricao: Optional[str] = None


class AuditCriterionCorrection(BaseModel):
    criterion_id: str
    label: str
    previous_status: Optional[str] = None
    previous_comment: Optional[str] = None
    corrected_status: str
    corrected_comment: Optional[str] = None


class AuditCorrectionsCreate(BaseModel):
    setor: Optional[str] = None
    alert_label: Optional[str] = None
    operator_name: Optional[str] = None
    exemplo_transcricao: Optional[str] = None
    corrections: list[AuditCriterionCorrection]


@router.get("")
def api_list_feedback(tipo: Optional[str] = None, setor: Optional[str] = None, ativo: Optional[bool] = None, _user: dict = Depends(require_authenticated_user)):
    """Lista feedbacks, com filtros opcionais por `tipo`, `setor` e ativos (`ativo`).

    Retorna `{"items": [...]}`. Requer usuario autenticado.
    """
    return {"items": list_feedback(tipo=tipo, setor=setor, ativo_only=bool(ativo))}


@router.post("/audit-corrections", status_code=201)
def api_create_audit_corrections(body: AuditCorrectionsCreate, _user: dict = Depends(require_authenticated_user)):
    """Converte correcoes manuais de uma auditoria em feedbacks de tipo 'avaliacao'.

    Recebe a lista `body.corrections` (cada item: criterio + status anterior da IA +
    status corrigido pelo auditor) e cria um feedback por correcao valida, montando
    automaticamente os textos de situacao/correcao/justificativa. Itens sem
    `criterion_id` ou `corrected_status` sao ignorados. Grava no banco; nao envia
    e-mail. Retorna `{"created": N, "ids": [...]}`.
    """
    username = _user.get("username", "admin")
    created_ids: list[int] = []

    for correction in body.corrections:
        if not correction.criterion_id or not correction.corrected_status:
            continue

        situation_parts = [
            f"A IA avaliou o criterio '{correction.label}' como {correction.previous_status or 'nao informado'}.",
        ]
        if correction.previous_comment:
            situation_parts.append(f"Comentario original: {correction.previous_comment}")
        if body.alert_label:
            situation_parts.append(f"Alerta: {body.alert_label}")

        correction_parts = [
            f"O auditor corrigiu o criterio '{correction.label}' para {correction.corrected_status}.",
        ]
        if correction.corrected_comment:
            correction_parts.append(f"Comentario correto: {correction.corrected_comment}")

        new_item = add_feedback(
            tipo="avaliacao",
            situacao=" ".join(situation_parts).strip(),
            correcao=" ".join(correction_parts).strip(),
            justificativa=(
                "Correcao manual aplicada por auditor humano durante a revisao da auditoria. "
                "Use esta correcao como referencia nas proximas avaliacoes do mesmo criterio."
            ),
            criado_por=username,
            setor=body.setor,
            criterio_id=correction.criterion_id,
            exemplo_transcricao=body.exemplo_transcricao,
        )
        if new_item.get("id"):
            created_ids.append(int(new_item["id"]))

    return {"created": len(created_ids), "ids": created_ids}


@router.get("/{feedback_id}")
def api_get_feedback(feedback_id: int, _user: dict = Depends(require_authenticated_user)):
    """Retorna um feedback pelo id. 404 se nao existir."""
    item = get_feedback_by_id(feedback_id)
    if not item:
        raise HTTPException(status_code=404, detail="Feedback não encontrado")
    return item


@router.post("", status_code=201)
def api_create_feedback(body: FeedbackCreate, _user: dict = Depends(require_authenticated_user)):
    """Cria um feedback avulso e dispara o e-mail de notificacao.

    `body.tipo` precisa estar em `VALID_TIPOS` (senao 422). Apos persistir, tenta
    enviar `send_new_feedback_email` de forma sincrona (falha no e-mail e apenas
    logada, nao quebra o request). Retorna o feedback criado.
    """
    if body.tipo not in VALID_TIPOS:
        raise HTTPException(status_code=422, detail=f"Tipo inválido. Válidos: {sorted(VALID_TIPOS)}")

    username = _user.get("username", "admin")

    new_feedback_item = add_feedback(
        tipo=body.tipo,
        situacao=body.situacao,
        correcao=body.correcao,
        justificativa=body.justificativa,
        criado_por=username,
        setor=body.setor,
        criterio_id=body.criterio_id,
        exemplo_transcricao=body.exemplo_transcricao,
    )

    # Cloud Run: CPU congela após a resposta, BackgroundTasks morrem.
    # Enviar e-mail de forma síncrona antes do return.
    if new_feedback_item:
        try:
            send_new_feedback_email(new_feedback_item)
        except Exception:
            import logging
            logging.getLogger(__name__).warning("Falha ao enviar email de feedback", exc_info=True)

    return new_feedback_item


@router.put("/{feedback_id}")
def api_update_feedback(feedback_id: int, body: FeedbackUpdate, _user: dict = Depends(require_authenticated_user)):
    """Atualiza campos de um feedback existente. 404 se nao existir.

    Retorna `{"updated": True}` em caso de sucesso.
    """
    updated = update_feedback(
        feedback_id,
        situacao=body.situacao,
        correcao=body.correcao,
        justificativa=body.justificativa,
        setor=body.setor,
        criterio_id=body.criterio_id,
        exemplo_transcricao=body.exemplo_transcricao,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Feedback não encontrado")
    return {"updated": True}


@router.patch("/{feedback_id}/toggle")
def api_toggle_feedback(feedback_id: int, _user: dict = Depends(require_authenticated_user)):
    """Inverte o flag `ativo` de um feedback (liga/desliga seu uso pela IA).

    Retorna o novo estado em `{"ativo": ...}`. 404 se nao existir.
    """
    new_state = toggle_feedback(feedback_id)
    if new_state is None:
        raise HTTPException(status_code=404, detail="Feedback não encontrado")
    return {"ativo": new_state}


@router.delete("/{feedback_id}")
def api_delete_feedback(feedback_id: int, _user: dict = Depends(require_authenticated_user)):
    """Remove um feedback pelo id. 404 se nao existir. Retorna `{"deleted": True}`."""
    if not delete_feedback(feedback_id):
        raise HTTPException(status_code=404, detail="Feedback não encontrado")
    return {"deleted": True}
