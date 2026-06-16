"""Export para fechamento/BI e listagens de auditorias (read-only).

Subdomínio extraído de `repositories/audits.py` (v1.3.167) sem mudança de
comportamento. `get_audits_for_export` monta o dict consumido pelo FECHAMENTO/BI
— as chaves e a semântica são CONTRATO, não alterar. `list_pending_dispatch_audits`
lista auditorias paradas em `awaiting_pair`; `_resolve_audio_hash_fallback`
resolve metadata de áudio por `input_hash` (somente leitura).

Os nomes seguem reexportados de `repositories.audits` (a fachada `db.database` e
`routers/review` os acessam como atributo de módulo; `get_audit_by_id`, que fica
em audits.py, usa `_resolve_audio_hash_fallback`). Módulo-folha: importa só de
common/domain_constants/audits_helpers — sem ciclo com audits.py.
"""

from typing import Any, Callable, Optional

from db.domain_constants import AUDIT_STATUS_DISCARDED
from repositories.common import (
    CALL_QUALITY_SCOPE,
    get_audit_scope,
    json_loads,
    normalize_audit_status,
)
from repositories.audits_helpers import _normalize_sector_id


ConnectionFactory = Callable[[], Any]


def _resolve_audio_hash_fallback(cursor, rows) -> dict:
    """Batch-resolve audio metadata para linhas sem `audio_storage_path` via `input_hash`.

    Retorna {audit_id: {"audio_mime_type", "audio_size_bytes"}} apenas para as
    auditorias que conseguem recuperar áudio através de outra auditoria que
    compartilha o mesmo `input_hash`. Operação é somente leitura — a persistência
    do backfill acontece quando o áudio é efetivamente servido, via
    `get_audit_media_record_by_id`.
    """
    hashes_to_resolve: dict = {}
    for row in rows:
        keys = row.keys()
        has_path = "audio_storage_path" in keys and bool(row["audio_storage_path"])
        if has_path:
            continue
        input_hash = row["input_hash"] if "input_hash" in keys else None
        if not input_hash:
            continue
        hashes_to_resolve.setdefault(input_hash, []).append(row["id"])

    if not hashes_to_resolve:
        return {}

    placeholders = ", ".join("%s" for _ in hashes_to_resolve)
    cursor.execute(
        f"""
        SELECT DISTINCT ON (input_hash)
               input_hash, audio_mime_type, audio_size_bytes
        FROM audits
        WHERE input_hash IN ({placeholders})
          AND COALESCE(audio_storage_path, '') <> ''
        ORDER BY input_hash, id ASC
        """,
        tuple(hashes_to_resolve.keys()),
    )
    resolved = {r["input_hash"]: r for r in cursor.fetchall()}

    out: dict = {}
    for input_hash, audit_ids in hashes_to_resolve.items():
        src = resolved.get(input_hash)
        if not src:
            continue
        for aid in audit_ids:
            out[aid] = {
                "audio_mime_type": src["audio_mime_type"] if "audio_mime_type" in src.keys() else None,
                "audio_size_bytes": src["audio_size_bytes"] if "audio_size_bytes" in src.keys() else None,
            }
    return out


def get_audits_for_export(
    get_connection: ConnectionFactory,
    month: int = None,
    year: int = None,
    supervisor: str = None,
    escala: str = None,
    sector_id: str = None,
    operator_name: str = None,
    statuses: Optional[list[str]] = None,
    limit: int = None,
    skip: int = 0,
    max_per_operator: Optional[int] = None,
) -> list[dict]:
    """Lista auditorias para o fechamento mensal, painel do supervisor e revisão.

    ⚠️ CONTRATO BI: o fechamento (DOCX/BI) consome o dict retornado aqui.
    Chaves, labels e semântica dos campos são contrato estável — NÃO alterar
    formato sem alinhamento (ver memória "Fechamento intocável").

    Filtros (todos opcionais, combináveis):
        month/year: mês-calendário sobre COALESCE(audit_date, timestamp).
        supervisor/escala: comparação exata case-insensitive via JOIN com
            `colaboradores`.
        sector_id: setor normalizado (minúsculas).
        operator_name: LIKE parcial case-insensitive.
        statuses: lista de status; sem ela, descartadas ficam FORA por default.
        max_per_operator: limita a N auditorias mais recentes por operador
            (ROW_NUMBER particionado por identidade do operador).
        limit/skip: paginação aplicada após os demais filtros.

    Pós-processamento em Python: deduplicação por id (o JOIN com
    `colaboradores` pode multiplicar linhas), filtro pelo escopo de qualidade
    (`call_quality` — documentos ficam fora do fechamento), resolução de
    áudio disponível (caminho próprio ou fallback por hash, somente leitura)
    e anexo do feedback de gestor quando existir.

    Obs.: `details` sai como JSON cru (string) e `transcription` desserializada
    — assimetria mantida porque os consumidores dependem desse formato.
    """
    conn = get_connection()
    try:

        cursor = conn.cursor()

        base_select = """
            SELECT a.*, o.supervisor, o.escala, f.gestor_nome, f.feedback_texto, f.pontos_melhoria, f.criado_em as feedback_em
        """
        base_from = """
            FROM audits a
            LEFT JOIN colaboradores o ON (
                (
                    a.operator_id IS NOT NULL AND a.operator_id != ''
                    AND o.id_telefonia = a.operator_id
                )
                OR (
                    a.operator_name IS NOT NULL AND a.operator_name != ''
                    AND o.nome = a.operator_name
                )
            )
            LEFT JOIN gestor_feedbacks f ON f.audit_id = a.id
            WHERE 1=1
        """
        where_clauses = ""
        params: list = []

        if month and year:
            date_start = f"{year:04d}-{month:02d}-01"
            date_end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
            where_clauses += " AND COALESCE(a.audit_date, a.timestamp) >= %s AND COALESCE(a.audit_date, a.timestamp) < %s "
            params.extend([date_start, date_end])

        if supervisor:
            where_clauses += " AND LOWER(TRIM(COALESCE(o.supervisor, ''))) = %s "
            params.append(supervisor.strip().lower())

        if escala:
            where_clauses += " AND LOWER(TRIM(COALESCE(o.escala, ''))) = %s "
            params.append(escala.strip().lower())

        if sector_id:
            where_clauses += " AND a.sector_id = %s "
            params.append(_normalize_sector_id(sector_id))

        if operator_name:
            where_clauses += " AND LOWER(TRIM(COALESCE(a.operator_name, ''))) LIKE %s "
            params.append(f"%%{operator_name.strip().lower()}%%")

        normalized_statuses = [
            normalized
            for normalized in (
                normalize_audit_status(status, default=None)
                for status in (statuses or [])
            )
            if normalized is not None
        ]
        if normalized_statuses:
            placeholders = ", ".join("%s" for _ in normalized_statuses)
            where_clauses += f" AND a.status IN ({placeholders}) "
            params.extend(normalized_statuses)
        else:
            # Sem filtro explicito, descartadas ficam fora (soft-delete).
            where_clauses += " AND COALESCE(a.status, '') <> %s "
            params.append(AUDIT_STATUS_DISCARDED)

        if max_per_operator is not None and int(max_per_operator) > 0:
            query = f"""
                WITH ranked AS (
                    {base_select},
                           ROW_NUMBER() OVER (
                               PARTITION BY LOWER(TRIM(COALESCE(NULLIF(a.operator_id, ''), a.operator_name, '')))
                               ORDER BY a.id DESC
                           ) AS rn
                    {base_from}
                    {where_clauses}
                )
                SELECT * FROM ranked
                WHERE rn <= %s
                ORDER BY id DESC
            """
            params.append(int(max_per_operator))
        else:
            query = f"{base_select}{base_from}{where_clauses} ORDER BY a.id DESC"

        if limit is not None:
            query += " LIMIT %s "
            params.append(limit)
        if skip is not None and skip > 0:
            query += " OFFSET %s "
            params.append(skip)

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        hash_fallback = _resolve_audio_hash_fallback(cursor, rows)

        seen_ids: set[int] = set()
        results: list[dict] = []
        for row in rows:
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])

            if get_audit_scope(row) != CALL_QUALITY_SCOPE:
                continue

            feedback = None
            if row["gestor_nome"]:
                feedback = {
                    "id": 0,
                    "audit_id": row["id"],
                    "gestor_nome": row["gestor_nome"],
                    "feedback_texto": row["feedback_texto"],
                    "pontos_melhoria": row["pontos_melhoria"],
                    "criado_em": row["feedback_em"],
                }

            has_audio_path = (
                "audio_storage_path" in row.keys()
                and bool(row["audio_storage_path"])
            )
            fallback = hash_fallback.get(row["id"]) if not has_audio_path else None
            audio_available = has_audio_path or fallback is not None

            if has_audio_path:
                mime_type = row["audio_mime_type"] if "audio_mime_type" in row.keys() else None
                size_bytes = row["audio_size_bytes"] if "audio_size_bytes" in row.keys() else None
            elif fallback:
                mime_type = fallback.get("audio_mime_type")
                size_bytes = fallback.get("audio_size_bytes")
            else:
                mime_type = None
                size_bytes = None

            results.append(
                # CONTRATO BI: as chaves e a semântica abaixo são consumidas pelo
                # fechamento/BI. NÃO renomear nem alterar significado (só adicionar
                # campos novos, se preciso, sem mexer nos existentes).
                {
                    "id": row["id"],                          # PK da auditoria
                    "timestamp": row["timestamp"],            # quando a auditoria foi criada
                    "operator_name": row["operator_name"],    # nome do operador auditado
                    "operator_id": row["operator_id"] or "",  # id de telefonia do operador
                    "score": row["score"],                    # nota obtida
                    "max_score": row["max_score"],            # nota máxima possível
                    "summary": row["summary"],                # resumo da avaliação
                    "details": row["details_json"],           # critérios (JSON cru — string, não desserializado aqui)
                    "transcription": json_loads(row["transcription_json"], []) if "transcription_json" in row.keys() else [],  # transcrição diarizada
                    "alert_id": row["alert_id"] if "alert_id" in row.keys() else None,        # id do alerta
                    "alert_label": row["alert_label"] if "alert_label" in row.keys() else None,  # rótulo do alerta
                    "sector_id": row["sector_id"] if "sector_id" in row.keys() else None,     # setor
                    "status": row["status"] if "status" in row.keys() else None,             # estado da auditoria
                    "contestation_reason": row["contestation_reason"] if "contestation_reason" in row.keys() else None,  # motivo da contestação
                    "contested_criteria": json_loads(row["contested_criteria"], None) if "contested_criteria" in row.keys() else None,  # critérios contestados
                    "contestation_verdict": row["contestation_verdict"] if "contestation_verdict" in row.keys() else None,  # veredito (accepted|rejected)
                    "review_defense": row["review_defense"] if "review_defense" in row.keys() else None,  # defesa técnica do auditor
                    "reviewed_by": row["reviewed_by"] if "reviewed_by" in row.keys() else None,  # quem revisou
                    "reviewed_at": row["reviewed_at"] if "reviewed_at" in row.keys() else None,  # quando revisou
                    "supervisor": row["supervisor"] or "",    # supervisor do operador (cadastro)
                    "escala": row["escala"] or "",            # escala/turno do operador (cadastro)
                    "audio_available": audio_available,       # há áudio servível
                    "audio_url": f"/api/audit/{row['id']}/audio" if audio_available else None,  # endpoint de streaming
                    "audio_mime_type": mime_type,             # mime do áudio
                    "audio_size_bytes": size_bytes,           # tamanho do áudio em bytes
                    "feedback": feedback,                     # feedback do gestor (dict) ou None
                }
            )

        return results
    finally:
        conn.close()

def list_pending_dispatch_audits(get_connection, older_than_hours: Optional[int] = None) -> list[dict]:
    """Lista auditorias paradas em `awaiting_pair` (aguardando envio ao supervisor).

    Usada pelo lembrete de despacho pendente; `older_than_hours` filtra só as
    paradas há mais tempo que o limite. Junta dados do colaborador para exibição.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT
                a.*,
                c.nome AS colaborador_nome,
                c.supervisor,
                c.setor,
                c.escala,
                c.matricula
            FROM audits a
            LEFT JOIN colaboradores c ON a.colaborador_id = c.id
            WHERE a.status = 'awaiting_pair'
        """
        
        if older_than_hours is not None:
            query += f" AND (a.timestamp::timestamp <= NOW() - INTERVAL '{older_than_hours} hours')"
            
        query += " ORDER BY a.timestamp DESC"
        
        cursor.execute(query)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
