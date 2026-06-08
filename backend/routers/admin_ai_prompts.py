import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Body
from db.database import get_connection
from routers.auth import require_admin
from repositories.ai_prompts import (
    get_prompt,
    list_prompts,
    update_prompt,
    list_audit_log,
    restore_from_audit,
    invalidate_ai_prompts_cache
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/ai-prompts", tags=["Admin", "AI Prompts"])


@router.get("", response_model=Dict[str, Any])
def get_all_prompts(
    admin: dict = Depends(require_admin),
):
    """
    Retorna a lista estruturada de todos os prompts configurados.
    """
    try:
        return list_prompts(get_connection)
    except Exception as e:
        logger.exception("Erro ao listar ai_prompts")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audit-log")
def get_global_audit_log(
    limit: int = 50,
    offset: int = 0,
    entity_id: Optional[str] = None,
    admin: dict = Depends(require_admin),
):
    """
    Retorna o log de auditoria global das alterações nos ai_prompts.
    """
    try:
        return list_audit_log(get_connection, limit, offset, entity_id)
    except Exception as e:
        logger.exception("Erro ao buscar audit log global de ai_prompts")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{chave:path}")
def get_prompt_by_key(
    chave: str,
    admin: dict = Depends(require_admin),
):
    """
    Retorna o valor de um ai_prompt específico via dot-path (ex: audit_system.regra_senha).
    """
    val = get_prompt(get_connection, chave)
    if val is None:
        raise HTTPException(status_code=404, detail="Prompt não encontrado.")
    return {"chave": chave, "valor": val}


@router.put("/{chave:path}")
def put_prompt(
    chave: str,
    valor: Any = Body(...),
    motivo: str = Body(..., embed=True),
    admin: dict = Depends(require_admin),
):
    """
    Atualiza um ai_prompt no banco de dados e registra a auditoria.
    O valor pode ser uma string simples ou um JSON (dict/list).
    """
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=400, detail="Motivo da alteracao e obrigatorio.")
        
    sucesso = update_prompt(
        get_connection=get_connection,
        chave=chave,
        valor=valor,
        alterado_por=admin["username"],
        motivo=motivo.strip(),
        origem="api",
    )
    
    if not sucesso:
        raise HTTPException(status_code=500, detail="Erro ao atualizar o ai_prompt.")
        
    return {"status": "ok", "chave": chave}


@router.post("/restore-from-audit/{audit_id}")
def restore_prompt_audit(
    audit_id: int,
    motivo: str = Body(..., embed=True),
    admin: dict = Depends(require_admin),
):
    """
    Restaura um ai_prompt ao estado que estava ANTES da alteração registrada neste log de auditoria.
    """
    if not motivo or not motivo.strip():
        raise HTTPException(status_code=400, detail="Motivo do restore e obrigatorio.")
        
    sucesso = restore_from_audit(
        get_connection=get_connection,
        audit_id=audit_id,
        alterado_por=admin["username"],
        motivo=motivo.strip(),
    )
    
    if not sucesso:
        raise HTTPException(status_code=400, detail="Nao foi possivel restaurar o ai_prompt (pode ter sido um log de criacao).")
        
    return {"status": "ok", "message": "Restore efetuado com sucesso."}


@router.post("/invalidate-cache")
def invalidate_cache(
    admin: dict = Depends(require_admin),
):
    """
    Invalida o cache local dos ai_prompts forçando uma leitura do banco de dados no próximo acesso.
    """
    invalidate_ai_prompts_cache()
    return {"status": "ok", "message": "Cache invalidado com sucesso."}
