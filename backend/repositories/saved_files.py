import json
from datetime import datetime
from typing import Callable, Optional, Any

from db.domain_constants import AUDIT_STATUS_DISCARDED
from repositories.common import extract_returning_id, get_row_value, strip_json_nul

ConnectionFactory = Callable[[], Any]


def _json_dumps(value):
    # strip_json_nul: U+0000 quebraria o cast metadata_json::jsonb na listagem.
    return strip_json_nul(json.dumps(value)) if value is not None else None


def _json_loads(value, default=None):
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def save_arquivo(
    get_connection: ConnectionFactory,
    tipo: str,
    conteudo: str,
    arquivo: str = "",
    audit_id: Optional[int] = None,
    operator_name: str = "",
    sector_id: str = "",
    alert_label: str = "",
    score: Optional[float] = None,
    metadata: Optional[dict] = None,
    criado_por: str = "",
    data_analise: Optional[str] = None,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO arquivos_salvos
                (tipo, conteudo, arquivo, data_analise, audit_id,
                 operator_name, sector_id, alert_label, score, metadata_json, criado_por)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tipo,
                conteudo,
                arquivo,
                data_analise or datetime.now().isoformat(),
                audit_id,
                operator_name,
                sector_id,
                alert_label,
                score,
                _json_dumps(metadata or {}),
                criado_por,
            ),
        )
        new_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return new_id
    finally:
        conn.close()


def list_arquivos_salvos(
    get_connection: ConnectionFactory,
    limit: int = 100,
    offset: int = 0,
    tipo: Optional[str] = None,
    include_audits: bool = True,
) -> list[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT
                a.id,
                a.tipo,
                LEFT(COALESCE(a.conteudo, ''), 800) AS conteudo_preview,
                a.arquivo,
                a.data_analise,
                a.audit_id,
                a.operator_name,
                a.sector_id,
                a.alert_label,
                a.score,
                a.criado_por,
                jsonb_strip_nulls(
                    jsonb_build_object(
                        'summary', NULLIF(meta.metadata ->> 'summary', ''),
                        'ai_feedback', NULLIF(meta.metadata ->> 'ai_feedback', ''),
                        'score', meta.metadata -> 'score',
                        'maxPossibleScore', meta.metadata -> 'maxPossibleScore',
                        'source_type', NULLIF(meta.metadata ->> 'source_type', ''),
                        'timestamp', NULLIF(meta.metadata ->> 'timestamp', ''),
                        'audio_date', NULLIF(meta.metadata ->> 'audio_date', ''),
                        'operator_id', COALESCE(
                            NULLIF(meta.metadata ->> 'operator_id', ''),
                            NULLIF(meta.metadata ->> 'operatorId', ''),
                            NULLIF(meta.metadata ->> 'operator_telefonia', ''),
                            NULLIF(meta.metadata ->> 'operatorTelefonia', ''),
                            NULLIF(meta.metadata ->> 'id_telefonia', ''),
                            NULLIF(meta.metadata ->> 'idTelefonia', ''),
                            NULLIF(meta.metadata #>> '{operator,operator_id}', ''),
                            NULLIF(meta.metadata #>> '{operator,operatorId}', '')
                        )
                    )
                )::text AS metadata_summary_json,
                au.status as audit_status
            FROM arquivos_salvos a
            LEFT JOIN audits au ON a.audit_id = au.id
            LEFT JOIN LATERAL (
                SELECT
                    CASE
                        WHEN COALESCE(TRIM(a.metadata_json), '') = '' THEN '{}'::jsonb
                        -- jsonb nao aceita o escape de NUL no JSON; remover (chr(92)+'u0000'
                        -- = a sequencia \\u0000) evita que 1 linha corrompida derrube a lista
                        -- inteira (incidente prod 2026-06-15, arquivo_salvo id=206).
                        ELSE replace(a.metadata_json, chr(92) || 'u0000', '')::jsonb
                    END AS metadata
            ) meta ON TRUE
        """
        params: list = []
        conditions: list[str] = []

        # Filtro de tipo
        if tipo:
            conditions.append("LOWER(TRIM(COALESCE(a.tipo, ''))) = LOWER(TRIM(%s))")
            params.append(tipo)
        elif not include_audits:
            conditions.append("LOWER(TRIM(COALESCE(a.tipo, ''))) <> 'auditoria'")

        # Blindagem: NUNCA listar arquivos vinculados a auditorias descartadas
        conditions.append("(au.status IS NULL OR au.status <> %s)")
        params.append(AUDIT_STATUS_DISCARDED)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # `data_analise` is the call/audit date. For automated Huawei audits this
        # can be D-1, so order by saved row insertion to show new arrivals first.
        query += " ORDER BY a.id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [
            {
                "id": row["id"],
                "tipo": row["tipo"],
                "conteudo": row["conteudo_preview"],
                "arquivo": row["arquivo"],
                "data_analise": row["data_analise"],
                "audit_id": row["audit_id"],
                "operator_name": row["operator_name"],
                "sector_id": row["sector_id"],
                "alert_label": row["alert_label"],
                "score": row["score"],
                "metadata": _json_loads(row["metadata_summary_json"], {}),
                "criado_por": row["criado_por"],
                "audit_status": row["audit_status"],
                "detail_loaded": False,
            }
            for row in rows
        ]
    finally:
        conn.close()


def get_arquivo_salvo(get_connection: ConnectionFactory, arquivo_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.*, au.status AS audit_status
            FROM arquivos_salvos a
            LEFT JOIN audits au ON a.audit_id = au.id
            WHERE a.id = %s
            """,
            (arquivo_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        metadata_json = get_row_value(row, "metadata_json")
        return {
            "id": get_row_value(row, "id"),
            "tipo": get_row_value(row, "tipo", ""),
            "conteudo": get_row_value(row, "conteudo", ""),
            "arquivo": get_row_value(row, "arquivo", ""),
            "data_analise": get_row_value(row, "data_analise"),
            "audit_id": get_row_value(row, "audit_id"),
            "operator_name": get_row_value(row, "operator_name", ""),
            "sector_id": get_row_value(row, "sector_id", ""),
            "alert_label": get_row_value(row, "alert_label", ""),
            "score": get_row_value(row, "score"),
            "metadata": _json_loads(metadata_json, {}),
            "criado_por": get_row_value(row, "criado_por", ""),
            "audit_status": get_row_value(row, "audit_status"),
            "detail_loaded": True,
        }
    finally:
        conn.close()


def update_arquivo_salvo(
    get_connection: ConnectionFactory,
    arquivo_id: int,
    conteudo: str,
    score: Optional[float] = None,
    metadata: Optional[dict] = None,
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if metadata is not None:
            cursor.execute(
                "UPDATE arquivos_salvos SET conteudo = %s, score = %s, metadata_json = %s WHERE id = %s",
                (conteudo, score, _json_dumps(metadata), arquivo_id),
            )
        else:
            cursor.execute(
                "UPDATE arquivos_salvos SET conteudo = %s WHERE id = %s",
                (conteudo, arquivo_id),
            )
        rowcount = getattr(cursor, "rowcount", None)
        updated = True if rowcount is None or type(rowcount) is not int else rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def delete_arquivo_salvo(get_connection: ConnectionFactory, arquivo_id: int) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM arquivos_salvos WHERE id = %s", (arquivo_id,))
        rowcount = getattr(cursor, "rowcount", None)
        deleted = True if rowcount is None else rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def get_arquivo_by_audit_id(get_connection: ConnectionFactory, audit_id: int) -> Optional[dict]:
    """Find an arquivo linked to a specific audit_id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM arquivos_salvos WHERE audit_id = %s LIMIT 1", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return None
        metadata_json = get_row_value(row, "metadata_json")
        return {
            "id": get_row_value(row, "id"),
            "tipo": get_row_value(row, "tipo", ""),
            "conteudo": get_row_value(row, "conteudo", ""),
            "arquivo": get_row_value(row, "arquivo", ""),
            "data_analise": get_row_value(row, "data_analise"),
            "audit_id": get_row_value(row, "audit_id"),
            "operator_name": get_row_value(row, "operator_name", ""),
            "sector_id": get_row_value(row, "sector_id", ""),
            "alert_label": get_row_value(row, "alert_label", ""),
            "score": get_row_value(row, "score"),
            "metadata": _json_loads(metadata_json, {}),
            "criado_por": get_row_value(row, "criado_por", ""),
        }
    finally:
        conn.close()


def update_arquivo_by_audit_id(
    get_connection: ConnectionFactory,
    audit_id: int,
    conteudo: str,
    score: Optional[float] = None,
    metadata: Optional[dict] = None,
    arquivo: Optional[str] = None,
    data_analise: Optional[str] = None,
    criado_por: Optional[str] = None,
) -> bool:
    """Update the arquivo linked to a specific audit_id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        updates = ["conteudo = %s", "score = %s", "metadata_json = %s"]
        params = [conteudo, score, _json_dumps(metadata or {})]
        
        if arquivo is not None:
            updates.append("arquivo = %s")
            params.append(arquivo)
            
        if data_analise is not None:
            updates.append("data_analise = %s")
            params.append(data_analise)
            
        if criado_por is not None and criado_por.strip() != "":
            updates.append("criado_por = %s")
            params.append(criado_por)
            
        params.append(audit_id)
        
        sql = f"""
            UPDATE arquivos_salvos
            SET {", ".join(updates)}
            WHERE audit_id = %s
        """
        
        cursor.execute(sql, params)
        rowcount = getattr(cursor, "rowcount", None)
        updated = True if rowcount is None or type(rowcount) is not int else rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def count_arquivos_salvos(
    get_connection: ConnectionFactory,
    tipo: Optional[str] = None,
    include_audits: bool = True,
) -> int:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = """
            SELECT COUNT(*)
            FROM arquivos_salvos a
            LEFT JOIN audits au ON a.audit_id = au.id
        """
        params: list = []
        conditions: list[str] = []

        if tipo:
            conditions.append("LOWER(TRIM(COALESCE(a.tipo, ''))) = LOWER(TRIM(%s))")
            params.append(tipo)
        elif not include_audits:
            conditions.append("LOWER(TRIM(COALESCE(a.tipo, ''))) <> 'auditoria'")

        # Blindagem: NUNCA contar arquivos vinculados a auditorias descartadas
        conditions.append("(au.status IS NULL OR au.status <> %s)")
        params.append(AUDIT_STATUS_DISCARDED)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        return count
    finally:
        conn.close()
