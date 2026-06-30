"""Repositório de colaboradores/operadores (tabela `colaboradores`).

Fonte de verdade do cadastro de operadores auditáveis. Cobre o CRUD de
colaboradores, a importação/upsert vinda do RH e da telefonia (Huawei), e a
resolução de qual operador é elegível para auditoria a partir de nome/id/setor.

Regras de negócio centrais aplicadas nas consultas:
- "Auditável" exige status ATIVO e flag `auditavel` (ver `_is_auditable_row`);
  linhas técnicas de telefonia e operadores removidos são filtrados
  (`_is_technical_telephony_row`, `_is_removed_operator_row`).
- O setor é resolvido/canonicalizado a partir de setor+escala+organização
  (`_normalize_operator_sector`, `map_db_sector_to_classification_sector` e o
  mapeamento de aliases em `operator_sector_mapping`).
- ids Huawei e de telefonia são coeridos/normalizados antes de gravar ou comparar
  (`_coerce_huawei_and_telefonia_ids`, `normalize_huawei_agent_id`).
- Mutações (create/update/delete) registram trilha de auditoria via
  `colaboradores_audit_log` (`_snapshot_colaborador` + `_log_colaborador_audit`).

Helpers puros foram extraídos para `operator_normalization`,
`operator_sector_mapping` e `colaboradores_audit_log` e são reexportados aqui
(`operators.<helper>`) para manter compatibilidade de imports e monkeypatch.

Sem custo de API (apenas acesso a banco/CPU).
"""

import contextlib
import json
from typing import Callable, Optional, Any

from core.operator_filters import (
    is_excluded_operation_values,
    is_technical_telephony_values,
)
from repositories.common import extract_returning_id, normalize_huawei_agent_id
# Helpers puros de normalização/parsing reexportados de operator_normalization
# (extraídos para legibilidade). Compat total: callers/testes usam operators.<helper>.
from repositories.operator_normalization import (  # noqa: F401
    _normalize_lookup_text,
    _map_status_telefonia_to_status,
    _is_active_status,
    _default_auditavel_from_status,
    _is_auditable_row,
    _coerce_auditavel,
    _normalize_operator_sector,
    _coerce_huawei_and_telefonia_ids,
    _resolve_huawei_id,
    _is_technical_telephony_row,
    _is_excluded_operation_row,
    _is_removed_operator_row,
    _pick_preferred_operator_id,
    _operator_payload_from_row,
)
# Trilha de auditoria de colaboradores: extraída para colaboradores_audit_log;
# reexportada p/ compat (callers internos + admin_criteria importam estes nomes).
from repositories.colaboradores_audit_log import (  # noqa: F401
    _snapshot_colaborador,
    _log_colaborador_audit,
)
from utils.text_processing import format_pt_br_name


ConnectionFactory = Callable[[], Any]


# Resolução/matching de setor canônico do colaborador: extraído para
# operator_sector_mapping (v1.3.165); reexportado p/ compat (callers internos +
# fachada usam operators.<nome>).
from repositories.operator_sector_mapping import (  # noqa: E402,F401
    _get_sector_aliases_repo,
    _get_default_connection_factory,
    _load_sector_aliases_dict,
    _map_organizacao_telefonia_to_sector,
    map_db_sector_to_classification_sector,
    _matches_operador_sector,
)


def ensure_colaborador_exists(
    get_connection: ConnectionFactory,
    nome: str,
    id_telefonia: str,
    sector_id: str = None,
) -> dict:
    """Garante o vínculo de um colaborador já existente com um `id_telefonia`.

    NÃO cria colaborador novo — o operador precisa já existir no cadastro. Procura
    por nome normalizado; se achar e o colaborador ainda não tem `id_telefonia`,
    preenche-o (UPDATE + commit).

    Retorna um dict de resultado descrevendo a ação tomada (chaves `action`/`reason`/
    `id`): "skipped" (nome vazio), "updated" (telefonia preenchida), "already_linked"
    (já tinha vínculo) ou "not_found" (nome não cadastrado). Efeito colateral:
    possível UPDATE em `colaboradores`.
    """
    normalized_name = _normalize_lookup_text(nome)
    id_telefonia = normalize_huawei_agent_id(id_telefonia)
    if not normalized_name:
        return {"action": "skipped", "reason": "empty_name"}

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, id_telefonia FROM colaboradores")
        rows = cursor.fetchall()

        match = next(
            (row for row in rows if _normalize_lookup_text(row["nome"]) == normalized_name),
            None,
        )
        if match:
            if not match["id_telefonia"] and id_telefonia:
                cursor.execute(
                    "UPDATE colaboradores SET id_telefonia = %s, atualizado_em = CURRENT_TIMESTAMP WHERE id = %s",
                    (id_telefonia, match["id"]),
                )
                conn.commit()
                return {"action": "updated", "id": match["id"]}

            return {"action": "already_linked", "id": match["id"]}

        return {"action": "not_found", "reason": "operator_must_exist_in_operadores"}
    finally:
        conn.close()


def upsert_colaborador(
    get_connection: ConnectionFactory,
    matricula: str,
    nome: str,
    supervisor: str,
    setor: str,
    escala: str,
    status: str,
    id_weon: str = "",
    id_huawei: str = "",
):
    """Insere ou atualiza um colaborador a partir de dados do cadastro de RH.

    Casa por `matricula` OU por `nome` (não-vazio). Se já existe, faz UPDATE
    preservando o `auditavel` atual quando presente; senão deriva `auditavel` do
    `status` (`_default_auditavel_from_status`) e faz INSERT. Nome é formatado em
    PT-BR, setor é canonicalizado (setor+escala) e `id_huawei` é normalizado antes
    de gravar. Não retorna valor. Efeito colateral: INSERT/UPDATE em `colaboradores`
    + commit.
    """
    nome = format_pt_br_name(nome.strip())
    setor = _normalize_operator_sector(setor, escala)
    id_huawei = normalize_huawei_agent_id(id_huawei)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, auditavel FROM colaboradores WHERE matricula = %s OR (nome = %s AND nome != '')",
            (matricula, nome),
        )
        row = cursor.fetchone()
        auditavel_value = row[1] if row and row[1] is not None else _default_auditavel_from_status(status)

        if row:
            cursor.execute(
                """
                UPDATE colaboradores
                SET nome = %s, supervisor = %s, setor = %s, escala = %s, status = %s, auditavel = %s, id_weon = %s, id_huawei = %s, atualizado_em = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (nome, supervisor, setor, escala, status, auditavel_value, id_weon, id_huawei, row[0]),
            )
            cursor.execute(
                """
                UPDATE fechamento_layout_operadores
                SET nome = %s, supervisor = %s, setor = %s, matricula = %s,
                    turno_operacao = %s, huawei = %s, weon = %s, status_base = %s,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE colaborador_id = %s
                """,
                (nome, supervisor, setor, matricula, escala, id_huawei, id_weon, status, row[0]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO colaboradores (
                    matricula, nome, supervisor, setor, escala, status, auditavel, id_weon, id_huawei
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (matricula, nome, supervisor, setor, escala, status, auditavel_value, id_weon, id_huawei),
            )

        conn.commit()
    finally:
        conn.close()


def upsert_colaborador_telefonia(
    get_connection: ConnectionFactory,
    nome: str,
    id_telefonia: str = "",
    softphone_number: str = "",
    telefonia_account: str = "",
    organizacao_telefonia: str = "",
    tipo_agente: str = "",
    status_telefonia: str = "",
):
    """Insere ou atualiza um colaborador a partir de dados da telefonia (Huawei).

    Casa o registro em ordem de prioridade: `id_telefonia`, depois
    `softphone_number`, depois nome normalizado. Mapeia organização -> setor e
    status de telefonia -> status interno. Se a linha for de operação excluída ou
    técnica (`is_excluded_operation_values`/`is_technical_telephony_values`), marca
    o colaborador existente como INATIVO/não-auditável e retorna sem inserir.
    Caso contrário faz UPDATE preservando campos já preenchidos, ou INSERT de uma
    linha INATIVA/não-auditável quando o operador é novo na base. Não retorna valor.
    Efeito colateral: INSERT/UPDATE em `colaboradores` + commit.
    """
    nome = format_pt_br_name(nome.strip())
    conn = get_connection()
    try:
        cursor = conn.cursor()
        _, id_telefonia = _coerce_huawei_and_telefonia_ids("", id_telefonia)

        normalized_name = _normalize_lookup_text(nome)
        existing_row = None

        if id_telefonia:
            cursor.execute("SELECT * FROM colaboradores WHERE id_telefonia = %s", (id_telefonia,))
            existing_row = cursor.fetchone()

        if existing_row is None and softphone_number:
            cursor.execute("SELECT * FROM colaboradores WHERE softphone_number = %s", (softphone_number,))
            existing_row = cursor.fetchone()

        if existing_row is None:
            cursor.execute("SELECT * FROM colaboradores WHERE nome IS NOT NULL AND nome != ''")
            rows = cursor.fetchall()
            existing_row = next(
                (row for row in rows if _normalize_lookup_text(row["nome"]) == normalized_name),
                None,
            )

        mapped_sector = _map_organizacao_telefonia_to_sector(organizacao_telefonia)
        mapped_status = _map_status_telefonia_to_status(status_telefonia)
        mapped_auditavel = _default_auditavel_from_status(mapped_status)
        should_remove_from_process = is_excluded_operation_values(
            mapped_sector,
            organizacao_telefonia,
            telefonia_account,
        ) or is_technical_telephony_values(
            nome=nome,
            matricula=existing_row["matricula"] if existing_row else "",
            supervisor=existing_row["supervisor"] if existing_row else "",
            telefonia_account=telefonia_account,
            organizacao_telefonia=organizacao_telefonia,
            tipo_agente=tipo_agente,
            status_telefonia=status_telefonia,
            id_telefonia=id_telefonia,
            softphone_number=softphone_number,
        )
        if should_remove_from_process:
            if existing_row:
                cursor.execute(
                    """
                    UPDATE colaboradores
                    SET status = 'INATIVO',
                        auditavel = 0,
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (existing_row["id"],),
                )
                cursor.execute(
                    """
                    UPDATE fechamento_layout_operadores
                    SET status_base = 'INATIVO',
                        atualizado_em = CURRENT_TIMESTAMP
                    WHERE colaborador_id = %s
                    """,
                    (existing_row["id"],),
                )
                conn.commit()
            return

        if existing_row:
            resolved_escala = existing_row["escala"] or organizacao_telefonia
            resolved_setor = _normalize_operator_sector(
                existing_row["setor"] or mapped_sector,
                resolved_escala,
                organizacao_telefonia or existing_row["organizacao_telefonia"] or "",
            )
            resolved_id_huawei, resolved_id_telefonia = _coerce_huawei_and_telefonia_ids(
                existing_row["id_huawei"] or "",
                id_telefonia or existing_row["id_telefonia"] or "",
            )
            cursor.execute(
                """
                UPDATE colaboradores
                SET nome = %s,
                    setor = %s,
                    escala = %s,
                    status = %s,
                    auditavel = %s,
                    id_huawei = %s,
                    id_telefonia = %s,
                    softphone_number = %s,
                    telefonia_account = %s,
                    organizacao_telefonia = %s,
                    tipo_agente = %s,
                    status_telefonia = %s,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (
                    nome or existing_row["nome"] or "",
                    resolved_setor,
                    resolved_escala,
                    existing_row["status"] or mapped_status,
                    existing_row["auditavel"] if existing_row["auditavel"] is not None else mapped_auditavel,
                    resolved_id_huawei,
                    resolved_id_telefonia,
                    softphone_number or existing_row["softphone_number"] or "",
                    telefonia_account or existing_row["telefonia_account"] or "",
                    organizacao_telefonia or existing_row["organizacao_telefonia"] or "",
                    tipo_agente or existing_row["tipo_agente"] or "",
                    status_telefonia or existing_row["status_telefonia"] or "",
                    existing_row["id"],
                ),
            )
            cursor.execute(
                """
                UPDATE fechamento_layout_operadores
                SET nome = %s, setor = %s, turno_operacao = %s, status_base = %s,
                    huawei = %s, atualizado_em = CURRENT_TIMESTAMP
                WHERE colaborador_id = %s
                """,
                (
                    nome or existing_row["nome"] or "",
                    resolved_setor,
                    resolved_escala,
                    existing_row["status"] or mapped_status,
                    resolved_id_huawei,
                    existing_row["id"],
                ),
            )
        else:
            resolved_setor = _normalize_operator_sector(mapped_sector, organizacao_telefonia, organizacao_telefonia)
            resolved_id_huawei, resolved_id_telefonia = _coerce_huawei_and_telefonia_ids("", id_telefonia)
            cursor.execute(
                """
                INSERT INTO colaboradores (
                    matricula, nome, supervisor, setor, escala, status, auditavel,
                    id_weon, id_huawei, id_telefonia, softphone_number,
                    telefonia_account, organizacao_telefonia, tipo_agente, status_telefonia
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "",
                    nome,
                    "",
                    resolved_setor,
                    organizacao_telefonia,
                    "INATIVO",
                    0,
                    "",
                    resolved_id_huawei,
                    resolved_id_telefonia,
                    softphone_number,
                    telefonia_account,
                    organizacao_telefonia,
                    tipo_agente,
                    status_telefonia,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def get_supervisores_e_escalas(get_connection: ConnectionFactory) -> dict:
    """Mapeia supervisores ativos para a lista de escalas que eles supervisionam.

    Considera apenas colaboradores ATIVOS com supervisor preenchido, ignorando
    linhas de operadores removidos. Escala vazia vira "Sem Escala".
    Retorna `{supervisor: [escala, ...]}`. Efeito colateral: leitura no banco.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT supervisor, escala, setor, nome, matricula,
                   telefonia_account, organizacao_telefonia, tipo_agente,
                   status_telefonia, id_telefonia, softphone_number
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND supervisor IS NOT NULL
              AND supervisor != ''
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    result = {}
    for row in rows:
        if _is_removed_operator_row(row):
            continue
        supervisor = row["supervisor"].strip()
        escala = row["escala"].strip() if row["escala"] else "Sem Escala"
        if supervisor not in result:
            result[supervisor] = set()
        result[supervisor].add(escala)

    return {key: list(value) for key, value in result.items()}


def list_supervisores(get_connection: ConnectionFactory) -> list[str]:
    """Retorna a lista ordenada de supervisores ativos (chaves de
    `get_supervisores_e_escalas`). Efeito colateral: leitura no banco.
    """
    return sorted(get_supervisores_e_escalas(get_connection).keys())


def buscar_colaborador_por_nome(get_connection: ConnectionFactory, nome: str) -> Optional[dict]:
    """Busca um colaborador auditável por nome, com fallback de match aproximado.

    Primeiro tenta match exato por nome normalizado entre colaboradores ATIVOS e
    auditáveis. Não achando, faz um match heurístico: exige o mesmo primeiro nome
    (>= 3 chars) e pontua pela sobreposição de partes do nome, escolhendo o de maior
    score. Linhas técnicas/removidas são ignoradas.

    Retorna um dict com chaves em camelCase para a UI (`name`, `preferredId`,
    `supervisor`, `setor`, `escala`, `matricula`, `idHuawei`, `idTelefonia`, ...) ou
    None se nada casar. Efeito colateral: leitura no banco.
    """
    if not nome or not nome.strip():
        return None
    normalized_target = _normalize_lookup_text(nome)
    if not normalized_target:
        return None

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, matricula, id_huawei,
                   id_telefonia, softphone_number, telefonia_account,
                   organizacao_telefonia, tipo_agente, status_telefonia, id_weon,
                   auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND nome IS NOT NULL
              AND nome != ''
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    for row in rows:
        if not _is_auditable_row(row) or _is_removed_operator_row(row):
            continue
        if _normalize_lookup_text(row["nome"]) == normalized_target:
            preferred_id, preferred_id_source = _pick_preferred_operator_id(row)
            resolved_setor = _normalize_operator_sector(
                row["setor"] or "",
                row["escala"] or "",
                row["organizacao_telefonia"] or "",
            )
            resolved_huawei_id = _resolve_huawei_id(row)
            _, resolved_telefonia_id = _coerce_huawei_and_telefonia_ids(
                row["id_huawei"],
                row["id_telefonia"],
            )
            return {
                "id": row["id"],
                "name": str(row["nome"] or "").strip(),
                "preferredId": preferred_id,
                "preferredIdSource": preferred_id_source,
                "supervisor": str(row["supervisor"] or "").strip(),
                "setor": resolved_setor,
                "escala": str(row["escala"] or "").strip(),
                "matricula": str(row["matricula"] or "").strip(),
                "idHuawei": resolved_huawei_id,
                "idTelefonia": resolved_telefonia_id,
                "softphoneNumber": str(row["softphone_number"] or "").strip(),
                "telefoniaAccount": str(row["telefonia_account"] or "").strip(),
                "organizacaoTelefonia": str(row["organizacao_telefonia"] or "").strip(),
                "tipoAgente": str(row["tipo_agente"] or "").strip(),
                "statusTelefonia": str(row["status_telefonia"] or "").strip(),
            }

    target_parts = normalized_target.split()
    if not target_parts:
        return None
    target_first = target_parts[0]
    if len(target_first) < 3:
        return None

    best_match = None
    best_score = 0
    for row in rows:
        if not _is_auditable_row(row) or _is_removed_operator_row(row):
            continue
        db_name = _normalize_lookup_text(row["nome"])
        db_parts = db_name.split()
        if not db_parts:
            continue
        if db_parts[0] != target_first:
            continue

        if len(target_parts) == 1 and len(db_parts) >= 1:
            score = 1.0 / len(db_parts)
        else:
            exact_matches = sum(1 for target_part in target_parts if target_part in db_parts)
            score = exact_matches / max(len(target_parts), len(db_parts))

        if score > best_score:
            best_score = score
            best_match = row

    if best_match:
        preferred_id, preferred_id_source = _pick_preferred_operator_id(best_match)
        resolved_setor = _normalize_operator_sector(
            best_match["setor"] or "",
            best_match["escala"] or "",
            best_match["organizacao_telefonia"] or "",
        )
        resolved_huawei_id = _resolve_huawei_id(best_match)
        _, resolved_telefonia_id = _coerce_huawei_and_telefonia_ids(
            best_match["id_huawei"],
            best_match["id_telefonia"],
        )
        return {
            "id": best_match["id"],
            "name": str(best_match["nome"] or "").strip(),
            "preferredId": preferred_id,
            "preferredIdSource": preferred_id_source,
            "supervisor": str(best_match["supervisor"] or "").strip(),
            "setor": resolved_setor,
            "escala": str(best_match["escala"] or "").strip(),
            "matricula": str(best_match["matricula"] or "").strip(),
            "idHuawei": resolved_huawei_id,
            "idTelefonia": resolved_telefonia_id,
            "softphoneNumber": str(best_match["softphone_number"] or "").strip(),
            "telefoniaAccount": str(best_match["telefonia_account"] or "").strip(),
            "organizacaoTelefonia": str(best_match["organizacao_telefonia"] or "").strip(),
            "tipoAgente": str(best_match["tipo_agente"] or "").strip(),
            "statusTelefonia": str(best_match["status_telefonia"] or "").strip(),
        }

    return None


def buscar_colaborador_por_matricula(get_connection: ConnectionFactory, matricula: str) -> Optional[dict]:
    """Busca um colaborador auditável pela `matricula` (match exato).

    Considera apenas colaboradores com `auditavel = TRUE` e `excluido = FALSE`.
    Retorna o dict montado por `_dict_from_colaborador_row` ou None se não houver
    correspondência (ou em caso de erro, que é logado). Efeito colateral: leitura
    no banco.
    """
    if not matricula or not str(matricula).strip():
        return None
    target_matricula = str(matricula).strip()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, matricula, id_huawei,
                   id_telefonia, softphone_number, telefonia_account,
                   organizacao_telefonia, tipo_agente, status_telefonia, id_weon,
                   auditavel
            FROM colaboradores
            WHERE matricula = %s AND auditavel = TRUE AND excluido = FALSE
            """,
            (target_matricula,)
        )
        row = cursor.fetchone()
        if row:
            from db.database import _dict_from_colaborador_row
            return _dict_from_colaborador_row(row)
    except Exception as e:
        from config.logging_config import logger
        logger.error(f"Erro ao buscar colaborador por matricula: {e}")
    finally:
        conn.close()
    return None

def buscar_colaborador_por_id_huawei(get_connection: ConnectionFactory, id_huawei: str) -> Optional[dict]:
    """Busca um colaborador auditável pelo id de agente Huawei (match exato).

    Normaliza `id_huawei` antes de consultar; considera apenas ATIVO + auditável.
    Retorna um dict camelCase para a UI (mesmo formato de `buscar_colaborador_por_nome`,
    acrescido de `huawei_registered: True`) ou None se não casar ou a linha for
    técnica/removida. Efeito colateral: leitura no banco.
    """
    target_id = normalize_huawei_agent_id(id_huawei)
    if not target_id:
        return None

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, matricula, id_huawei,
                   id_telefonia, softphone_number, telefonia_account,
                   organizacao_telefonia, tipo_agente, status_telefonia, id_weon,
                   auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND COALESCE(NULLIF(TRIM(id_huawei), ''), '') = %s
            """,
            (target_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row or not _is_auditable_row(row) or _is_removed_operator_row(row):
        return None

    preferred_id, preferred_id_source = _pick_preferred_operator_id(row)
    resolved_huawei_id, resolved_telefonia_id = _coerce_huawei_and_telefonia_ids(
        row["id_huawei"],
        row["id_telefonia"],
    )
    resolved_setor = _normalize_operator_sector(
        row["setor"] or "",
        row["escala"] or "",
        row["organizacao_telefonia"] or "",
    )
    return {
        "id": row["id"],
        "name": str(row["nome"] or "").strip(),
        "preferredId": preferred_id,
        "preferredIdSource": preferred_id_source,
        "supervisor": str(row["supervisor"] or "").strip(),
        "setor": resolved_setor,
        "escala": str(row["escala"] or "").strip(),
        "matricula": str(row["matricula"] or "").strip(),
        "idHuawei": resolved_huawei_id,
        "idTelefonia": resolved_telefonia_id,
        "softphoneNumber": str(row["softphone_number"] or "").strip(),
        "telefoniaAccount": str(row["telefonia_account"] or "").strip(),
        "organizacaoTelefonia": str(row["organizacao_telefonia"] or "").strip(),
        "tipoAgente": str(row["tipo_agente"] or "").strip(),
        "statusTelefonia": str(row["status_telefonia"] or "").strip(),
        "huawei_registered": True,
    }


def resolve_auditable_colaborador(
    get_connection: ConnectionFactory,
    nome: str,
    operator_id: Optional[str] = None,
    sector_id: Optional[str] = None,
) -> Optional[dict]:
    """Resolve um operador elegivel para auditoria a partir do modulo Operadores.

    A auditoria deve aceitar somente colaboradores ativos, auditaveis e que
    estejam no setor/processo selecionado. Linhas tecnicas de telefonia ficam
    fora mesmo quando aparecem na base bruta de colaboradores.
    """
    normalized_name = _normalize_lookup_text(nome or "")
    normalized_operator_id = _normalize_lookup_text(operator_id or "")
    if not normalized_name and not normalized_operator_id:
        return None

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, matricula, id_huawei,
                   id_telefonia, softphone_number, telefonia_account,
                   organizacao_telefonia, tipo_agente, status_telefonia,
                   id_weon, auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND nome IS NOT NULL
              AND nome != ''
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    def matches_identity(row) -> bool:
        if normalized_name and _normalize_lookup_text(row["nome"]) == normalized_name:
            return True
        if not normalized_operator_id:
            return False
        identifiers = [
            row["matricula"],
            _resolve_huawei_id(row),
            row["id_huawei"],
            row["id_telefonia"],
            row["softphone_number"],
            row["telefonia_account"],
            row.get("id_weon"),
        ]
        return any(
            normalized_operator_id == _normalize_lookup_text(value)
            for value in identifiers
            if value
        )

    for row in rows:
        if not _is_auditable_row(row):
            continue
        if _is_removed_operator_row(row):
            continue
        if not matches_identity(row):
            continue

        resolved_setor = _normalize_operator_sector(
            row["setor"] or "",
            row["escala"] or "",
            row["organizacao_telefonia"] or "",
        ) or _map_organizacao_telefonia_to_sector(row["organizacao_telefonia"] or "")
        resolved_escala = str(row["escala"] or "").strip() or str(row["organizacao_telefonia"] or "").strip()
        if not _matches_operador_sector(sector_id, resolved_setor, resolved_escala):
            continue

        payload = _operator_payload_from_row(row)
        payload["setor"] = resolved_setor
        payload["escala"] = resolved_escala
        return payload

    return None


def list_colaboradores(get_connection: ConnectionFactory) -> list:
    """Lista todos os colaboradores (não-removidos) já deduplicados e normalizados.

    A ordenação prioriza o titular ATUAL em casos de id_huawei duplicado (ex.:
    handover de ramal): ATIVO antes de INATIVO, auditável antes de não-auditável,
    `atualizado_em` DESC como desempate (ver BUG-025). Cada linha é deduplicada por
    id_huawei -> matricula -> nome, e tem ids/ setor/ flag `auditavel` normalizados
    antes de retornar. Efeito colateral: leitura no banco.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, status,
                   matricula, id_weon, id_huawei, id_telefonia,
                   softphone_number, telefonia_account,
                   organizacao_telefonia, tipo_agente, auditavel,
                   status_telefonia, atualizado_em
            FROM colaboradores
            ORDER BY
              CASE WHEN UPPER(COALESCE(status, '')) = 'ATIVO' THEN 0 ELSE 1 END,
              CASE WHEN COALESCE(auditavel, 1) = 1 THEN 0 ELSE 1 END,
              atualizado_em DESC NULLS LAST,
              nome
            """
        )
        # Ordenacao acima garante que, em casos de duplicidade de id_huawei
        # (ex: handover de ramal entre colaboradores), o titular ATUAL aparece
        # primeiro: ATIVO antes de INATIVO, auditavel antes de nao-auditavel,
        # e atualizado_em DESC como desempate. Sem isso, ORDER BY nome
        # escolhia arbitrariamente o primeiro nome alfabetico e o novo
        # titular do ramal desaparecia (BUG-025).
        rows = [dict(row) for row in cursor.fetchall()]
        filtered_rows = []
        seen_identifiers = set()

        for row in rows:
            if _is_removed_operator_row(row):
                continue

            ident_huawei = normalize_huawei_agent_id(row.get("id_huawei"))
            ident_matricula = str(row.get("matricula") or "").strip()
            ident_nome = str(row.get("nome") or "").strip().lower()

            # Deduplicar por id_huawei ou matricula (caso a importacao tenha gerado duplicidades com IDs vazios)
            # Prioriza id_huawei, depois matricula, senao usa o nome para evitar mostrar o mesmo operador N vezes.
            ident_key = f"h:{ident_huawei}" if ident_huawei else (f"m:{ident_matricula}" if ident_matricula else f"n:{ident_nome}")

            if ident_key in seen_identifiers:
                continue
            seen_identifiers.add(ident_key)
            
            row["id_huawei"], row["id_telefonia"] = _coerce_huawei_and_telefonia_ids(
                row.get("id_huawei", ""),
                row.get("id_telefonia", ""),
            )
            row["setor"] = _normalize_operator_sector(
                row.get("setor", ""),
                row.get("escala", ""),
                row.get("organizacao_telefonia", ""),
            )
            row["auditavel"] = _is_auditable_row(row)
            filtered_rows.append(row)
    finally:
        conn.close()
    return filtered_rows


def listar_auditaveis_com_id_huawei(get_connection: ConnectionFactory) -> list:
    """Retorna colaboradores ATIVOS e auditaveis com id_huawei preenchido.

    Usado pelo orquestrador de sincronizacao Huawei para saber quais agentes
    consultar na API. Para a automacao Huawei, id_telefonia/matricula/nome nao
    habilitam coleta quando id_huawei esta vazio.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, nome, supervisor, setor, escala, matricula,
                   id_huawei, id_telefonia, organizacao_telefonia, auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND COALESCE(NULLIF(TRIM(id_huawei), ''), '') <> ''
            ORDER BY nome
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

    resultado: list[dict] = []
    for row in rows:
        if not _is_auditable_row(row):
            continue
        if _is_removed_operator_row(row):
            continue

        id_huawei_coerced, id_telefonia_coerced = _coerce_huawei_and_telefonia_ids(
            row.get("id_huawei", ""),
            row.get("id_telefonia", ""),
        )
        setor_coerced = _normalize_operator_sector(
            row.get("setor", ""),
            row.get("escala", ""),
            row.get("organizacao_telefonia", ""),
        )
        agent_id = (id_huawei_coerced or "").strip()
        if not agent_id:
            continue
        resultado.append(
            {
                "id": row["id"],
                "nome": str(row.get("nome") or "").strip(),
                "supervisor": str(row.get("supervisor") or "").strip(),
                "setor": setor_coerced,
                "escala": str(row.get("escala") or "").strip(),
                "matricula": str(row.get("matricula") or "").strip(),
                "id_huawei": agent_id,
                "id_telefonia": id_telefonia_coerced,
                "huawei_registered": True,
                "auditavel_db": True,
            }
        )
    return resultado


def create_colaborador(
    get_connection: ConnectionFactory,
    nome: str,
    supervisor: str = "",
    setor: str = "",
    escala: str = "",
    status: str = "ATIVO",
    matricula: str = "",
    id_weon: str = "",
    id_huawei: str = "",
    id_telefonia: str = "",
    softphone_number: str = "",
    telefonia_account: str = "",
    organizacao_telefonia: str = "",
    tipo_agente: str = "",
    status_telefonia: str = "",
    auditavel: Optional[bool] = None,
    oficial: bool = True,
    *,
    alterado_por: str = "system",
    motivo: Optional[str] = None,
    origem: str = "api",
) -> int:
    """Cria um colaborador novo e registra a criação no audit log.

    Formata nome (PT-BR), canonicaliza setor e coage ids Huawei/telefonia antes do
    INSERT. `auditavel` é derivado de `auditavel`/`status` via `_coerce_auditavel`.
    Os parâmetros keyword-only `alterado_por`/`motivo`/`origem` alimentam a trilha em
    `colaboradores_audit_log`.

    Retorna o id do novo colaborador. Efeito colateral: INSERT em `colaboradores`,
    INSERT no audit log e commit.
    """
    nome = format_pt_br_name(nome.strip())
    setor = _normalize_operator_sector(setor, escala, organizacao_telefonia)
    id_huawei, id_telefonia = _coerce_huawei_and_telefonia_ids(id_huawei, id_telefonia)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        auditavel_value = _coerce_auditavel(auditavel, status)
        cursor.execute(
            """
            INSERT INTO colaboradores (
                nome, supervisor, setor, escala, status, matricula,
                id_weon, id_huawei, id_telefonia, softphone_number,
                telefonia_account, organizacao_telefonia, auditavel,
                tipo_agente, status_telefonia, atualizado_em, oficial
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
            RETURNING id
            """,
            (
                nome.strip(),
                supervisor,
                setor,
                escala,
                status,
                matricula,
                id_weon,
                id_huawei,
                id_telefonia,
                softphone_number,
                telefonia_account,
                organizacao_telefonia,
                auditavel_value,
                tipo_agente,
                status_telefonia,
                oficial,
            ),
        )
        new_id = extract_returning_id(cursor.fetchone())
        snapshot = _snapshot_colaborador(cursor, new_id)
        _log_colaborador_audit(
            cursor,
            acao="create",
            entity_id=new_id,
            payload_antes=None,
            payload_depois=snapshot,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return new_id
    finally:
        conn.close()


def update_colaborador(
    get_connection: ConnectionFactory,
    colaborador_id: int,
    nome: str,
    supervisor: str = "",
    setor: str = "",
    escala: str = "",
    status: str = "ATIVO",
    matricula: str = "",
    id_weon: str = "",
    id_huawei: str = "",
    id_telefonia: str = "",
    softphone_number: str = "",
    telefonia_account: str = "",
    organizacao_telefonia: str = "",
    tipo_agente: str = "",
    status_telefonia: str = "",
    auditavel: Optional[bool] = None,
    *,
    alterado_por: str = "system",
    motivo: Optional[str] = None,
    origem: str = "api",
) -> bool:
    """Atualiza um colaborador existente pelo `colaborador_id` e registra a mudança.

    Sobrescreve todos os campos do cadastro (formata nome, canonicaliza setor, coage
    ids e deriva `auditavel`). A trilha em `colaboradores_audit_log` só é gravada se
    o snapshot antes/depois realmente mudou (evita ruído em re-saves idênticos).
    Os keyword-only `alterado_por`/`motivo`/`origem` identificam a origem da mudança.

    Retorna True se a linha foi atualizada (rowcount > 0), False caso contrário.
    Efeito colateral: UPDATE em `colaboradores`, possível INSERT no audit log e commit.
    """
    nome = format_pt_br_name(nome.strip())
    setor = _normalize_operator_sector(setor, escala, organizacao_telefonia)
    id_huawei, id_telefonia = _coerce_huawei_and_telefonia_ids(id_huawei, id_telefonia)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        auditavel_value = _coerce_auditavel(auditavel, status)
        snapshot_before = _snapshot_colaborador(cursor, colaborador_id)
        cursor.execute(
            """
            UPDATE colaboradores
            SET nome = %s, supervisor = %s, setor = %s, escala = %s, status = %s,
                auditavel = %s, matricula = %s, id_weon = %s, id_huawei = %s, id_telefonia = %s,
                softphone_number = %s, telefonia_account = %s,
                organizacao_telefonia = %s, tipo_agente = %s,
                status_telefonia = %s, atualizado_em = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (
                nome.strip(),
                supervisor,
                setor,
                escala,
                status,
                auditavel_value,
                matricula,
                id_weon,
                id_huawei,
                id_telefonia,
                softphone_number,
                telefonia_account,
                organizacao_telefonia,
                tipo_agente,
                status_telefonia,
                colaborador_id,
            ),
        )
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
            SET nome = %s, supervisor = %s, setor = %s, matricula = %s,
                turno_operacao = %s, huawei = %s, weon = %s, status_base = %s,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE colaborador_id = %s
            """,
            (
                nome.strip(),
                supervisor,
                setor,
                matricula,
                escala,
                id_huawei,
                id_weon,
                status,
                colaborador_id,
            ),
        )
        updated = cursor.rowcount > 0
        if updated:
            snapshot_after = _snapshot_colaborador(cursor, colaborador_id)
            # Loga apenas se algo mudou de fato (evita ruido em re-saves identicos)
            if snapshot_before != snapshot_after:
                _log_colaborador_audit(
                    cursor,
                    acao="update",
                    entity_id=colaborador_id,
                    payload_antes=snapshot_before,
                    payload_depois=snapshot_after,
                    alterado_por=alterado_por,
                    motivo=motivo,
                    origem=origem,
                )
        conn.commit()
        return updated
    finally:
        conn.close()


def delete_colaborador(
    get_connection: ConnectionFactory,
    operador_id: int,
    *,
    alterado_por: str = "system",
    motivo: Optional[str] = None,
    origem: str = "api",
) -> bool:
    """Remove um colaborador e todos os dados dependentes, em cascata transacional.

    Apaga em cadeia tudo que aponta para o operador: arquivos salvos, feedbacks de
    gestor e audits vinculados, cadeia de contatos do fechamento, e desvincula
    (`colaborador_id = NULL`) o layout de operadores do fechamento. Por fim deleta a
    linha de `colaboradores` e registra a remoção no audit log (com o snapshot
    anterior). Os keyword-only `alterado_por`/`motivo`/`origem` identificam a origem.

    Retorna True se o colaborador foi deletado. Em erro faz rollback, loga e
    relança. Efeito colateral: múltiplos DELETE/UPDATE + commit (ou rollback).
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        snapshot_before = _snapshot_colaborador(cursor, operador_id)

        # Encontra audits ligados a este operador
        cursor.execute("SELECT id FROM audits WHERE colaborador_id = %s", (operador_id,))
        audit_ids = [row[0] for row in cursor.fetchall()]

        if audit_ids:
            # Para cada audit_id, deleta dados dependentes
            format_strings = ','.join(['%s'] * len(audit_ids))
            cursor.execute(f"DELETE FROM arquivos_salvos WHERE audit_id IN ({format_strings})", tuple(audit_ids))
            cursor.execute(f"DELETE FROM gestor_feedbacks WHERE audit_id IN ({format_strings})", tuple(audit_ids))
            cursor.execute(f"DELETE FROM audits WHERE id IN ({format_strings})", tuple(audit_ids))

        cursor.execute("DELETE FROM fechamento_cadeia_contatos WHERE colaborador_id = %s", (operador_id,))

        # O fechamento deve refletir apenas colaboradores cadastrados. A FK do
        # schema atual ja faz ON DELETE SET NULL, mas este UPDATE mantem o
        # comportamento correto tambem em bancos que tenham sido criados antes
        # da constraint atual: a linha historica fica no layout, porem some da
        # consulta porque nao aponta mais para um colaborador existente.
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
               SET colaborador_id = NULL,
                   atualizado_em = CURRENT_TIMESTAMP
             WHERE colaborador_id = %s
            """,
            (operador_id,),
        )

        cursor.execute("DELETE FROM colaboradores WHERE id = %s", (operador_id,))
        deleted = cursor.rowcount > 0
        if deleted and snapshot_before is not None:
            _log_colaborador_audit(
                cursor,
                acao="delete",
                entity_id=operador_id,
                payload_antes=snapshot_before,
                payload_depois=None,
                alterado_por=alterado_por,
                motivo=motivo,
                origem=origem,
            )
        conn.commit()
        return deleted
    except Exception as exc:
        conn.rollback()
        import logging
        logging.getLogger(__name__).error("Erro ao deletar colaborador %s: %s", operador_id, exc)
        raise
    finally:
        conn.close()


def bulk_apply_colaborador_action(
    get_connection: ConnectionFactory,
    colaborador_ids: list[int],
    action: str,
) -> int:
    """Aplica uma ação em lote (status/auditável) a vários colaboradores de uma vez.

    `action` deve ser uma de: "activate"/"enable_audit" (ATIVO + auditável) ou
    "inactivate"/"disable_audit" (INATIVO + não-auditável); qualquer outro valor
    levanta `ValueError`. Ids são deduplicados e filtrados (> 0); lista vazia retorna
    0 sem tocar o banco.

    Retorna a quantidade de linhas atualizadas (rowcount). Efeito colateral: UPDATE
    em `colaboradores` (não grava audit log por item) + commit.
    """
    normalized_ids = sorted({int(item) for item in colaborador_ids if int(item) > 0})
    if not normalized_ids:
        return 0

    if action == "activate":
        assignments = "status = 'ATIVO', auditavel = 1, atualizado_em = CURRENT_TIMESTAMP"
    elif action == "inactivate":
        assignments = "status = 'INATIVO', auditavel = 0, atualizado_em = CURRENT_TIMESTAMP"
    elif action == "enable_audit":
        assignments = "status = 'ATIVO', auditavel = 1, atualizado_em = CURRENT_TIMESTAMP"
    elif action == "disable_audit":
        assignments = "status = 'INATIVO', auditavel = 0, atualizado_em = CURRENT_TIMESTAMP"
    else:
        raise ValueError("acao de lote invalida")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE colaboradores SET {assignments} WHERE id = ANY(%s)",
            (normalized_ids,),
        )
        layout_status = "ATIVO" if action in ("activate", "enable_audit") else "INATIVO"
        cursor.execute(
            """
            UPDATE fechamento_layout_operadores
            SET status_base = %s, atualizado_em = CURRENT_TIMESTAMP
            WHERE colaborador_id = ANY(%s)
            """,
            (layout_status, normalized_ids),
        )
        updated = cursor.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


def get_colaboradores_lookup(
    get_connection: ConnectionFactory,
    supervisor: Optional[str] = None,
    escala: Optional[str] = None,
    sector_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """Lista operadores auditáveis para seleção na UI, com filtros e busca textual.

    Filtra colaboradores ATIVOS e auditáveis; aplica filtros de `supervisor`/`escala`
    no SQL e de `sector_id` em memória (via `_matches_operador_sector`). `search` é
    casada (acento-insensível) contra nome, ids, matrícula, supervisor e escala.
    Resultados são deduplicados por nome+preferredId, ordenados por nome e truncados
    em `limit`.

    Retorna uma lista de dicts camelCase para a UI (`name`, `preferredId`, `escala`,
    `sectorId`, `displaySector`, ids, `auditavel`, ...). Efeito colateral: leitura no
    banco.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT
                nome, supervisor, escala, setor, matricula, id_huawei,
                id_telefonia, softphone_number, telefonia_account,
                organizacao_telefonia, tipo_agente, status, status_telefonia, auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND nome IS NOT NULL
              AND nome != ''
        """
        params = []

        if supervisor:
            query += " AND supervisor = %s"
            params.append(supervisor)
        if escala:
            query += " AND escala = %s"
            params.append(escala)

        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    normalized_search = _normalize_lookup_text(search or "")
    operators: list[dict] = []
    seen_keys: set[str] = set()

    for row in rows:
        if not _is_auditable_row(row):
            continue
        if _is_removed_operator_row(row):
            continue

        resolved_setor = _normalize_operator_sector(
            row["setor"] or "",
            row["escala"] or "",
            row["organizacao_telefonia"] or "",
        ) or _map_organizacao_telefonia_to_sector(row["organizacao_telefonia"] or "")
        resolved_escala = str(row["escala"] or "").strip() or str(row["organizacao_telefonia"] or "").strip()

        if not _matches_operador_sector(sector_id, resolved_setor, resolved_escala):
            continue

        preferred_id, preferred_id_source = _pick_preferred_operator_id(row)
        searchable_values = [
            row["nome"],
            preferred_id,
            row["matricula"],
            row["id_huawei"],
            row["id_telefonia"],
            row["softphone_number"],
            row["telefonia_account"],
            row["supervisor"],
            resolved_escala,
        ]
        if normalized_search and not any(
            normalized_search in _normalize_lookup_text(value)
            for value in searchable_values
            if value
        ):
            continue

        key = f"{_normalize_lookup_text(row['nome'])}|{preferred_id}"
        if key in seen_keys:
            continue
        seen_keys.add(key)

        resolved_huawei_id, resolved_telefonia_id = _coerce_huawei_and_telefonia_ids(
            row["id_huawei"],
            row["id_telefonia"],
        )
        operators.append(
            {
                "name": str(row["nome"] or "").strip(),
                "preferredId": preferred_id,
                "preferredIdSource": preferred_id_source,
                "supervisor": str(row["supervisor"] or "").strip(),
                "escala": resolved_escala,
                "sectorId": _normalize_lookup_text(resolved_setor),
                "displaySector": resolved_setor,
                "matricula": str(row["matricula"] or "").strip(),
                "idHuawei": resolved_huawei_id,
                "idTelefonia": resolved_telefonia_id,
                "softphoneNumber": str(row["softphone_number"] or "").strip(),
                "telefoniaAccount": str(row["telefonia_account"] or "").strip(),
                "organizacaoTelefonia": str(row["organizacao_telefonia"] or "").strip(),
                "tipoAgente": str(row["tipo_agente"] or "").strip(),
                "statusTelefonia": str(row["status_telefonia"] or "").strip(),
                "auditavel": _is_auditable_row(row),
            }
        )

    operators.sort(key=lambda item: (item["name"].lower(), item["preferredId"]))
    return operators[: max(1, limit)]


def get_colaboradores_para_prompt(
    get_connection: ConnectionFactory,
    supervisor: Optional[str] = None,
    escala: Optional[str] = None,
    sector_id: Optional[str] = None,
) -> list[str]:
    """Retorna os nomes de colaboradores auditáveis para injetar no prompt da IA.

    Filtra ATIVOS e auditáveis (com filtros opcionais de `supervisor`/`escala` no SQL
    e de `sector_id` em memória), descarta linhas removidas, e retorna apenas os
    nomes — ordenados e sem duplicatas. Lista usada para ancorar a identificação do
    operador na avaliação. Efeito colateral: leitura no banco.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT DISTINCT nome, supervisor, escala, setor, auditavel
            FROM colaboradores
            WHERE status = 'ATIVO'
              AND COALESCE(auditavel, 1) = 1
              AND nome IS NOT NULL
              AND nome != ''
        """
        params = []

        if supervisor:
            query += " AND supervisor = %s"
            params.append(supervisor)
        if escala:
            query += " AND escala = %s"
            params.append(escala)

        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    nomes_filtrados = [
        str(row["nome"]).strip()
        for row in rows
        if not _is_removed_operator_row(row)
        and _is_auditable_row(row)
        and _matches_operador_sector(
            sector_id,
            _normalize_operator_sector(row["setor"] or "", row["escala"] or ""),
            row["escala"] or "",
        )
    ]
    return sorted(dict.fromkeys(nome for nome in nomes_filtrados if nome))
