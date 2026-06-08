from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.domain_constants import (
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    REVIEW_QUEUE_STATUS_PENDING,
)
import db.database as database
from repositories import audits, classification_review
from repositories import audits
from repositories.common import json_loads
from routers.auth import require_admin


router = APIRouter(tags=["review"])


class ContestationVerdictRequest(BaseModel):
    verdict: str
    defense: str
    updated_details: list[dict] | None = None


@router.get("/api/revisao/contestacoes")
def list_review_contestations(
    limit: int = 200,
    month: int = None,
    year: int = None,
    sector_id: str = None,
    supervisor: str = None,
    operator_name: str = None,
    _user: dict = Depends(require_admin),
):
    limit = max(1, min(limit, 500))
    export_audits = audits.get_audits_for_export(database.get_connection, 
        month=month,
        year=year,
        supervisor=supervisor,
        sector_id=sector_id,
        operator_name=operator_name,
        statuses=[AUDIT_STATUS_CONTESTATION_PENDING_REVIEW],
    )
    export_audits.sort(key=lambda audit: audit.get("timestamp", ""), reverse=True)
    limited = export_audits[:limit]
    for audit in limited:
        audit_id = audit.get("id")
        audit["audio_url"] = (
            f"/api/audit/{audit_id}/audio" if audit_id and audit.get("audio_available") else None
        )
    return {
        "total": len(export_audits),
        "contestacoes": limited,
    }


from typing import Optional

from fastapi.responses import JSONResponse

@router.get("/api/revisao/classificacao")
def list_review_classification_queue(
    limit: Optional[int] = None,
    status: str = REVIEW_QUEUE_STATUS_PENDING,
    sector_id: str = None,
    _user: dict = Depends(require_admin),
):
    try:
        return classification_review.listar_fila_revisao_classificacao(database.get_connection, limit=limit, status=status, sector_id=sector_id)
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={"error": str(e), "trace": traceback.format_exc()})


@router.delete("/api/revisao/classificacao/pendentes")
def clear_pending_classification_queue(_user: dict = Depends(require_admin)):
    """Limpa todas as ligações retidas na fila de triagem manual."""
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        
        # Pega as hashes e os IDs do Huawei para apagar em lote
        from db.domain_constants import REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES
        cursor.execute(
            """
            SELECT input_hash, metadata_json 
            FROM fila_revisao_classificacao 
            WHERE status = ANY(%s)
            """,
            (list(REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES),)
        )
        rows = cursor.fetchall()
        
        hashes_to_delete = []
        huawei_ids_to_delete = []
        
        for row in rows:
            input_hash = row["input_hash"]
            raw_meta = row["metadata_json"]
            meta = json_loads(raw_meta, {})
            if not isinstance(meta, dict):
                meta = {}

            if meta.get("archived"):
                continue

            # Na fila de Triagem (Limpar Pendentes), não queremos apagar as ligações 
            # que vieram da Telefonia e que ainda NÃO foram enviadas para a IA,
            # EXCETO se o usuário mandou manualmente para a Triagem.
            is_huawei = str(meta.get("origem") or "").lower() == "huawei_sync"
            is_manual = meta.get("is_manual") is True
            classification_done = meta.get("classification_status") == "done"
            
            if is_huawei and not classification_done and not is_manual:
                continue

            hashes_to_delete.append(input_hash)
            if meta.get("huawei_call_id"):
                huawei_ids_to_delete.append(str(meta.get("huawei_call_id")))
                
        if hashes_to_delete:
            cursor.execute(
                "DELETE FROM fila_revisao_classificacao WHERE input_hash = ANY(%s)",
                (hashes_to_delete,)
            )
            
        if huawei_ids_to_delete:
            cursor.execute(
                "DELETE FROM huawei_sync_logs WHERE call_id = ANY(%s)",
                (huawei_ids_to_delete,)
            )
            
        conn.commit()
        return {"status": "ok", "message": f"{len(hashes_to_delete)} itens removidos da fila de triagem com sucesso.", "deleted": len(hashes_to_delete)}
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Falha ao remover gravações pendentes: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao limpar gravações pendentes.")
    finally:
        conn.close()


@router.get("/api/revisao/auditorias/{audit_id}")
def get_review_audit_detail(audit_id: int, _user: dict = Depends(require_admin)):
    audit = audits.get_audit_by_id(database.get_connection, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Auditoria não encontrada.")
    media_record = audits.get_audit_media_record(database.get_connection, audit_id)
    if not (media_record and media_record.get("audio_storage_path")):
        media_record = database.recover_audit_audio_from_classified_queue(audit_id, audit, media_record)
    audit["audio_available"] = bool(media_record and media_record.get("audio_storage_path"))
    audit["audio_url"] = f"/api/audit/{audit_id}/audio" if audit.get("audio_available") else None
    return audit


@router.post("/api/revisao/auditorias/{audit_id}/veredito")
def finalize_review_contestation(
    audit_id: int,
    payload: ContestationVerdictRequest,
    user: dict = Depends(require_admin),
):
    try:
        result = audits.finalize_contestation_review(database.get_connection, 
            audit_id,
            verdict=payload.verdict,
            defense=payload.defense,
            reviewed_by=user.get("username") or "Auditoria",
            updated_details=payload.updated_details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "success": True,
        "message": "Veredito técnico registrado com sucesso.",
        **result,
    }
