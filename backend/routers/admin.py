"""Router admin: gestão de usuários e colaboradores (RH).

Expõe os endpoints ``/api/admin/...`` e ``/api/rh/...`` usados pelas telas
administrativas:

- contas de login (tabela ``users``): listar, criar, atualizar, deletar e gerar
  contas de supervisor em lote a partir das escalas;
- colaboradores/operadores (cadastro de RH): CRUD e ação em lote
  (ativar/inativar, habilitar/desabilitar auditoria), além de vínculo e lookups
  para os prompts.

As rotas de colaborador são expostas em dois caminhos equivalentes
(``/operadores`` e ``/colaboradores``) por compatibilidade. A maioria exige
``require_admin``; os lookups de RH aceitam usuário autenticado e, quando o papel
é ``supervisor``, restringem o resultado ao supervisor do próprio usuário.

Sem custo de API de IA: só acesso a banco via os repositórios ``operators`` e
``auth_users``. As validações de senha (mín. 8 caracteres, maiúscula e dígito)
vivem nos handlers de criação/atualização de usuário.
"""

import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import db.database as database
from repositories import operators
from repositories import auth_users
from routers.auth import (
    _normalize_auth_lookup,
    require_admin,
    require_authenticated_user,
)
from routers.common import generate_temporary_password, resolve_user_supervisor_name


router = APIRouter(tags=["admin"])


def _generate_temporary_password() -> str:
    """Gera uma senha temporária, respeitando override de ``main``.

    Se o módulo ``main`` (ou ``backend.main``) expuser um
    ``_generate_temporary_password`` (caminho usado por testes via monkeypatch),
    delega para ele; caso contrário usa o gerador padrão de ``routers.common``.
    """
    main_module = sys.modules.get("main") or sys.modules.get("backend.main")
    if main_module is not None:
        patched_generator = getattr(main_module, "_generate_temporary_password", None)
        if callable(patched_generator):
            return patched_generator()
    return generate_temporary_password()


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "admin"
    supervisor_name: str = ""
    sector_id: str = ""
    escala: str = ""


class VincularOperadorRequest(BaseModel):
    nome: str
    operator_id: str
    sector_id: str = ""


class CreateColaboradorRequest(BaseModel):
    nome: str
    supervisor: str = ""
    setor: str = ""
    escala: str = ""
    status: str = "ATIVO"
    auditavel: bool = True
    matricula: str = ""
    id_weon: str = ""
    id_huawei: str = ""
    id_telefonia: str = ""
    softphone_number: str = ""
    telefonia_account: str = ""
    organizacao_telefonia: str = ""
    tipo_agente: str = ""
    status_telefonia: str = ""


class UpdateColaboradorRequest(BaseModel):
    nome: str
    supervisor: str = ""
    setor: str = ""
    escala: str = ""
    status: str = "ATIVO"
    auditavel: bool = True
    matricula: str = ""
    id_weon: str = ""
    id_huawei: str = ""
    id_telefonia: str = ""
    softphone_number: str = ""
    telefonia_account: str = ""
    organizacao_telefonia: str = ""
    tipo_agente: str = ""
    status_telefonia: str = ""


class BulkColaboradorActionRequest(BaseModel):
    ids: list[int]
    action: str


@router.post("/api/admin/generate-supervisor-accounts")
def generate_supervisor_accounts(_user: dict = Depends(require_admin)):
    """Cria contas de login (role ``supervisor``) para supervisores sem usuário.

    Compara os supervisores conhecidos (de ``get_supervisores_e_escalas``) com os
    usuários já existentes (normalizando os nomes via ``_normalize_auth_lookup``) e
    cria apenas os que faltam, cada um com uma senha temporária gerada.

    Requer admin. Efeitos colaterais: lê e escreve na tabela ``users``. Retorna o
    total criado, a lista de usernames e as credenciais temporárias geradas (para
    repasse manual).
    """
    supervisors = operators.get_supervisores_e_escalas(database.get_connection)

    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT supervisor_name, username FROM users")
        existing_users = cursor.fetchall()
    finally:
        conn.close()

    existing_supervisor_names = {
        _normalize_auth_lookup(row[0] or row[1]) for row in existing_users
    }

    new_users = []
    for supervisor_name in supervisors.keys():
        normalized_supervisor_name = _normalize_auth_lookup(supervisor_name)
        if normalized_supervisor_name in existing_supervisor_names:
            continue

        username = supervisor_name.strip()
        password = _generate_temporary_password()
        auth_users.create_user(database.get_connection, username, password, "supervisor", username)
        new_users.append(
            {
                "username": username,
                "role": "supervisor",
                "supervisor_name": username,
                "temporary_password": password,
            }
        )
        existing_supervisor_names.add(normalized_supervisor_name)

    return {
        "created": len(new_users),
        "usernames": [user["username"] for user in new_users],
        "credentials": [
            {"username": user["username"], "temporary_password": user["temporary_password"]}
            for user in new_users
        ],
    }


@router.get("/api/admin/users")
def admin_list_users(_user: dict = Depends(require_admin)):
    """Lista todas as contas de login (tabela ``users``). Requer admin."""
    return auth_users.list_users(database.get_connection)


@router.post("/api/admin/users")
def admin_create_user(req: CreateUserRequest, _user: dict = Depends(require_admin)):
    """Cria uma conta de login. Requer admin.

    Valida obrigatoriedade de usuário/senha, política de senha (mín. 8 caracteres,
    ao menos uma maiúscula e um dígito) e ``role`` em {``admin``, ``supervisor``}.
    Levanta HTTP 400 em validação inválida e HTTP 409 se o usuário já existir.
    Efeito colateral: INSERT em ``users``. Retorna status e o username (lowercase).
    """
    if not req.username.strip() or not req.password.strip():
        raise HTTPException(status_code=400, detail="Usuário e senha são obrigatórios.")
    password = req.password.strip()
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres.")
    if not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos uma letra maiúscula.")
    if not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos um número.")
    if req.role not in ("admin", "supervisor"):
        raise HTTPException(status_code=400, detail="O perfil deve ser 'admin' ou 'supervisor'.")
    ok = auth_users.create_user(database.get_connection, req.username, req.password, req.role, req.supervisor_name, req.sector_id, req.escala)
    if not ok:
        raise HTTPException(status_code=409, detail="Usuário já existe.")
    return {"status": "created", "username": req.username.lower()}


@router.delete("/api/admin/users/{username}")
def admin_delete_user(username: str, user: dict = Depends(require_admin)):
    """Deleta uma conta de login. Requer admin.

    Impede a autoexclusão (HTTP 400 se ``username`` for o do próprio usuário) e
    levanta HTTP 404 se a conta não existir. Efeito colateral: DELETE em ``users``.
    """
    if _normalize_auth_lookup(username) == _normalize_auth_lookup(user.get("username", "")):
        raise HTTPException(status_code=400, detail="Não é possível deletar o próprio usuário.")
    ok = auth_users.delete_user(database.get_connection, username)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"status": "deleted", "username": username}


class UpdateUserRequest(BaseModel):
    password: str = ""
    role: str = ""
    supervisor_name: str = ""
    sector_id: str = ""
    escala: str = ""


@router.put("/api/admin/users/{username}")
def admin_update_user(username: str, req: UpdateUserRequest, _user: dict = Depends(require_admin)):
    """Atualiza uma conta de login. Requer admin.

    Campos vazios são tratados como "não alterar" (viram None). Se uma nova senha
    for informada, aplica a mesma política de força (mín. 8, maiúscula, dígito);
    ``role``, quando informado, deve ser ``admin`` ou ``supervisor``. Levanta HTTP
    400 em validação inválida e HTTP 404 se a conta não existir. Efeito colateral:
    UPDATE em ``users``.
    """
    new_password = req.password.strip() or None
    if new_password:
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres.")
        if not any(c.isupper() for c in new_password):
            raise HTTPException(status_code=400, detail="A senha deve conter pelo menos uma letra maiúscula.")
        if not any(c.isdigit() for c in new_password):
            raise HTTPException(status_code=400, detail="A senha deve conter pelo menos um número.")
    role = req.role.strip() or None
    if role and role not in ("admin", "supervisor"):
        raise HTTPException(status_code=400, detail="O perfil deve ser 'admin' ou 'supervisor'.")
    supervisor_name = req.supervisor_name if req.supervisor_name is not None else None
    sector_id = req.sector_id if req.sector_id is not None else None
    escala = req.escala if req.escala is not None else None
    ok = auth_users.update_user(
        database.get_connection,
        username,
        new_password=new_password,
        role=role,
        supervisor_name=supervisor_name,
        sector_id=sector_id,
        escala=escala,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {"status": "updated", "username": username}


@router.get("/api/admin/operadores")
@router.get("/api/admin/colaboradores")
def admin_list_operadores(_user: dict = Depends(require_admin)):
    """Lista todos os colaboradores cadastrados. Requer admin.

    Exposto nos dois caminhos (``/operadores`` e ``/colaboradores``) por
    compatibilidade. Somente leitura.
    """
    return operators.list_colaboradores(database.get_connection)


@router.post("/api/admin/operadores")
@router.post("/api/admin/colaboradores")
def admin_create_operador(req: CreateColaboradorRequest, _user: dict = Depends(require_admin)):
    """Cria um colaborador (cadastro de RH). Requer admin.

    Exige ``nome`` (HTTP 400 se vazio); demais campos (supervisor, setor, escala,
    ids de telefonia/Huawei/WEON, status, auditável etc.) são opcionais. Efeito
    colateral: INSERT em ``colaboradores``. Retorna o ``id`` criado.
    """
    if not req.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    new_id = operators.create_colaborador(database.get_connection, 
        nome=req.nome,
        supervisor=req.supervisor,
        setor=req.setor,
        escala=req.escala,
        status=req.status,
        auditavel=req.auditavel,
        matricula=req.matricula,
        id_weon=req.id_weon,
        id_huawei=req.id_huawei,
        id_telefonia=req.id_telefonia,
        softphone_number=req.softphone_number,
        telefonia_account=req.telefonia_account,
        organizacao_telefonia=req.organizacao_telefonia,
        tipo_agente=req.tipo_agente,
        status_telefonia=req.status_telefonia,
    )
    return {"status": "created", "id": new_id}


@router.put("/api/admin/operadores/{operador_id}")
@router.put("/api/admin/colaboradores/{operador_id}")
def admin_update_operador(
    operador_id: int,
    req: UpdateColaboradorRequest,
    _user: dict = Depends(require_admin),
):
    """Atualiza um colaborador pelo id. Requer admin.

    Exige ``nome`` (HTTP 400 se vazio) e levanta HTTP 404 se o colaborador não
    existir. Efeito colateral: UPDATE em ``colaboradores``.
    """
    if not req.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    ok = operators.update_colaborador(database.get_connection, 
        colaborador_id=operador_id,
        nome=req.nome,
        supervisor=req.supervisor,
        setor=req.setor,
        escala=req.escala,
        status=req.status,
        auditavel=req.auditavel,
        matricula=req.matricula,
        id_weon=req.id_weon,
        id_huawei=req.id_huawei,
        id_telefonia=req.id_telefonia,
        softphone_number=req.softphone_number,
        telefonia_account=req.telefonia_account,
        organizacao_telefonia=req.organizacao_telefonia,
        tipo_agente=req.tipo_agente,
        status_telefonia=req.status_telefonia,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    return {"status": "updated", "id": operador_id}


@router.delete("/api/admin/operadores/{operador_id}")
@router.delete("/api/admin/colaboradores/{operador_id}")
def admin_delete_operador(operador_id: int, _user: dict = Depends(require_admin)):
    """Deleta um colaborador pelo id. Requer admin.

    Levanta HTTP 404 se não existir. Efeito colateral: DELETE em ``colaboradores``.
    """
    ok = operators.delete_colaborador(database.get_connection, operador_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    return {"status": "deleted", "id": operador_id}


@router.post("/api/admin/operadores/bulk-action")
@router.post("/api/admin/colaboradores/bulk-action")
def admin_bulk_action_operadores(
    req: BulkColaboradorActionRequest,
    _user: dict = Depends(require_admin),
):
    """Aplica uma ação em lote a vários colaboradores. Requer admin.

    ``action`` deve estar em {``activate``, ``inactivate``, ``enable_audit``,
    ``disable_audit``} (HTTP 400 caso contrário). Efeito colateral: UPDATE em massa
    em ``colaboradores`` para os ``ids`` informados. Retorna o total solicitado e o
    total efetivamente atualizado.
    """
    valid_actions = {"activate", "inactivate", "enable_audit", "disable_audit"}
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail="Ação em lote inválida.")
    updated = operators.bulk_apply_colaborador_action(database.get_connection, req.ids, req.action)
    return {
        "status": "updated",
        "requested": len(req.ids),
        "updated": updated,
        "action": req.action,
    }


@router.post("/api/rh/operadores/vincular")
def vincular_operador(req: VincularOperadorRequest, _user: dict = Depends(require_admin)):
    """Vincula/garante um colaborador a um ``operator_id`` (e setor). Requer admin.

    Delega a ``operators.ensure_colaborador_exists`` (cria ou atualiza o vínculo).
    Efeito colateral: pode inserir/atualizar em ``colaboradores``.
    """
    return operators.ensure_colaborador_exists(database.get_connection, req.nome, req.operator_id, req.sector_id)


@router.get("/api/rh/operadores")
def get_rh_operadores(
    supervisor: str = None,
    escala: str = None,
    sector_id: str = None,
    user: dict = Depends(require_authenticated_user),
):
    """Lista colaboradores para uso nos prompts (filtrável). Requer autenticação.

    Aceita filtros opcionais ``supervisor``, ``escala`` e ``sector_id``. Se o
    usuário for ``supervisor``, o filtro de supervisor é forçado para o nome do
    próprio usuário (ignora o parâmetro recebido). Somente leitura.
    """
    effective_supervisor = supervisor
    if user.get("role") == "supervisor":
        effective_supervisor = resolve_user_supervisor_name(user)
    return operators.get_colaboradores_para_prompt(database.get_connection, 
        supervisor=effective_supervisor,
        escala=escala,
        sector_id=sector_id,
    )


@router.get("/api/rh/operadores/lookup")
def get_rh_operadores_lookup(
    supervisor: str = None,
    escala: str = None,
    sector_id: str = None,
    search: str = None,
    limit: int = 100,
    user: dict = Depends(require_authenticated_user),
):
    """Lookup paginado/buscável de colaboradores (autocomplete). Requer autenticação.

    Igual a ``get_rh_operadores`` quanto a filtros e à restrição por supervisor
    quando o usuário é ``supervisor``, mas aceita também ``search`` (texto) e
    ``limit``. Somente leitura.
    """
    effective_supervisor = supervisor
    if user.get("role") == "supervisor":
        effective_supervisor = resolve_user_supervisor_name(user)
    return operators.get_colaboradores_lookup(database.get_connection, 
        supervisor=effective_supervisor,
        escala=escala,
        sector_id=sector_id,
        search=search,
        limit=limit,
    )
