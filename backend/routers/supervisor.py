"""Router do Portal do Supervisor/Gestor da auditoria.

Atende o portal usado por supervisores (e admins) para revisar as auditorias dos
seus operadores. Principais grupos de endpoints:

- Exportações de relatório por operador/mês: gestores (Excel e PDF) e planejamento
  (Excel e PDF), além do report de config de export.
- Decisão do supervisor sobre uma auditoria: aprovar ou contestar.
- Listagem do painel (``GET /api/gestores/auditorias``) com KPIs e injeção de
  "Ligação não encontrada" para dar visibilidade total dos operadores ativos.
- Detalhe de auditoria, feedback do gestor (salvar/ler) e serviço do HTML do portal.

Autorização: supervisores só enxergam/agem sobre auditorias do seu próprio nome
(via ``get_supervisor_audit_for_user`` / ``resolve_user_supervisor_name``); admins
veem tudo. Regra de negócio: no painel, no máximo 2 auditorias por operador
(``MAX_AUDITS_PER_OPERATOR_SUPERVISOR``).

CUSTO DE API: nenhum direto. As exportações geram Excel/PDF em CPU e leem o banco;
não há chamadas pagas a Azure neste módulo.
"""

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from db.domain_constants import (
    AUDIT_PASS_THRESHOLD,
    AUDIT_STATUS_APPROVED,
    AUDIT_STATUS_CONTESTATION_ACCEPTED,
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    AUDIT_STATUS_PENDING_APPROVAL,
)
import db.database as database
from repositories import audits
from repositories import operators
from repositories.analytics_quality import get_indicators_by_supervisor
from routers.auth import (
    _normalize_auth_lookup,
    require_authenticated_user,
    require_supervisor_or_admin,
)
from routers.common import (
    _safe_filename,
    estimate_stream_size,
    get_supervisor_audit_for_user,
    resolve_user_supervisor_name,
    safe_log_report_export,
)
from schemas import AuditResult


router = APIRouter(tags=["supervisor"])
APPROVAL_THRESHOLD_PERCENT = AUDIT_PASS_THRESHOLD * 100


from typing import Any

class AuditActionRequest(BaseModel):
    """Corpo das ações do supervisor sobre uma auditoria (aprovar/contestar).

    ``reason`` é o motivo (obrigatório só na contestação) e ``contested_criteria``
    é a lista opcional de critérios contestados.
    """

    reason: str = None
    contested_criteria: list[Any] | None = None


class GestorFeedbackRequest(BaseModel):
    """Corpo do feedback do gestor sobre uma auditoria.

    Inclui o id da auditoria, o nome do gestor, o texto do feedback e os pontos de
    melhoria.
    """

    audit_id: int
    gestor_nome: str
    feedback_texto: str
    pontos_melhoria: str


# Supervisores revisam no maximo 2 auditorias por operador (regra de negocio).
# Este limite se aplica ao painel do supervisor; a auditoria individual nao tem este limite.
MAX_AUDITS_PER_OPERATOR_SUPERVISOR = 2


# Status exibidos no painel do supervisor — awaiting_pair fica oculto ate parear.
_SUPERVISOR_VISIBLE_STATUSES = [
    AUDIT_STATUS_PENDING_APPROVAL,
    AUDIT_STATUS_APPROVED,
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    AUDIT_STATUS_CONTESTATION_ACCEPTED,
]


@router.post("/api/export/gestores")
def export_gestores(
    result: AuditResult,
    audit_id: int | None = None,
    alert_id: str = None,
    alert_label: str = None,
    sector_id: str = None,
    user: dict = Depends(require_authenticated_user),
):
    """Exporta a "consulta de gestores" de uma auditoria em Excel (download).

    Se ``audit_id`` for informado, usa a auditoria persistida (após checar o acesso
    do supervisor) e o feedback do gestor; senão monta o relatório a partir do
    ``AuditResult`` recebido no corpo. Gera o ``.xlsx`` via ``generate_gestores_excel``,
    registra a exportação na trilha (best-effort) e devolve como streaming.

    Efeito: leitura no banco e log da exportação. Sem custo de API paga.
    """
    from core.export_gestores import generate_gestores_excel

    stored_audit = None
    if audit_id is not None and audit_id > 0:
        get_supervisor_audit_for_user(user, audit_id)
        stored_audit = audits.get_audit_by_id(database.get_connection, audit_id)
        if stored_audit is None:
            raise HTTPException(status_code=404, detail="Auditoria não encontrada.")

    feedback = database.get_gestor_feedback(audit_id) if audit_id is not None else None

    audit_data = {
        "timestamp": stored_audit["timestamp"] if stored_audit else (result.timestamp or ""),
        "operator_name": stored_audit["operator_name"] if stored_audit else (result.operatorName or ""),
        "operator_id": stored_audit["operator_id"] if stored_audit else (result.operatorId or ""),
        "score": stored_audit["score"] if stored_audit else result.score,
        "max_score": stored_audit["max_score"] if stored_audit else result.maxPossibleScore,
        "summary": stored_audit["summary"] if stored_audit else result.summary,
        "details": json.dumps(
            stored_audit["details"] if stored_audit else [detail.model_dump() for detail in result.details]
        ),
        "alert_id": stored_audit["alert_id"] if stored_audit else alert_id,
        "alert_label": stored_audit["alert_label"] if stored_audit else alert_label,
        "sector_id": stored_audit["sector_id"] if stored_audit else sector_id,
        "source_type": stored_audit["source_type"] if stored_audit else result.source_type,
        "transcription_text": "\n".join(
            f"[{seg.get('start', '')}] {seg.get('text', '')}"
            for seg in (stored_audit["transcription"] if stored_audit else [segment.model_dump() for segment in (result.transcription or [])])
            if seg.get("text")
        ),
        "feedback": feedback,
    }

    excel_file = generate_gestores_excel([audit_data])
    effective_result = result
    if stored_audit is not None:
        effective_result = AuditResult(
            score=stored_audit["score"],
            maxPossibleScore=stored_audit["max_score"],
            summary=stored_audit["summary"],
            ai_feedback=stored_audit.get("ai_feedback"),
            details=stored_audit["details"],
            transcription=stored_audit["transcription"],
            operatorId=stored_audit["operator_id"],
            operatorName=stored_audit["operator_name"],
            timestamp=stored_audit["timestamp"],
            source_type=stored_audit["source_type"],
            audit_scope=stored_audit["audit_scope"],
            audio_quality=stored_audit.get("audio_quality"),
        )
    filename = f"consulta_gestores_{_safe_filename(effective_result.operatorName or 'audit')}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    safe_log_report_export(
        report_kind="gestores",
        file_format="xlsx",
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        user=user,
        result=effective_result,
        alert_id=audit_data["alert_id"],
        alert_label=audit_data["alert_label"],
        sector_id=audit_data["sector_id"],
        file_size_bytes=estimate_stream_size(excel_file),
        metadata={"export_source": "gestores_excel"},
    )
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/api/export/gestores/pdf")
def export_gestores_pdf(
    result: AuditResult,
    audit_id: int | None = None,
    alert_id: str = None,
    alert_label: str = None,
    sector_id: str = None,
    user: dict = Depends(require_authenticated_user),
):
    """Exporta a "consulta de gestores" de uma auditoria em PDF (download).

    Versão PDF de ``export_gestores``: usa a auditoria persistida quando ``audit_id``
    é dado (com checagem de acesso do supervisor) ou o ``AuditResult`` do corpo,
    gera o PDF via ``generate_gestores_pdf``, loga a exportação e devolve streaming.

    Efeito: leitura no banco e log da exportação. Sem custo de API paga.
    """
    from core.export_gestores_pdf import generate_gestores_pdf

    stored_audit = None
    if audit_id is not None and audit_id > 0:
        get_supervisor_audit_for_user(user, audit_id)
        stored_audit = audits.get_audit_by_id(database.get_connection, audit_id)
        if stored_audit is None:
            raise HTTPException(status_code=404, detail="Auditoria não encontrada.")

    audit_data = {
        "timestamp": stored_audit["timestamp"] if stored_audit else (result.timestamp or ""),
        "operator_name": stored_audit["operator_name"] if stored_audit else (result.operatorName or ""),
        "operator_id": stored_audit["operator_id"] if stored_audit else (result.operatorId or ""),
        "score": stored_audit["score"] if stored_audit else result.score,
        "max_score": stored_audit["max_score"] if stored_audit else result.maxPossibleScore,
        "summary": stored_audit["summary"] if stored_audit else result.summary,
        "details": json.dumps(
            stored_audit["details"] if stored_audit else [detail.model_dump() for detail in result.details]
        ),
        "alert_id": stored_audit["alert_id"] if stored_audit else alert_id,
        "alert_label": stored_audit["alert_label"] if stored_audit else alert_label,
        "sector_id": stored_audit["sector_id"] if stored_audit else sector_id,
        "source_type": stored_audit["source_type"] if stored_audit else result.source_type,
        "transcription": stored_audit["transcription"] if stored_audit else [segment.model_dump() for segment in (result.transcription or [])],
    }

    pdf_file = generate_gestores_pdf(audit_data)
    effective_result = result
    if stored_audit is not None:
        effective_result = AuditResult(
            score=stored_audit["score"],
            maxPossibleScore=stored_audit["max_score"],
            summary=stored_audit["summary"],
            ai_feedback=stored_audit.get("ai_feedback"),
            details=stored_audit["details"],
            transcription=stored_audit["transcription"],
            operatorId=stored_audit["operator_id"],
            operatorName=stored_audit["operator_name"],
            timestamp=stored_audit["timestamp"],
            source_type=stored_audit["source_type"],
            audit_scope=stored_audit["audit_scope"],
            audio_quality=stored_audit.get("audio_quality"),
        )
    filename = f"relatorio_gestores_{_safe_filename(effective_result.operatorName or 'audit')}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    safe_log_report_export(
        report_kind="gestores",
        file_format="pdf",
        filename=filename,
        media_type="application/pdf",
        user=user,
        result=effective_result,
        alert_id=audit_data["alert_id"],
        alert_label=audit_data["alert_label"],
        sector_id=audit_data["sector_id"],
        file_size_bytes=estimate_stream_size(pdf_file),
        metadata={"export_source": "gestores_pdf"},
    )
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers=headers,
    )


@router.get("/api/export/gestores/config")
def export_gestores_config(user: dict = Depends(require_authenticated_user)):
    """Retorna o relatório de configuração do export de gestores.

    Útil para diagnosticar como o export está parametrizado. Loga o acesso na
    trilha de exportações (best-effort). Retorna ``{"report": <texto>}``.
    """
    from core.export_gestores import get_export_config_report

    report = get_export_config_report()
    safe_log_report_export(
        report_kind="gestores_config",
        file_format="json",
        filename="export_config_gestores.json",
        media_type="application/json",
        user=user,
        file_size_bytes=len(report.encode("utf-8")),
        metadata={"report_length": len(report)},
    )
    return {"report": report}


@router.get("/api/export/planejamento")
def export_planejamento(
    month: int = None,
    year: int = None,
    sector_id: str = None,
    user: dict = Depends(require_authenticated_user),
):
    """Export consolidado mensal para o Planejamento.

    Dados brutos — não calcula quartil (regra do Planejamento).
    """
    from datetime import datetime
    from core.export_planejamento import generate_planejamento_excel

    if month is None:
        month = datetime.now().month
    if year is None:
        year = datetime.now().year

    excel_file = generate_planejamento_excel(
        database.get_connection, month, year, sector_id
    )
    mes_nome = f"{month:02d}"
    filename = f"fechamento_auditoria_{mes_nome}_{year}.xlsx"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    safe_log_report_export(
        report_kind="planejamento",
        file_format="xlsx",
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        user=user,
        file_size_bytes=estimate_stream_size(excel_file),
        metadata={"month": month, "year": year, "sector_id": sector_id},
    )
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.get("/api/export/planejamento/pdf")
def export_planejamento_pdf(
    month: int = None,
    year: int = None,
    sector_id: str = None,
    user: dict = Depends(require_authenticated_user),
):
    """Export consolidado mensal em PDF para o Planejamento."""
    from datetime import datetime
    from core.export_planejamento_pdf import generate_planejamento_pdf

    if month is None:
        month = datetime.now().month
    if year is None:
        year = datetime.now().year

    pdf_file = generate_planejamento_pdf(
        database.get_connection, month, year, sector_id
    )
    mes_nome = f"{month:02d}"
    filename = f"fechamento_auditoria_{mes_nome}_{year}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    safe_log_report_export(
        report_kind="planejamento_pdf",
        file_format="pdf",
        filename=filename,
        media_type="application/pdf",
        user=user,
        file_size_bytes=estimate_stream_size(pdf_file),
        metadata={"month": month, "year": year, "sector_id": sector_id},
    )
    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers=headers,
    )


@router.post("/api/gestores/auditorias/{audit_id}/approve")
def approve_audit(audit_id: int, user: dict = Depends(require_supervisor_or_admin)):
    """Aprova uma auditoria que está aguardando decisão do supervisor.

    Checa o acesso do supervisor e exige que o status seja
    ``pending_approval`` (senão HTTP 400). Muda o status para ``approved``. Erros
    de transição de status viram HTTP 400. Efeito: escrita no banco.
    """
    audit = get_supervisor_audit_for_user(user, audit_id)
    if audit.get("status") != AUDIT_STATUS_PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail="Somente auditorias aguardando decisao do supervisor podem ser aprovadas por esta rota.",
        )
    try:
        database.update_audit_status(audit_id, AUDIT_STATUS_APPROVED, None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "message": "Auditoria aprovada com sucesso."}


@router.post("/api/gestores/auditorias/{audit_id}/contest")
def contest_audit(
    audit_id: int,
    payload: AuditActionRequest,
    user: dict = Depends(require_supervisor_or_admin),
):
    """Abre uma contestação do supervisor sobre uma auditoria.

    Checa o acesso, exige ``reason`` não vazio (senão HTTP 400) e move a auditoria
    para ``contestation_pending_review`` (revisão técnica), serializando os
    ``contested_criteria`` em JSON. Erros de transição viram HTTP 400. Efeito:
    escrita no banco.
    """
    get_supervisor_audit_for_user(user, audit_id)
    if not payload.reason or not payload.reason.strip():
        raise HTTPException(status_code=400, detail="Motivo da contestação é obrigatório.")
    contested_json = json.dumps(payload.contested_criteria) if payload.contested_criteria else None
    try:
        database.update_audit_status(
            audit_id,
            AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
            payload.reason,
            contested_criteria=contested_json,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "message": "Contestação enviada para revisão técnica."}


@router.get("/api/gestores/auditorias")
def get_gestores_auditorias(
    limit: int = 500,
    skip: int = 0,
    month: int = None,
    year: int = None,
    sector_id: str = None,
    operator_name: str = None,
    supervisor: str = None,
    escala: str = None,
    user: dict = Depends(require_supervisor_or_admin),
):
    """Monta o painel do supervisor: auditorias visíveis + KPIs do período.

    Para supervisores, força o filtro pelo próprio nome (ignora o ``supervisor``
    da query); admins podem filtrar livremente. Pagina no banco com teto de
    ``MAX_AUDITS_PER_OPERATOR_SUPERVISOR`` (2) auditorias por operador (via
    ROW_NUMBER) e limita aos status visíveis (``_SUPERVISOR_VISIBLE_STATUSES``).

    Em seguida injeta linhas-fantasma "Ligação não encontrada" (ids negativos,
    ``is_missing=True``) para cada operador ATIVO/auditável que ainda não atingiu a
    cota de 2, garantindo visibilidade total no painel. Os KPIs (total, nota média
    ponderada, taxa de aprovação) vêm de funções analíticas independentes da
    paginação e contam apenas auditorias ``approved``.

    Efeito: várias leituras no banco. Retorna ``{"kpis": {...}, "auditorias": [...]}``.
    """
    effective_supervisor = supervisor

    if user["role"] == "supervisor":
        effective_supervisor = resolve_user_supervisor_name(user)

    # Paginação real no banco: o limite de 2 por operador aplica-se via
    # ROW_NUMBER() dentro de uma CTE, evitando os buracos fantasma do filtro Python.
    paginated_audits = database.get_audits_for_export(
        month=month,
        year=year,
        supervisor=effective_supervisor,
        escala=escala,
        sector_id=sector_id,
        operator_name=operator_name,
        statuses=_SUPERVISOR_VISIBLE_STATUSES,
        limit=limit,
        skip=skip,
        max_per_operator=MAX_AUDITS_PER_OPERATOR_SUPERVISOR,
    )

    # Inject missing audits (Ligação não encontrada) to ensure full visibility
    from repositories.operators import list_colaboradores
    from datetime import datetime

    ops = list_colaboradores(database.get_connection)
    
    if effective_supervisor:
        normalized_supervisor = effective_supervisor.strip().lower()
        ops = [op for op in ops if (op.get("supervisor") or "").strip().lower() == normalized_supervisor]
    if escala:
        normalized_escala = escala.strip().lower()
        ops = [op for op in ops if (op.get("escala") or "").strip().lower() == normalized_escala]
    if operator_name:
        normalized_op = operator_name.strip().lower()
        ops = [op for op in ops if normalized_op in (op.get("nome") or "").strip().lower()]
        
    active_ops = [op for op in ops if str(op.get("status") or "").upper() == "ATIVO" and op.get("auditavel", 1)]

    audit_counts = {}
    for a in paginated_audits:
        name = (a.get("operator_name") or "").strip().lower()
        audit_counts[name] = audit_counts.get(name, 0) + 1

    missing_audits = []
    dummy_id_counter = -1
    for op in active_ops:
        name = (op.get("nome") or "").strip().lower()
        count = audit_counts.get(name, 0)
        while count < MAX_AUDITS_PER_OPERATOR_SUPERVISOR:
            missing_audits.append({
                "id": dummy_id_counter,
                "operator_name": op.get("nome"),
                "operator_id": op.get("id_telefonia"),
                "supervisor": op.get("supervisor"),
                "escala": op.get("escala"),
                "status": "approved", # Mostra no painel
                "summary": "Ligação não encontrada",
                "score": 0.0,
                "max_score": 0.0,
                "timestamp": datetime.now().isoformat(),
                "audit_date": datetime.now().isoformat(),
                "details": [],
                "transcription": [],
                "is_missing": True,
                "alert_label": "N/A",
                "sector_id": sector_id or "N/A"
            })
            dummy_id_counter -= 1
            count += 1

    paginated_audits.extend(missing_audits)

    # KPIs vêm da função analítica global — independem da paginação e só contam
    # auditorias já aprovadas (status = approved), que é a massa oficial do painel.
    supervisor_indicators = get_indicators_by_supervisor(
        database.get_connection,
        month=month,
        year=year,
        sector_id=sector_id,
    )
    if effective_supervisor:
        normalized_supervisor = effective_supervisor.strip().lower()
        supervisor_indicators = [
            row for row in supervisor_indicators
            if str(row.get("supervisor") or "").strip().lower() == normalized_supervisor
        ]

    total_auditorias = sum(int(row.get("total_auditorias") or 0) for row in supervisor_indicators)
    if total_auditorias > 0:
        weighted_sum = sum(
            float(row.get("media_percentual") or 0) * int(row.get("total_auditorias") or 0)
            for row in supervisor_indicators
        )
        nota_media = round(weighted_sum / total_auditorias, 2)
    else:
        nota_media = 0.0

    # Aprovações: precisamos recalcular a partir dos registros aprovados reais,
    # já que os indicadores agregados não expõem o corte aprovado/reprovado.
    approved_audits = database.get_audits_for_export(
        month=month,
        year=year,
        supervisor=effective_supervisor,
        escala=escala,
        sector_id=sector_id,
        operator_name=operator_name,
        statuses=[AUDIT_STATUS_APPROVED],
    )
    approved_scores = [
        (float(audit.get("score") or 0.0) / float(audit.get("max_score") or 1.0)) * 100
        for audit in approved_audits
        if audit.get("max_score") is not None and float(audit.get("max_score") or 0.0) > 0
    ]
    total_aprovadas = sum(1 for score in approved_scores if score >= APPROVAL_THRESHOLD_PERCENT)
    total_reprovadas = len(approved_scores) - total_aprovadas
    taxa_aprovacao = round(total_aprovadas / len(approved_scores) * 100, 2) if approved_scores else 0.0

    kpis = {
        "total_auditorias": total_auditorias,
        "nota_media": nota_media,
        "taxa_aprovacao": taxa_aprovacao,
        "total_aprovadas": total_aprovadas,
        "total_reprovadas": total_reprovadas,
    }

    return {
        "kpis": kpis,
        "auditorias": paginated_audits,
    }


@router.get("/api/gestores/auditorias/{audit_id}")
def get_gestor_auditoria_detail(audit_id: int, user: dict = Depends(require_supervisor_or_admin)):
    """Detalha uma auditoria para o painel do gestor (com feedback e áudio).

    Checa o acesso do supervisor, carrega a auditoria (HTTP 404 se inexistente),
    anexa o feedback do gestor e resolve o áudio (recuperando da fila de
    classificação se não estiver no storage), expondo ``audio_available`` e
    ``audio_url``. Efeito: leitura no banco (e possível recuperação de mídia).
    """
    get_supervisor_audit_for_user(user, audit_id)
    audit = audits.get_audit_by_id(database.get_connection, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Auditoria não encontrada.")

    audit["feedback"] = database.get_gestor_feedback(audit_id)
    media_record = database.get_audit_media_record(audit_id)
    if not (media_record and media_record.get("audio_storage_path")):
        media_record = database.recover_audit_audio_from_classified_queue(audit_id, audit, media_record)
    audit["audio_available"] = bool(media_record and media_record.get("audio_storage_path"))
    audit["audio_url"] = f"/api/audit/{audit_id}/audio" if audit.get("audio_available") else None
    return audit


@router.post("/api/gestores/feedback")
def save_feedback(req: GestorFeedbackRequest, user: dict = Depends(require_supervisor_or_admin)):
    """Salva o feedback do gestor para uma auditoria.

    Checa o acesso do supervisor à auditoria e persiste nome/feedback/pontos de
    melhoria. HTTP 500 se a gravação falhar. Efeito: escrita no banco.
    """
    get_supervisor_audit_for_user(user, req.audit_id)
    success = database.save_gestor_feedback(
        req.audit_id,
        req.gestor_nome,
        req.feedback_texto,
        req.pontos_melhoria,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Erro ao salvar o feedback no banco de dados.")
    return {"status": "success", "message": "Feedback salvo com sucesso."}


@router.get("/api/gestores/feedback/{audit_id}")
def get_feedback(audit_id: int, user: dict = Depends(require_supervisor_or_admin)):
    """Lê o feedback do gestor de uma auditoria.

    Checa o acesso do supervisor; HTTP 404 se não houver feedback. Efeito: leitura
    no banco.
    """
    get_supervisor_audit_for_user(user, audit_id)
    feedback = database.get_gestor_feedback(audit_id)
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback não encontrado.")
    return feedback


@router.get("/gestores")
def serve_gestores_portal():
    """Serve o HTML estático do portal dos gestores.

    Lê ``gestores_portal.html`` do diretório do backend e devolve como HTML. HTTP
    404 se o arquivo não existir. Rota pública (sem dependência de auth). Efeito:
    leitura de arquivo no disco.
    """
    portal_path = os.path.join(os.path.dirname(__file__), "..", "gestores_portal.html")
    portal_path = os.path.abspath(portal_path)
    if not os.path.exists(portal_path):
        raise HTTPException(status_code=404, detail="Portal dos gestores não encontrado.")
    with open(portal_path, "r", encoding="utf-8") as file_handle:
        return HTMLResponse(content=file_handle.read())


@router.get("/api/rh/supervisores")
def get_rh_supervisores(user: dict = Depends(require_supervisor_or_admin)):
    """Retorna o mapa supervisor -> escalas a partir do cadastro de RH.

    Para supervisores, filtra o retorno apenas ao seu próprio nome (lookup
    normalizado); admins recebem todos. Efeito: leitura no banco.
    """
    all_data = operators.get_supervisores_e_escalas(database.get_connection)

    if user["role"] == "supervisor":
        supervisor_name = resolve_user_supervisor_name(user)
        return {
            name: shifts
            for name, shifts in all_data.items()
            if _normalize_auth_lookup(name) == _normalize_auth_lookup(supervisor_name)
        }
    return all_data
