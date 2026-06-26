"""Router admin do catalogo de criterios de auditoria (setores/alertas/criterios).

CRUD completo sobre as tres tabelas que definem o que a IA avalia:
`audit_sectors`, `audit_alerts` e `audit_criteria`, mais o log de auditoria das
mudancas (Fase 1.1) e a invalidacao do cache do catalogo (Fase 1.2).

Sem custo de API: todas as rotas apenas leem/gravam no banco e mexem em caches em
memoria. O custo de Azure OpenAI ocorre depois, quando o pipeline de auditoria usa
este catalogo para montar o prompt.

Toda mutacao chama `_invalidate_catalog_cache()` para que a proxima auditoria use os
valores atualizados sem precisar reiniciar o processo. As rotas de mutacao exigem
perfil admin (`require_admin`); a unica excecao e `/api/criteria/export`, sem
dependencia de auth, que devolve o catalogo no formato legado do `auditCriteria.json`.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import db.database as database

logger = logging.getLogger(__name__)
from repositories.admin_criteria import (
    get_sectors,
    get_alerts,
    get_criteria,
    get_export_format,
    create_sector,
    delete_sector,
    get_sector_members,
    rename_sector_with_cascade,
    create_alert,
    update_alert,
    delete_alert,
    create_criterion,
    update_criterion,
    delete_criterion,
    list_audit_log,
    AlertWeightBudgetExceeded,
)
from routers.auth import require_admin, require_authenticated_user

router = APIRouter(tags=["admin_criteria"])


def _username(user: dict) -> str:
    return str(user.get("username") or "admin")


def _invalidate_catalog_cache() -> None:
    """Invalida o lru_cache do catalogo apos qualquer mutacao.

    Limitacao conhecida: lru_cache vive por processo, entao em Cloud Run multi-pod
    so o pod que recebeu a request fica fresh. Na pratica o catalogo e pequeno e
    consultado raramente — proxima fase pode mover pra leitura sem cache.
    """
    try:
        from core.classification import clear_classification_caches
        clear_classification_caches()
    except Exception:
        logger.exception("Falha ao invalidar cache do catalogo (mutacao DB ja persistiu)")


# Models

class SectorCreate(BaseModel):
    id: str  # e.g 'transferencia'
    label: str
    description: Optional[str] = None
    motivo: Optional[str] = None

class SectorUpdate(BaseModel):
    label: str
    description: Optional[str] = None
    motivo: Optional[str] = None

class SectorRename(BaseModel):
    new_label: str
    description: Optional[str] = None
    cascade: bool = True  # propaga o novo nome para os colaboradores vinculados
    motivo: Optional[str] = None

class AlertCreate(BaseModel):
    sector_id: str
    original_id: Optional[str] = None  # like '4.1.1'
    label: str
    context: Optional[str] = None
    pop_ref: Optional[str] = None
    expected_direction: Optional[str] = None
    motivo: Optional[str] = None

class AlertUpdate(BaseModel):
    label: str
    context: Optional[str] = None
    pop_ref: Optional[str] = None
    expected_direction: Optional[str] = None
    motivo: Optional[str] = None

class CriterionCreate(BaseModel):
    alert_id: str
    chave: str
    label: str
    weight: float
    description: Optional[str] = None
    type: str = "boolean"
    deflator: float = 0
    referencia: Optional[str] = None
    exemplo: Optional[str] = None
    motivo: Optional[str] = None

class CriterionUpdate(BaseModel):
    chave: str
    label: str
    weight: float
    description: Optional[str] = None
    type: str = "boolean"
    deflator: float = 0
    referencia: Optional[str] = None
    exemplo: Optional[str] = None
    motivo: Optional[str] = None


# Public / Read-for-All Authed Endpoint

@router.get("/api/criteria/export")
def export_criteria():
    """Exports criteria in the exact format of the original auditCriteria.json"""
    return get_export_format(database.get_connection)


# --- Sectors ---

@router.get("/api/admin/sectors")
def admin_get_sectors(_user: dict = Depends(require_admin)):
    """Lista todos os setores cadastrados em `audit_sectors`. Somente admin."""
    return get_sectors(database.get_connection)

@router.post("/api/admin/sectors")
def admin_create_sector(req: SectorCreate, user: dict = Depends(require_admin)):
    """Cria um setor novo e invalida o cache do catalogo.

    `req.id` e o id interno fixo (ex.: 'transferencia') e `req.label` o rotulo
    exibido; ambos obrigatorios. Registra o autor (`user`) e o motivo no audit log.
    Retorna 400 se id/label vazios ou se o setor ja existir.
    """
    if not req.id.strip() or not req.label.strip():
         raise HTTPException(status_code=400, detail="ID e Label são obrigatórios.")
    try:
        create_sector(
            database.get_connection,
            req.id.strip(),
            req.label.strip(),
            req.description,
            alterado_por=_username(user),
            motivo=req.motivo or "",
        )
        _invalidate_catalog_cache()
        return {"status": "created", "id": req.id}
    except Exception as e:
        logger.error("Erro ao criar setor: %s", e)
        raise HTTPException(status_code=400, detail="Erro ao criar setor ou dado já existe.")

@router.put("/api/admin/sectors/{sector_id}")
def admin_update_sector(sector_id: str, req: SectorUpdate, user: dict = Depends(require_admin)):
    """Atualiza um setor e propaga o novo nome para colaboradores vinculados.

    Este endpoint e usado pela tela legada de criterios. Para evitar dois fluxos
    divergentes de edicao de setor, ele reaproveita a mesma cascata do `/rename`:
    muda o label/description, atualiza `colaboradores.setor` e garante o alias do
    novo nome para o mesmo `sector_id`.
    """
    if not req.label.strip():
        raise HTTPException(status_code=400, detail="Label é obrigatório.")
    result = rename_sector_with_cascade(
        database.get_connection,
        sector_id,
        req.label,
        req.description,
        cascade=True,
        alterado_por=_username(user),
        motivo=req.motivo or "",
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Setor não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "updated", "id": sector_id, **result}

@router.delete("/api/admin/sectors/{sector_id}")
def admin_delete_sector(
    sector_id: str,
    motivo: Optional[str] = Query(default=None),
    user: dict = Depends(require_admin),
):
    """Remove um setor e invalida o cache. `motivo` (query) vai pro audit log.

    Retorna 404 se o setor nao existir.
    """
    if not delete_sector(
        database.get_connection,
        sector_id,
        alterado_por=_username(user),
        motivo=motivo or "",
    ):
         raise HTTPException(status_code=404, detail="Setor não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "deleted", "id": sector_id}

@router.get("/api/admin/sectors/{sector_id}/members")
def admin_get_sector_members(sector_id: str, _user: dict = Depends(require_admin)):
    """Preview: colaboradores cujo setor resolve para `sector_id` (via apelidos).

    Usado pela UI para mostrar "N colaboradores serao renomeados" antes de confirmar
    a cascata de rename.
    """
    members = get_sector_members(database.get_connection, sector_id)
    return {"count": len(members), "colaboradores": members}

@router.post("/api/admin/sectors/{sector_id}/rename")
def admin_rename_sector(sector_id: str, req: SectorRename, user: dict = Depends(require_admin)):
    """Renomeia o rotulo do setor e (se `cascade`) propaga para os colaboradores
    vinculados. O `id` interno e as regras de auditoria nao mudam."""
    if not req.new_label.strip():
        raise HTTPException(status_code=400, detail="Novo rótulo é obrigatório.")
    result = rename_sector_with_cascade(
        database.get_connection,
        sector_id,
        req.new_label,
        req.description,
        cascade=req.cascade,
        alterado_por=_username(user),
        motivo=req.motivo or "",
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Setor não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "renamed", "id": sector_id, **result}


# --- Alerts ---

@router.get("/api/admin/alerts")
def admin_get_alerts(sector_id: Optional[str] = None, _user: dict = Depends(require_admin)):
    """Lista alertas, opcionalmente filtrados por `sector_id` (query). Somente admin."""
    return get_alerts(database.get_connection, sector_id=sector_id)

@router.post("/api/admin/alerts")
def admin_create_alert(req: AlertCreate, user: dict = Depends(require_admin)):
    """Cria um alerta dentro de um setor e invalida o cache do catalogo.

    `req.sector_id` e `req.label` sao obrigatorios; `original_id` (ex.: '4.1.1'),
    `pop_ref` e `expected_direction` sao opcionais. Retorna o id gerado. Erro 400 se
    campos obrigatorios faltarem ou o alerta ja existir.
    """
    if not req.sector_id.strip() or not req.label.strip():
        raise HTTPException(status_code=400, detail="Sector ID e Label são obrigatórios.")
    try:
        new_id = create_alert(
            database.get_connection,
            req.sector_id,
            req.label,
            req.context,
            req.original_id,
            alterado_por=_username(user),
            motivo=req.motivo or "",
            pop_ref=req.pop_ref,
            expected_direction=req.expected_direction,
        )
        _invalidate_catalog_cache()
        return {"status": "created", "id": new_id}
    except Exception as e:
         logger.error("Erro ao criar alerta: %s", e)
         raise HTTPException(status_code=400, detail="Erro ao criar alerta ou dado já existe.")

@router.put("/api/admin/alerts/{alert_id}")
def admin_update_alert(alert_id: str, req: AlertUpdate, user: dict = Depends(require_admin)):
    """Atualiza um alerta (label/context/pop_ref/expected_direction) e invalida o cache.

    `alert_id` pode conter caracteres especiais (ex.: '::'), entao deve vir
    url-encoded no path. Retorna 404 se o alerta nao existir.
    """
    # alert_id contains special characters perhaps (::) so it must be passed in body or url encoded
    if not update_alert(
        database.get_connection,
        alert_id,
        req.label,
        req.context,
        alterado_por=_username(user),
        motivo=req.motivo or "",
        pop_ref=req.pop_ref,
        expected_direction=req.expected_direction,
    ):
         raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "updated", "id": alert_id}

@router.delete("/api/admin/alerts/{alert_id}")
def admin_delete_alert(
    alert_id: str,
    motivo: Optional[str] = Query(default=None),
    user: dict = Depends(require_admin),
):
    """Remove um alerta e invalida o cache. `motivo` (query) vai pro audit log.

    Retorna 404 se o alerta nao existir.
    """
    if not delete_alert(
        database.get_connection,
        alert_id,
        alterado_por=_username(user),
        motivo=motivo or "",
    ):
         raise HTTPException(status_code=404, detail="Alerta não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "deleted", "id": alert_id}


# --- Criteria ---

@router.get("/api/admin/criteria")
def admin_get_criteria(alert_id: Optional[str] = None, _user: dict = Depends(require_admin)):
    """Lista criterios, opcionalmente filtrados por `alert_id` (query). Somente admin."""
    return get_criteria(database.get_connection, alert_id=alert_id)

@router.post("/api/admin/criteria")
def admin_create_criterion(req: CriterionCreate, user: dict = Depends(require_admin)):
    """Cria um criterio sob um alerta e invalida o cache do catalogo.

    Campos vindos de `CriterionCreate` (alert_id, chave, label, weight, type,
    deflator, etc.) sao repassados ao repositorio. Retorna o id gerado; erro 400 se
    o dado for invalido ou ja existir.
    """
    try:
        new_id = create_criterion(
            database.get_connection,
            req.alert_id,
            req.chave,
            req.label,
            req.weight,
            req.description,
            req.type,
            req.deflator,
            req.referencia,
            req.exemplo,
            alterado_por=_username(user),
            motivo=req.motivo or "",
        )
        _invalidate_catalog_cache()
        return {"status": "created", "id": new_id}
    except AlertWeightBudgetExceeded as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
         logger.error("Erro ao criar critério: %s", e)
         raise HTTPException(status_code=400, detail="Erro ao criar critério ou dado já existe.")

@router.put("/api/admin/criteria/{criterion_id}")
def admin_update_criterion(criterion_id: int, req: CriterionUpdate, user: dict = Depends(require_admin)):
    """Atualiza um criterio existente (por id numerico) e invalida o cache.

    Retorna 404 se o criterio nao existir.
    """
    try:
        updated = update_criterion(
             database.get_connection,
             criterion_id,
             req.chave,
             req.label,
             req.weight,
             req.description,
             req.type,
             req.deflator,
             req.referencia,
             req.exemplo,
             alterado_por=_username(user),
             motivo=req.motivo or "",
        )
    except AlertWeightBudgetExceeded as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
         raise HTTPException(status_code=404, detail="Critério não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "updated", "id": criterion_id}

@router.delete("/api/admin/criteria/{criterion_id}")
def admin_delete_criterion(
    criterion_id: int,
    motivo: Optional[str] = Query(default=None),
    user: dict = Depends(require_admin),
):
    """Remove um criterio (por id numerico) e invalida o cache.

    `motivo` (query) vai pro audit log. Retorna 404 se o criterio nao existir.
    """
    if not delete_criterion(
        database.get_connection,
        criterion_id,
        alterado_por=_username(user),
        motivo=motivo or "",
    ):
        raise HTTPException(status_code=404, detail="Critério não encontrado.")
    _invalidate_catalog_cache()
    return {"status": "deleted", "id": criterion_id}


# --- Audit log (Fase 1.1) ---

@router.get("/api/admin/criteria/audit-log")
def admin_list_criteria_audit_log(
    entity_type: str = Query(..., pattern="^(sector|alert|criterion)$"),
    entity_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _user: dict = Depends(require_admin),
):
    """Lista mudancas em audit_sectors/alerts/criteria (mais recentes primeiro).

    `entity_type` obrigatorio (sector|alert|criterion). `entity_id` opcional pra
    filtrar so as mudancas de um critério/alerta/setor especifico.
    """
    return list_audit_log(
        database.get_connection,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )


# --- Cache invalidation (Fase 1.2) ---

@router.post("/api/admin/criteria/cache/invalidate")
def admin_invalidate_criteria_cache(_user: dict = Depends(require_admin)):
    """Invalida o lru_cache do catalogo de criterios em classification.py.

    Necessario apos qualquer mutacao via UI para a IA passar a usar os valores
    atualizados sem restart. As proprias rotas de mutacao deveriam chamar isso
    automaticamente — endpoint exposto pra cenarios de seed externo / debug.
    """
    from core.classification import clear_classification_caches

    clear_classification_caches()
    return {"status": "invalidated", "caches": ["load_audit_criteria_catalog", "build_sectors_and_alerts_prompt", "get_alert_lookup_by_id"]}
