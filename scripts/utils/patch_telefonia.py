import os
import sys

filename = 'backend/routers/telefonia.py'
with open(filename, 'r', encoding='utf-8') as f:
    content = f.read()

import_statement = """from automation import load_classified_audio, _build_alert_from_classification
from core.audit import process_audit_with_ai"""

content = content.replace("from automation import load_classified_audio", import_statement)

endpoint = """
@router.post("/recordings/{input_hash}/audit")
async def auditar_instantaneamente_gravacao(
    input_hash: str,
    user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    \"\"\"Audita imediatamente uma gravacao da Huawei (bypass triagem manual).\"\"\"
    item = _get_huawei_queue_item_or_404(input_hash)
    status = str(item.get("status") or "").strip()

    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        raise HTTPException(
            status_code=409,
            detail="Gravacao ja foi auditada.",
        )

    metadata = _queue_metadata(item)
    sector_id = str(metadata.get("setor") or "").strip()
    alert_id = str(metadata.get("alerta_previsto") or "").strip()
    operator_name = str(metadata.get("operador_nome") or "").strip()
    operator_id = str(metadata.get("operador_id") or "").strip()
    source_type = _recording_source_type(item)
    
    if not alert_id:
        raise HTTPException(status_code=400, detail="Alerta previsto nao encontrado no item.")
        
    try:
        from core.audit import process_audit_with_ai
        from automation import _build_alert_from_classification
        media_bytes, mime_type, filename = load_classified_audio(item)
    except Exception as e:
        logger.error(f"Erro ao carregar audio para auditoria instantanea: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    try:
        alert = _build_alert_from_classification(sector_id, alert_id)
        result, result_hash, from_cache = await process_audit_with_ai(
            media_bytes,
            mime_type,
            alert,
            operator_name,
            operator_id,
            sector_id,
        )
    except Exception as e:
        logger.error(f"Falha na IA durante auditoria instantanea: {e}")
        raise HTTPException(status_code=500, detail=f"Erro na analise de IA: {e}")

    audit_id = database.persist_audit_artifacts(
        result,
        from_cache=from_cache,
        input_hash=result_hash or input_hash,
        alert_id=alert_id,
        alert_label=alert.label,
        operator_id=operator_id,
        sector_id=sector_id,
        audio_bytes=media_bytes if source_type == 'audio' else None,
        audio_mime_type=mime_type if source_type == 'audio' else None,
        original_filename=filename,
        status="awaiting_pair",
    )
    if not audit_id:
        raise HTTPException(status_code=500, detail="Falha ao salvar a auditoria.")

    # Marca fila como auditada
    database.atualizar_status_fila_revisao_classificacao(
        input_hash,
        status=REVIEW_QUEUE_STATUS_AUDITED,
        motivos_revisao_append=["auditada_instantaneamente"],
        metadata_merge={
            "telefonia_audit_requested_at": _utc_now_iso(),
            "telefonia_audit_requested_by": user.get("username") or user.get("sub") or "admin",
            "audit_id": audit_id,
        },
    )

    return {
        "success": True,
        "message": "Gravacao auditada com sucesso.",
        "audit_id": audit_id,
    }

"""

if "@router.post(\"/recordings/{input_hash}/audit\")" not in content:
    idx = content.find("@router.post(\"/cron/sync\")")
    if idx != -1:
        content = content[:idx] + endpoint + content[idx:]

with open(filename, 'w', encoding='utf-8') as f:
    f.write(content)
