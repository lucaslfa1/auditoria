"""Fase 2 — Router admin para `sector_aliases`.

CRUD completo + audit-log + cache invalidate. Mesmo padrao de autenticacao e
contrato JSON da Fase 1.1/1.3 (admin_criteria).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import db.database as database
from repositories import sector_aliases as sa_repo
from routers.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin_sector_aliases"])


_VALID_PATTERN_TYPES = {
    "setor_exact",
    "setor_startswith",
    "setor_contains",
    "escala_contains",
    "supervisor_contains",
    "organizacao_contains",
    "organizacao_startswith",
}


def _username(user: dict) -> str:
    return str(user.get("username") or "admin")


class AliasCreate(BaseModel):
    pattern_type: str
    pattern_value: str
    canonical_sector_id: str
    priority: int = 100
    descricao: Optional[str] = None
    ativo: bool = True
    motivo: Optional[str] = None


class AliasUpdate(BaseModel):
    pattern_type: Optional[str] = None
    pattern_value: Optional[str] = None
    canonical_sector_id: Optional[str] = None
    priority: Optional[int] = None
    descricao: Optional[str] = None
    ativo: Optional[bool] = None
    motivo: Optional[str] = None


@router.get("/api/admin/sector-aliases")
def admin_list_sector_aliases(_user: dict = Depends(require_admin)):
    """Lista todas as regras de apelido de setor cadastradas. Somente admin."""
    return sa_repo.list_aliases(database.get_connection)


@router.post("/api/admin/sector-aliases")
def admin_create_sector_alias(req: AliasCreate, user: dict = Depends(require_admin)):
    """Cria uma regra de apelido (mapeia padrao -> setor canonico).

    Valida `pattern_type` contra `_VALID_PATTERN_TYPES` e exige `pattern_value` e
    `canonical_sector_id` nao-vazios; senao retorna 400. `priority` ordena a aplicacao
    das regras (o repositorio carrega/avalia por priority DESC, id ASC — maior
    prioridade vence). Retorna o id criado; 400 em conflito/dado invalido.
    """
    if req.pattern_type not in _VALID_PATTERN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"pattern_type invalido. Use um de: {sorted(_VALID_PATTERN_TYPES)}",
        )
    if not req.pattern_value.strip():
        raise HTTPException(status_code=400, detail="pattern_value e obrigatorio.")
    if not req.canonical_sector_id.strip():
        raise HTTPException(status_code=400, detail="canonical_sector_id e obrigatorio.")
    try:
        new_id = sa_repo.create_alias(
            database.get_connection,
            pattern_type=req.pattern_type,
            pattern_value=req.pattern_value,
            canonical_sector_id=req.canonical_sector_id,
            priority=req.priority,
            descricao=req.descricao,
            ativo=req.ativo,
            alterado_por=_username(user),
            motivo=req.motivo,
        )
        if new_id is None:
            raise HTTPException(status_code=400, detail="Falha ao criar alias (motivo logado).")
        return {"status": "created", "id": new_id}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro ao criar sector_alias: %s", exc)
        raise HTTPException(status_code=400, detail="Conflito ou dado invalido.")


@router.put("/api/admin/sector-aliases/{alias_id}")
def admin_update_sector_alias(
    alias_id: int,
    req: AliasUpdate,
    user: dict = Depends(require_admin),
):
    """Atualiza parcialmente uma regra de apelido (campos None sao ignorados).

    Se `pattern_type` for informado, valida contra `_VALID_PATTERN_TYPES` (400 se
    invalido). Retorna 404 se o alias nao existir. Registra autor/motivo no audit log.
    """
    if req.pattern_type is not None and req.pattern_type not in _VALID_PATTERN_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"pattern_type invalido. Use um de: {sorted(_VALID_PATTERN_TYPES)}",
        )
    ok = sa_repo.update_alias(
        database.get_connection,
        alias_id,
        pattern_type=req.pattern_type,
        pattern_value=req.pattern_value,
        canonical_sector_id=req.canonical_sector_id,
        priority=req.priority,
        descricao=req.descricao,
        ativo=req.ativo,
        alterado_por=_username(user),
        motivo=req.motivo,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Alias nao encontrado.")
    return {"status": "updated", "id": alias_id}


@router.delete("/api/admin/sector-aliases/{alias_id}")
def admin_delete_sector_alias(
    alias_id: int,
    motivo: Optional[str] = Query(default=None),
    user: dict = Depends(require_admin),
):
    """Remove uma regra de apelido. `motivo` (query) vai pro audit log.

    Retorna 404 se o alias nao existir.
    """
    ok = sa_repo.delete_alias(
        database.get_connection,
        alias_id,
        alterado_por=_username(user),
        motivo=motivo,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Alias nao encontrado.")
    return {"status": "deleted", "id": alias_id}


@router.get("/api/admin/sector-aliases/audit-log")
def admin_list_sector_aliases_audit_log(
    entity_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _user: dict = Depends(require_admin),
):
    """Lista o historico de mudancas das regras de apelido (mais recentes primeiro).

    `entity_id` opcional filtra o historico de um alias especifico; `limit` entre 1 e
    500 (default 50).
    """
    return sa_repo.list_audit_log(
        database.get_connection,
        entity_id=entity_id,
        limit=limit,
    )


@router.post("/api/admin/sector-aliases/cache/invalidate")
def admin_invalidate_sector_aliases_cache(_user: dict = Depends(require_admin)):
    """Invalida o cache em memoria das regras de apelido.

    Forca a proxima resolucao de setor a reler do banco. Util apos seed externo ou
    quando a mutacao ocorreu em outro pod (o cache vive por processo).
    """
    sa_repo.clear_cache()
    return {"status": "invalidated", "caches": ["sector_aliases._rules_cache"]}
