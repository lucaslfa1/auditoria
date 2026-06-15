"""Consultas (read-only) da fila de triagem (`fila_revisao_classificacao`).

Listagens e buscas da fila, incluindo o cálculo do flag `is_oficial` (operador
cadastrado e ATIVO em `colaboradores`, casado por id_huawei para origem
huawei_sync e por nome nas demais). Sem side-effects.

Extraído de `repositories/classification_review.py` (v1.3.144) sem mudança de
comportamento; os nomes seguem reexportados de
`repositories.classification_review` (e da fachada `db.database`).
"""

from datetime import datetime
from typing import Callable, Optional, Any

from db.domain_constants import (
    REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES,
    REVIEW_QUEUE_READY_STATUSES,
    REVIEW_QUEUE_STATUS_ALL,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
)
from repositories.common import (
    json_loads,
    normalize_review_status,
    normalize_sector_id as _normalize_sector_id,
)
from repositories.classification_review_helpers import _normalize_metadata_value


ConnectionFactory = Callable[[], Any]


def listar_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    limit: Optional[int] = None,
    status: Optional[str] = REVIEW_QUEUE_STATUS_PENDING,
    sector_id: Optional[str] = None,
    origem: Optional[str] = None,
    order_by: str = "priority",
) -> list[dict]:
    """Lista itens da fila de triagem com filtros de status/setor/origem.

    `status=ready_for_audit` tem regra especial: além dos statuses prontos,
    inclui itens `monthly_capped` de períodos ANTERIORES (a trava de cota
    mensal expira na virada do mês e o item volta a ser elegível).
    `status=pending` unifica auto e manual na mesma lista (v1.3.92).
    """
    status_normalizado = normalize_review_status(status)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        filtros = []
        params: list = []

        if status_normalizado == REVIEW_QUEUE_STATUS_READY_FOR_AUDIT:
            current_period = datetime.now().strftime("%Y-%m")
            filtros.append(
                """
                (
                    status = ANY(%s)
                    OR (
                        status = %s
                        AND COALESCE((metadata_json::jsonb ->> 'monthly_cap_period'), '') <> %s
                    )
                )
                """
            )
            params.extend(
                [
                    list(REVIEW_QUEUE_READY_STATUSES),
                    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
                    current_period,
                ]
            )
        elif status_normalizado == REVIEW_QUEUE_STATUS_PENDING:
            # Fluxo unificado (v1.3.92): auto e manual aparecem juntos em Triagem.
            # A distincao visual fica no badge "Auto" do frontend, que olha
            # metadata.is_manual + metadata.origem. Antes existia um NOT clause
            # que escondia huawei_sync com classification_status='pending' ate a
            # fase 2 rodar, mas Lucas pediu fluxo unico.
            filtros.append(
                """
                (
                    status = %s
                    OR status = ANY(%s)
                    OR (
                        status = 'downloaded'
                        AND COALESCE(metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                    )
                )
                """
            )
            params.extend(
                [
                    status_normalizado,
                    [
                        item
                        for item in REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES
                        if item != REVIEW_QUEUE_STATUS_PENDING
                    ],
                ]
            )
        elif status_normalizado != REVIEW_QUEUE_STATUS_ALL:
            filtros.append("status = %s")
            params.append(status_normalizado)
        if sector_id:
            filtros.append("COALESCE(setor_previsto, '') = %s")
            params.append(_normalize_sector_id(sector_id) or "")
        if origem:
            filtros.append("metadata_json::jsonb ->> 'origem' = %s")
            params.append(origem)

        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""

        if order_by == "recent":
            order_clause = "ORDER BY atualizado_em DESC, id DESC"
        else:
            order_clause = "ORDER BY CASE prioridade WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, atualizado_em DESC, id DESC"

        limit_clause = "LIMIT %s" if limit is not None else ""

        query = f"""
            SELECT f.*,
                   official_by_huawei.nome AS official_operator_name,
                   official_by_huawei.id_huawei AS official_operator_id_huawei,
                   CASE
                       WHEN COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                           THEN official_by_huawei.id_huawei IS NOT NULL
                       ELSE EXISTS(SELECT 1
                                      FROM colaboradores c
                                      WHERE LOWER(TRIM(c.nome)) = LOWER(TRIM(COALESCE(NULLIF(f.operador_previsto, ''), f.metadata_json::jsonb ->> 'operator_name')))
                                         AND c.status = 'ATIVO'
                                    )
                   END as is_oficial
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.nome, c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                ORDER BY
                    CASE WHEN UPPER(c.status) = 'ATIVO' THEN 0 ELSE 1 END,
                    CASE WHEN COALESCE(c.auditavel, 1) = 1 THEN 0 ELSE 1 END,
                    c.atualizado_em DESC NULLS LAST,
                    c.nome
                LIMIT 1
            ) official_by_huawei ON TRUE
            {where_clause}
            {order_clause}
            {limit_clause}
        """
        if limit is not None:
            params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    items: list[dict] = []
    for row in rows:
        metadata = json_loads(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        official_operator_name = row["official_operator_name"] if "official_operator_name" in row.keys() else None
        official_operator_id_huawei = (
            row["official_operator_id_huawei"] if "official_operator_id_huawei" in row.keys() else None
        )
        operator_name = (
            official_operator_name
            or row["operador_previsto"]
            or metadata.get("operator_name")
            or metadata.get("operator_name_real")
            or metadata.get("huawei_operator_name")
        )
        operator_id = (
            official_operator_id_huawei
            or metadata.get("operator_id_huawei_real")
            or metadata.get("id_huawei")
            or metadata.get("operator_id")
            or metadata.get("operator_matricula")
            or metadata.get("matricula")
            or metadata.get("huawei_agent_id")
        )
        items.append(
            {
                "id": row["id"],
                "input_hash": row["input_hash"],
                "nome_arquivo": row["nome_arquivo"],
                "setor_previsto": row["setor_previsto"] or metadata.get("operator_sector_id"),
                "alerta_previsto": row["alerta_previsto"],
                "confianca": row["confianca"],
                "operador_previsto": row["operador_previsto"],
                "operator_name": operator_name,
                "operator_id": operator_id,
                "erro": row["erro"],
                "prioridade": row["prioridade"],
                "motivos_revisao": json_loads(row["motivos_json"], []),
                "metadata": metadata,
                "status": row["status"],
                "criado_em": row["criado_em"],
                "atualizado_em": row["atualizado_em"],
                "is_oficial": row["is_oficial"],
            }
        )
    return items


def obter_fila_revisao_classificacao_por_hash(
    get_connection: ConnectionFactory,
    input_hash: str,
) -> Optional[dict]:
    """Busca um item da fila pelo `input_hash` (chave de dedupe da gravação).

    Inclui o flag `is_oficial` calculado (operador cadastrado e ATIVO em
    `colaboradores`) com a mesma regra da listagem.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # is_oficial replicado de listar_fila_revisao_classificacao: huawei_sync
        # casa por id_huawei; demais origens casam por nome do operador.
        cursor.execute(
            """
            SELECT f.*,
                   CASE
                       WHEN COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                           THEN official_by_huawei.id_huawei IS NOT NULL
                       ELSE EXISTS(SELECT 1
                                      FROM colaboradores c
                                      WHERE LOWER(TRIM(c.nome)) = LOWER(TRIM(COALESCE(NULLIF(f.operador_previsto, ''), f.metadata_json::jsonb ->> 'operator_name')))
                                         AND c.status = 'ATIVO'
                                    )
                   END as is_oficial
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                ORDER BY
                    CASE WHEN UPPER(c.status) = 'ATIVO' THEN 0 ELSE 1 END,
                    CASE WHEN COALESCE(c.auditavel, 1) = 1 THEN 0 ELSE 1 END,
                    c.atualizado_em DESC NULLS LAST,
                    c.nome
                LIMIT 1
            ) official_by_huawei ON TRUE
            WHERE f.input_hash = %s
            LIMIT 1
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "input_hash": row["input_hash"],
            "nome_arquivo": row["nome_arquivo"],
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "confianca": row["confianca"],
            "operador_previsto": row["operador_previsto"],
            "erro": row["erro"],
            "prioridade": row["prioridade"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
            "is_oficial": row["is_oficial"],
        }
    finally:
        conn.close()


def obter_fila_revisao_classificacao_por_auditoria(
    get_connection: ConnectionFactory,
    audit_id: int,
    audit_input_hash: Optional[str] = None,
) -> Optional[dict]:
    """Localiza o item da fila vinculado a uma auditoria já criada.

    O vínculo vive em `metadata.audit_id` / `metadata.audit_input_hash`
    (gravados quando a auditoria nasce do item). Retorna o mais recente.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE COALESCE((metadata_json::jsonb ->> 'audit_id'), '') = %s
               OR (
                    %s <> ''
                    AND COALESCE((metadata_json::jsonb ->> 'audit_input_hash'), '') = %s
               )
            ORDER BY atualizado_em DESC, id DESC
            LIMIT 1
            """,
            (str(audit_id), str(audit_input_hash or ""), str(audit_input_hash or "")),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "input_hash": row["input_hash"],
            "nome_arquivo": row["nome_arquivo"],
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "confianca": row["confianca"],
            "operador_previsto": row["operador_previsto"],
            "erro": row["erro"],
            "prioridade": row["prioridade"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }
    finally:
        conn.close()


def listar_paths_audio_classificado_fila_revisao(
    get_connection: ConnectionFactory,
) -> list[str]:
    """Lista os paths de áudio classificado (`metadata.classified_audio_path`).

    Usado pela limpeza de storage para saber quais arquivos ainda têm dono.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT metadata_json
            FROM fila_revisao_classificacao
            WHERE metadata_json IS NOT NULL
              AND metadata_json != ''
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    paths: list[str] = []
    for row in rows:
        metadata = _normalize_metadata_value(row["metadata_json"])
        path = str(metadata.get("classified_audio_path") or "").strip()
        if path:
            paths.append(path)
    return paths
