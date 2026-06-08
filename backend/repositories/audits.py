from datetime import datetime
from typing import Callable, Optional

from db.domain_constants import (
    AUDIT_CONTESTATION_VERDICT_ACCEPTED,
    AUDIT_CONTESTATION_VERDICT_REJECTED,
    AUDIT_STATUS_AWAITING_PAIR,
    AUDIT_STATUS_APPROVED,
    AUDIT_STATUS_CONTESTATION_ACCEPTED,
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    AUDIT_STATUS_CONTESTED,
    AUDIT_STATUS_DISCARDED,
    AUDIT_STATUS_PENDING_APPROVAL,
    DEFAULT_AUDIT_STATUS,
    DEFAULT_SOURCE_TYPE,
)
from repositories.common import (
    CALL_QUALITY_SCOPE,
    derive_audit_scope,
    extract_returning_id,
    get_audit_scope,
    json_dumps,
    json_loads,
    normalize_audit_scope,
    normalize_audit_status,
    normalize_source_type,
    row_to_audit_result,
)
from schemas import AuditResult
import db.database as database

from typing import Callable, Optional, Any

ConnectionFactory = Callable[[], Any]

_REVIEW_DETAIL_STATUSES = {"pass", "fail"}


def _normalize_binary_detail_status(raw_status: object) -> str:
    status = str(raw_status or "").strip().lower()
    if status in {"pass", "na", "n/a", "pending_manual"}:
        return "pass"
    if status in {"fail", "partial"}:
        return "fail"
    raise ValueError("Status de criterio invalido.")

def _normalize_sector_id(sector_id: Optional[str]) -> Optional[str]:
    normalized = str(sector_id or "").strip().lower()
    return normalized or None


def _normalize_operator_name(operator_name: Optional[str]) -> Optional[str]:
    normalized = str(operator_name or "").strip()
    return normalized or None


def _normalize_operator_id(operator_id: Optional[str]) -> Optional[str]:
    normalized = str(operator_id or "").strip()
    return normalized or None


def get_operator_audit_counts_for_month_bulk(
    get_connection: ConnectionFactory,
    operator_keys: list[tuple[str, str]],   # [(name, id), ...]
    year: int,
    month: int,
) -> dict[tuple[str, str], int]:
    """Retorna {(name_lower, id_lower): count} para todos os operadores em UMA query."""
    if not operator_keys:
        return {}
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        date_start = f"{year:04d}-{month:02d}-01"
        date_end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
        
        # Prepara chaves normalizadas para matching
        # Usamos uma CTE VALUES para fazer join com a tabela de auditorias
        from psycopg2.extras import execute_values
        
        # Filtramos para pegar apenas auditorias do mes/ano atual que nao foram descartadas
        # e estao no escopo de qualidade.
        # Identidade e baseada em operator_id (prioridade) ou operator_name.
        
        # Para facilitar o join, normalizamos as chaves de entrada
        normalized_keys = [
            (str(name or "").strip().lower(), str(oid or "").strip().lower())
            for name, oid in operator_keys
        ]
        
        # Note: A query de contagem aqui segue a mesma logica da get_operator_audit_count_for_month
        # mas agrupa por operador.
        # Refactoring to manual VALUES building to be safer with complex joins
        values_list = ",".join(cursor.mogrify("(%s, %s)", k).decode('utf-8') for k in normalized_keys)
        
        final_query = f"""
            WITH input_keys(search_name, search_id) AS (
                VALUES {values_list}
            ),
            relevant_audits AS (
                SELECT 
                    LOWER(TRIM(COALESCE(operator_name, ''))) as op_name,
                    LOWER(TRIM(COALESCE(operator_id, ''))) as op_id,
                    CONCAT_WS(
                        '|',
                        COALESCE(NULLIF(TRIM(operator_id), ''), LOWER(TRIM(COALESCE(operator_name, '')))),
                        COALESCE(timestamp::text, ''),
                        COALESCE(alert_id, ''),
                        COALESCE(source_type, '')
                    ) as audit_uid
                FROM audits
                WHERE COALESCE(audit_date, timestamp) >= %s
                  AND COALESCE(audit_date, timestamp) < %s
                  AND COALESCE(audit_scope, %s) = %s
                  AND COALESCE(status, '') <> %s
            )
            SELECT 
                ik.search_name, 
                ik.search_id, 
                COUNT(DISTINCT ra.audit_uid)
            FROM input_keys ik
            LEFT JOIN relevant_audits ra ON (
                (ik.search_id <> '' AND ra.op_id = ik.search_id)
                OR (ik.search_id = '' AND ra.op_id = '' AND ra.op_name = ik.search_name)
            )
            GROUP BY ik.search_name, ik.search_id
        """
        
        cursor.execute(final_query, (date_start, date_end, CALL_QUALITY_SCOPE, CALL_QUALITY_SCOPE, AUDIT_STATUS_DISCARDED))

        
        results = {}
        for row in cursor.fetchall():
            results[(row[0], row[1])] = int(row[2])
        return results
    finally:
        conn.close()


def get_operator_audit_count_for_month(
    get_connection: ConnectionFactory,
    operator_name: str,
    year: int,
    month: int,
    operator_id: Optional[str] = None,
) -> int:
    """Delega para o bulk para manter consistencia."""
    counts = get_operator_audit_counts_for_month_bulk(
        get_connection, 
        [(operator_name, operator_id)], 
        year, 
        month
    )
    key = (_normalize_operator_name(operator_name).lower() if operator_name else "", 
           _normalize_operator_id(operator_id).lower() if operator_id else "")
    return counts.get(key, 0)


def get_supervisor_audit_count_for_month(
    get_connection: ConnectionFactory,
    operator_name: str,
    year: int,
    month: int,
    operator_id: Optional[str] = None,
) -> int:
    """Counts audits in the supervisor panel (excludes awaiting_pair and discarded)."""
    import calendar
    from datetime import date
    from db.domain_constants import AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_DISCARDED
    
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        op_id_norm = _normalize_operator_id(operator_id)
        op_name_norm = _normalize_operator_name(operator_name)
        
        query = """
            SELECT COUNT(*) 
            FROM audits 
            WHERE CAST(COALESCE(audit_date, timestamp) AS DATE) >= %s 
              AND CAST(COALESCE(audit_date, timestamp) AS DATE) <= %s
              AND status NOT IN (%s, %s)
              AND (
                  (TRIM(COALESCE(operator_id, '')) <> '' AND TRIM(COALESCE(operator_id, '')) = %s)
                  OR 
                  (TRIM(COALESCE(operator_id, '')) = '' AND LOWER(TRIM(COALESCE(operator_name, ''))) = LOWER(%s))
              )
        """
        cursor.execute(query, (start_date, end_date, AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_DISCARDED, op_id_norm, op_name_norm))
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()



def _resolve_open_review_queue(
    cursor: Any,
    *,
    operator_name: Optional[str],
    operator_id: Optional[str],
) -> list[dict]:
    """Find all open (awaiting_pair or pending_approval) audits for an operator."""
    import logging
    logger = logging.getLogger(__name__)

    normalized_operator_name = _normalize_operator_name(operator_name)
    normalized_operator_id = _normalize_operator_id(operator_id)

    if normalized_operator_id and normalized_operator_name:
        query = """
            SELECT id, status
            FROM audits
            WHERE (
                TRIM(COALESCE(operator_id, '')) = %s
                OR (
                    TRIM(COALESCE(operator_id, '')) = ''
                    AND LOWER(TRIM(COALESCE(operator_name, ''))) = LOWER(%s)
                )
            )
              AND status IN (%s, %s)
            ORDER BY id ASC
        """
        params = (
            normalized_operator_id,
            normalized_operator_name,
            AUDIT_STATUS_AWAITING_PAIR,
            AUDIT_STATUS_PENDING_APPROVAL,
        )
    elif normalized_operator_id:
        query = """
            SELECT id, status
            FROM audits
            WHERE TRIM(COALESCE(operator_id, '')) = %s
              AND status IN (%s, %s)
            ORDER BY id ASC
        """
        params = (
            normalized_operator_id,
            AUDIT_STATUS_AWAITING_PAIR,
            AUDIT_STATUS_PENDING_APPROVAL,
        )
    elif normalized_operator_name:
        query = """
            SELECT id, status
            FROM audits
            WHERE LOWER(TRIM(COALESCE(operator_name, ''))) = LOWER(%s)
              AND status IN (%s, %s)
            ORDER BY id ASC
        """
        params = (
            normalized_operator_name,
            AUDIT_STATUS_AWAITING_PAIR,
            AUDIT_STATUS_PENDING_APPROVAL,
        )
    else:
        return []

    cursor.execute(query, params)
    rows = cursor.fetchall()
    results = [
        {
            "id": int(row["id"]),
            "status": row["status"],
        }
        for row in rows
    ]
    logger.debug(
        "[pair-queue] _resolve_open_review_queue: operator_id=%s, operator_name=%s -> %d open audits: %s",
        normalized_operator_id, normalized_operator_name, len(results),
        [r["id"] for r in results],
    )
    return results


def rebalance_operator_review_queue(
    get_connection: ConnectionFactory,
    *,
    operator_name: Optional[str],
    operator_id: Optional[str],
) -> dict:
    """Return a read-only snapshot of the operator's open review queue.

    Historically this function automatically promoted ``awaiting_pair`` items
    to ``pending_approval`` to keep the supervisor queue at two items per
    operator. That behaviour was removed: promotion is now a manual action
    performed by the auditor through the dedicated endpoint
    ``POST /api/audits/{audit_id}/promote-to-pending-approval``.

    The function is kept (and still called from existing call sites) because
    callers rely on the snapshot of ``pending_ids`` / ``awaiting_ids``. It no
    longer mutates audit statuses.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        open_audits = _resolve_open_review_queue(
            cursor,
            operator_name=operator_name,
            operator_id=operator_id,
        )
    finally:
        conn.close()

    pending_ids = [item["id"] for item in open_audits if item["status"] == AUDIT_STATUS_PENDING_APPROVAL]
    awaiting_ids = [item["id"] for item in open_audits if item["status"] == AUDIT_STATUS_AWAITING_PAIR]

    return {
        "pending_ids": pending_ids,
        "awaiting_ids": awaiting_ids,
        "open_ids": [item["id"] for item in open_audits],
    }


def promote_audit_to_pending_approval(
    get_connection: ConnectionFactory,
    audit_id: int,
) -> dict:
    """Promote a single ``awaiting_pair`` audit to ``pending_approval``.

    Manual replacement for the auto-promotion logic previously baked into
    :func:`rebalance_operator_review_queue`. Returns the updated audit row's
    id and status, or raises ``ValueError`` if the audit is not eligible.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM audits WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")
        current_status = row[1] if not isinstance(row, dict) else row.get("status")
        if current_status != AUDIT_STATUS_AWAITING_PAIR:
            raise ValueError(
                f"Auditoria {audit_id} nao esta em '{AUDIT_STATUS_AWAITING_PAIR}' (status atual: {current_status})."
            )
        cursor.execute(
            "UPDATE audits SET status = %s WHERE id = %s AND status = %s",
            (AUDIT_STATUS_PENDING_APPROVAL, audit_id, AUDIT_STATUS_AWAITING_PAIR),
        )
        conn.commit()
    finally:
        conn.close()

    return {"audit_id": audit_id, "status": AUDIT_STATUS_PENDING_APPROVAL}


def enqueue_audit_for_supervisor_review(
    get_connection: ConnectionFactory,
    result: AuditResult,
    input_hash: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    operator_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    ai_feedback: Optional[str] = None,
    rebalance: bool = False,
) -> dict:
    audit_id = save_audit(
        get_connection,
        result,
        input_hash=input_hash,
        alert_id=alert_id,
        alert_label=alert_label,
        operator_id=operator_id,
        driver_name=driver_name,
        sector_id=sector_id,
        ai_feedback=ai_feedback,
        status=AUDIT_STATUS_AWAITING_PAIR,
    )
    if input_hash:
        try:
            source_media = get_audit_media_record_by_hash(get_connection, input_hash)
            if (
                source_media
                and int(source_media.get("id") or 0) != int(audit_id)
                and source_media.get("audio_storage_path")
            ):
                update_audit_audio_storage(
                    get_connection,
                    audit_id,
                    audio_storage_path=source_media.get("audio_storage_path") or "",
                    audio_original_filename=source_media.get("audio_original_filename") or "",
                    audio_mime_type=source_media.get("audio_mime_type") or "audio/wav",
                    audio_size_bytes=int(source_media.get("audio_size_bytes") or 0),
                )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Falha ao vincular audio persistido ao audit %s", audit_id, exc_info=True
            )

    if rebalance:
        queue_state = rebalance_operator_review_queue(
            get_connection,
            operator_name=result.operatorName,
            operator_id=operator_id or result.operatorId,
        )
        review_status = AUDIT_STATUS_PENDING_APPROVAL if audit_id in queue_state["pending_ids"] else AUDIT_STATUS_AWAITING_PAIR
    else:
        queue_state = {
            "pending_ids": [],
            "awaiting_ids": [audit_id],
            "open_ids": [audit_id],
        }
        review_status = AUDIT_STATUS_AWAITING_PAIR

    return {
        "audit_id": audit_id,
        "status": review_status,
        "pending_count": len(queue_state["pending_ids"]),
        "open_count": len(queue_state["open_ids"]),
    }


def save_audit(
    get_connection: ConnectionFactory,
    result: AuditResult,
    input_hash: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    operator_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    ai_feedback: Optional[str] = None,
    status: str = DEFAULT_AUDIT_STATUS,
    colaborador_id: Optional[int] = None,
):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        details_json = json_dumps([detail.model_dump() for detail in result.details])
        transcription_json = json_dumps([segment.model_dump() for segment in result.transcription])
        audio_quality_json = json_dumps(result.audio_quality)
        normalized_source_type = normalize_source_type(result.source_type, default=DEFAULT_SOURCE_TYPE)
        normalized_status = normalize_audit_status(status, default=DEFAULT_AUDIT_STATUS)
        audit_scope = normalize_audit_scope(
            derive_audit_scope(normalized_source_type, result.audio_quality),
            default=CALL_QUALITY_SCOPE,
        )
        normalized_sector_id = _normalize_sector_id(sector_id)
        cursor.execute(
            """
            INSERT INTO audits (
                timestamp, audit_date, operator_name, score, max_score, summary,
                details_json, transcription_json, input_hash,
                alert_id, alert_label, operator_id, driver_name, source_type, sector_id, audio_quality, audit_scope, ai_feedback, status,
                colaborador_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                result.timestamp or datetime.now().isoformat(),
                getattr(result, "audio_date", None),
                result.operatorName,
                result.score,
                result.maxPossibleScore,
                result.summary,
                details_json,
                transcription_json,
                input_hash,
                alert_id,
                alert_label,
                operator_id,
                driver_name,
                normalized_source_type,
                normalized_sector_id,
                audio_quality_json,
                audit_scope,
                ai_feedback,
                normalized_status,
                colaborador_id,
            ),
        )
        conn.commit()
        return extract_returning_id(cursor.fetchone())
    finally:
        conn.close()


def get_latest_audit_id_by_input_hash(
    get_connection: ConnectionFactory,
    input_hash: str,
) -> Optional[int]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM audits WHERE input_hash = %s ORDER BY id DESC LIMIT 1", (input_hash,))
        row = cursor.fetchone()
        if not row:
            return None
        return int(row["id"] if isinstance(row, dict) else row[0])
    finally:
        conn.close()


def _write_audit_result_fields(cursor, audit_id: int, result: AuditResult, ai_feedback: Optional[str] = None) -> None:
    details_json = json_dumps([d.model_dump() for d in result.details])
    transcription_json = json_dumps([s.model_dump() for s in result.transcription])
    audio_quality_json = json_dumps(result.audio_quality)

    cursor.execute(
        """
        UPDATE audits
        SET score = %s,
            max_score = %s,
            summary = %s,
            details_json = %s,
            transcription_json = %s,
            audio_quality = %s,
            ai_feedback = %s
        WHERE id = %s
        """,
        (
            result.score,
            result.maxPossibleScore,
            result.summary,
            details_json,
            transcription_json,
            audio_quality_json,
            ai_feedback or result.ai_feedback,
            audit_id,
        ),
    )


def update_audit_result(
    get_connection: ConnectionFactory,
    input_hash: str,
    result: AuditResult,
    ai_feedback: Optional[str] = None,
) -> Optional[int]:
    """Update an existing audit's evaluation results by input_hash."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM audits WHERE input_hash = %s ORDER BY id DESC LIMIT 1", (input_hash,))
        row = cursor.fetchone()
        if not row:
            return None

        audit_id = int(row["id"] if isinstance(row, dict) else row[0])
        _write_audit_result_fields(cursor, audit_id, result, ai_feedback)
        conn.commit()
        return audit_id
    finally:
        conn.close()


def update_audit_result_by_id(
    get_connection: ConnectionFactory,
    audit_id: int,
    result: AuditResult,
    ai_feedback: Optional[str] = None,
) -> Optional[int]:
    """Update an existing audit's evaluation results by id."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM audits WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return None

        target_id = int(row["id"] if isinstance(row, dict) else row[0])
        _write_audit_result_fields(cursor, target_id, result, ai_feedback)
        conn.commit()
        return target_id
    finally:
        conn.close()


def update_audit_by_id(
    get_connection: ConnectionFactory,
    audit_id: int,
    result: AuditResult,
    ai_feedback: Optional[str] = None,
) -> Optional[dict]:
    """Update a saved audit by id after manual auditor corrections.

    Returns:
      - None se a auditoria nao foi encontrada (chamador deve retornar 404).
      - dict com chaves {"updated": bool, "rag_payload": Optional[dict]}.
        rag_payload != None significa que o auditor mudou criterios e o caller
        deve disparar salvar_feedback_rag_sync em background (v1.3.90).

    v1.3.90: o feedback RAG NAO eh mais chamado dentro desta funcao. Ele tornava
    o PUT travado por 200ms-vários segundos esperando o embedding do Azure. O
    router agora agenda BackgroundTasks pra processar isso depois do response.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, details_json, transcription_json, sector_id FROM audits WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if not row:
            return None

        try:
            old_details = json_loads(row["details_json"], [])
        except Exception:
            old_details = []

        old_map = {}
        for d in old_details:
            if isinstance(d, dict) and d.get("criterionId"):
                old_map[d["criterionId"]] = d

        changed_criteria = []
        for new_d in result.details:
            cid = new_d.criterionId
            old_d = old_map.get(cid)
            if old_d and old_d.get("status") != new_d.status:
                changed_criteria.append(
                    f"Critério '{new_d.label}': a IA avaliou como '{old_d.get('status')}', mas o auditor corrigiu para '{new_d.status}'. "
                    f"Just. Final: {new_d.comment}"
                )

        rag_payload: Optional[dict] = None
        if changed_criteria:
            exemplo_text = ""
            try:
                t_json = json_loads(row["transcription_json"], [])
                exemplo_text = " ".join([seg.get("text", "") for seg in t_json if isinstance(seg, dict) and seg.get("text")])
                exemplo_text = exemplo_text[:2000]
            except Exception:
                pass

            rag_payload = {
                "tipo": "avaliacao",
                "situacao": "A IA errou a avaliação original na auditoria.",
                "correcao": " ".join(changed_criteria),
                "justificativa": "Correção manual do auditor de qualidade.",
                "criado_por": "auditor_qualidade",
                "setor": row["sector_id"] if "sector_id" in row.keys() else None,
                "exemplo_transcricao": exemplo_text or None,
            }

        details_json = json_dumps([d.model_dump() for d in result.details])
        transcription_json = json_dumps([s.model_dump() for s in result.transcription])
        audio_quality_json = json_dumps(result.audio_quality)

        cursor.execute(
            """
            UPDATE audits
            SET score = %s,
                max_score = %s,
                summary = %s,
                details_json = %s,
                transcription_json = %s,
                audio_quality = %s,
                ai_feedback = %s
            WHERE id = %s
            """,
            (
                result.score,
                result.maxPossibleScore,
                result.summary,
                details_json,
                transcription_json,
                audio_quality_json,
                ai_feedback or result.ai_feedback,
                audit_id,
            ),
        )
        conn.commit()
        return {"updated": cursor.rowcount > 0, "rag_payload": rag_payload}
    finally:
        conn.close()


def get_audit_by_hash(get_connection: ConnectionFactory, input_hash: str) -> Optional[AuditResult]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM audits
            WHERE input_hash = %s
              AND discarded_at IS NULL
              AND COALESCE(status, '') <> %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (input_hash, AUDIT_STATUS_DISCARDED),
        )
        row = cursor.fetchone()
        return row_to_audit_result(row)
    finally:
        conn.close()


def get_audit_media_record_by_hash(get_connection: ConnectionFactory, input_hash: str) -> Optional[dict]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, input_hash, audio_storage_path, audio_original_filename, audio_mime_type, audio_size_bytes
            FROM audits
            WHERE input_hash = %s
              AND discarded_at IS NULL
              AND COALESCE(status, '') <> %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (input_hash, AUDIT_STATUS_DISCARDED),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "input_hash": row["input_hash"] or "",
            "audio_storage_path": row["audio_storage_path"] if "audio_storage_path" in row.keys() else None,
            "audio_original_filename": row["audio_original_filename"] if "audio_original_filename" in row.keys() else None,
            "audio_mime_type": row["audio_mime_type"] if "audio_mime_type" in row.keys() else None,
            "audio_size_bytes": row["audio_size_bytes"] if "audio_size_bytes" in row.keys() else None,
        }
    finally:
        conn.close()


def get_audit_media_record_by_id(get_connection: ConnectionFactory, audit_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, input_hash, audio_storage_path, audio_original_filename, audio_mime_type, audio_size_bytes
            FROM audits
            WHERE id = %s
            LIMIT 1
            """,
            (audit_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        if not (row["audio_storage_path"] if "audio_storage_path" in row.keys() else None) and (row["input_hash"] or ""):
            cursor.execute(
                """
                SELECT id, input_hash, audio_storage_path, audio_original_filename, audio_mime_type, audio_size_bytes
                FROM audits
                WHERE input_hash = %s
                  AND id <> %s
                  AND COALESCE(audio_storage_path, '') <> ''
                ORDER BY id ASC
                LIMIT 1
                """,
                (row["input_hash"], audit_id),
            )
            source_row = cursor.fetchone()
            if source_row:
                cursor.execute(
                    """
                    UPDATE audits
                    SET audio_storage_path = %s,
                        audio_original_filename = %s,
                        audio_mime_type = %s,
                        audio_size_bytes = %s
                    WHERE id = %s
                    """,
                    (
                        source_row["audio_storage_path"] if "audio_storage_path" in source_row.keys() else None,
                        source_row["audio_original_filename"] if "audio_original_filename" in source_row.keys() else None,
                        source_row["audio_mime_type"] if "audio_mime_type" in source_row.keys() else None,
                        source_row["audio_size_bytes"] if "audio_size_bytes" in source_row.keys() else None,
                        audit_id,
                    ),
                )
                conn.commit()
                row = source_row
        return {
            "id": int(audit_id),
            "input_hash": row["input_hash"] or "",
            "audio_storage_path": row["audio_storage_path"] if "audio_storage_path" in row.keys() else None,
            "audio_original_filename": row["audio_original_filename"] if "audio_original_filename" in row.keys() else None,
            "audio_mime_type": row["audio_mime_type"] if "audio_mime_type" in row.keys() else None,
            "audio_size_bytes": row["audio_size_bytes"] if "audio_size_bytes" in row.keys() else None,
        }
    finally:
        conn.close()


def update_audit_audio_storage(
    get_connection: ConnectionFactory,
    audit_id: int,
    *,
    audio_storage_path: str,
    audio_original_filename: str,
    audio_mime_type: str,
    audio_size_bytes: int,
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE audits
            SET audio_storage_path = %s, audio_original_filename = %s, audio_mime_type = %s, audio_size_bytes = %s
            WHERE id = %s
            """,
            (
                audio_storage_path,
                audio_original_filename,
                audio_mime_type,
                audio_size_bytes,
                audit_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_audit_by_id(get_connection: ConnectionFactory, audit_id: int) -> Optional[dict]:
    conn = get_connection()
    try:
        
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT a.*, o.supervisor, o.escala
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
            WHERE a.id = %s
            LIMIT 1
            """,
            (audit_id,),
        )
        row = cursor.fetchone()

        if not row:
            return None

        has_audio_path = (
            "audio_storage_path" in row.keys()
            and bool(row["audio_storage_path"])
        )
        fallback_map = {} if has_audio_path else _resolve_audio_hash_fallback(cursor, [row])
        fallback = fallback_map.get(row["id"])
        audio_available = has_audio_path or fallback is not None

        if has_audio_path:
            mime_type = row["audio_mime_type"] if "audio_mime_type" in row.keys() else None
            size_bytes = row["audio_size_bytes"] if "audio_size_bytes" in row.keys() else None
            original_filename = row["audio_original_filename"] if "audio_original_filename" in row.keys() else None
        elif fallback:
            mime_type = fallback.get("audio_mime_type")
            size_bytes = fallback.get("audio_size_bytes")
            original_filename = None
        else:
            mime_type = None
            size_bytes = None
            original_filename = None

        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "audio_date": row["audit_date"] if "audit_date" in row.keys() else None,
            "operator_name": row["operator_name"] or "",
            "operator_id": row["operator_id"] or "",
            "score": row["score"],
            "max_score": row["max_score"],
            "summary": row["summary"] or "",
            "details": json_loads(row["details_json"], []),
            "transcription": json_loads(row["transcription_json"], []),
            "input_hash": row["input_hash"] or "",
            "alert_id": row["alert_id"] if "alert_id" in row.keys() else None,
            "alert_label": row["alert_label"] if "alert_label" in row.keys() else None,
            "sector_id": row["sector_id"] if "sector_id" in row.keys() else None,
            "supervisor": row["supervisor"] if "supervisor" in row.keys() else "",
            "escala": row["escala"] if "escala" in row.keys() else "",
            "source_type": normalize_source_type(row["source_type"], default=DEFAULT_SOURCE_TYPE),
            "audit_scope": get_audit_scope(row),
            "audio_quality": json_loads(row["audio_quality"], None),
            "audio_available": audio_available,
            "audio_url": f"/api/audit/{row['id']}/audio" if audio_available else None,
            "audio_mime_type": mime_type,
            "audio_original_filename": original_filename,
            "audio_size_bytes": size_bytes,
            "ai_feedback": row["ai_feedback"] if "ai_feedback" in row.keys() else None,
            "status": row["status"] if "status" in row.keys() else None,
            "contestation_reason": row["contestation_reason"] if "contestation_reason" in row.keys() else None,
            "contested_criteria": json_loads(row["contested_criteria"], None) if "contested_criteria" in row.keys() else None,
            "contestation_verdict": row["contestation_verdict"] if "contestation_verdict" in row.keys() else None,
            "review_defense": row["review_defense"] if "review_defense" in row.keys() else None,
            "reviewed_by": row["reviewed_by"] if "reviewed_by" in row.keys() else None,
            "reviewed_at": row["reviewed_at"] if "reviewed_at" in row.keys() else None,
        }
    finally:
        conn.close()


_ALLOWED_STATUS_TRANSITIONS = {
    AUDIT_STATUS_PENDING_APPROVAL: {
        AUDIT_STATUS_APPROVED,
        AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
    },
    AUDIT_STATUS_CONTESTATION_PENDING_REVIEW: {
        AUDIT_STATUS_CONTESTATION_ACCEPTED,
        AUDIT_STATUS_APPROVED,
    },
    AUDIT_STATUS_AWAITING_PAIR: {
        AUDIT_STATUS_PENDING_APPROVAL,
    },
    # Terminal states — no further transitions allowed via update_audit_status
    AUDIT_STATUS_APPROVED: set(),
    AUDIT_STATUS_CONTESTATION_ACCEPTED: set(),
}


def update_audit_status(
    get_connection: ConnectionFactory,
    audit_id: int,
    status: str,
    reason: Optional[str] = None,
    contested_criteria: Optional[str] = None,
):
    normalized_status = normalize_audit_status(status, default=None)
    if normalized_status is None:
        raise ValueError("Status de auditoria invalido.")
    normalized_reason = str(reason or "").strip() or None
    if normalized_status == AUDIT_STATUS_CONTESTED and normalized_reason is None:
        raise ValueError("Motivo da contestacao e obrigatorio.")
    if normalized_status in (AUDIT_STATUS_AWAITING_PAIR, AUDIT_STATUS_PENDING_APPROVAL) and normalized_reason is not None:
        raise ValueError("Motivo de contestacao nao e permitido para auditorias em fila aberta.")
    if normalized_status not in (AUDIT_STATUS_CONTESTED, AUDIT_STATUS_APPROVED, AUDIT_STATUS_CONTESTATION_ACCEPTED):
        normalized_reason = None

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Validate source status transition (C1 fix)
        cursor.execute("SELECT status FROM audits WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")
        current_status = row[0] or ""
        allowed_targets = _ALLOWED_STATUS_TRANSITIONS.get(current_status)
        if allowed_targets is not None and normalized_status not in allowed_targets:
            raise ValueError(
                f"Transicao de status invalida: {current_status} -> {normalized_status}"
            )
        # Preserve review fields for statuses that are part of the review flow
        _REVIEW_FLOW_STATUSES = {
            AUDIT_STATUS_APPROVED,
            AUDIT_STATUS_CONTESTATION_PENDING_REVIEW,
            AUDIT_STATUS_CONTESTATION_ACCEPTED,
        }
        preserve_review = normalized_status in _REVIEW_FLOW_STATUSES

        if preserve_review:
            cursor.execute(
                """
                UPDATE audits
                SET status = %s,
                    contestation_reason = %s,
                    contested_criteria = %s
                WHERE id = %s
                """,
                (normalized_status, normalized_reason, contested_criteria, audit_id),
            )
        else:
            cursor.execute(
                """
                UPDATE audits
                SET status = %s,
                    contestation_reason = %s,
                    contested_criteria = %s,
                    contestation_verdict = NULL,
                    review_defense = NULL,
                    reviewed_by = NULL,
                    reviewed_at = NULL
                WHERE id = %s
                """,
                (normalized_status, normalized_reason, contested_criteria, audit_id),
            )
        conn.commit()
    finally:
        conn.close()


def discard_audit(
    get_connection: ConnectionFactory,
    audit_id: int,
    *,
    discarded_by: str,
    reason: Optional[str] = None,
) -> dict:
    """Marca uma auditoria como descartada (soft-delete).

    Descartadas saem da cota mensal, do dashboard e do painel do supervisor,
    mas permanecem para rastreabilidade (trilha de auditoria/LGPD).
    """
    normalized_reason = str(reason or "").strip() or None
    normalized_reviewer = str(discarded_by or "").strip() or "Auditoria"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, status FROM audits WHERE id = %s", (audit_id,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")
        current_status = row["status"] if isinstance(row, dict) else row[1]
        if current_status == AUDIT_STATUS_DISCARDED:
            return {"id": audit_id, "status": AUDIT_STATUS_DISCARDED, "already_discarded": True}

        cursor.execute(
            """
            UPDATE audits
            SET status = %s,
                discarded_at = %s,
                discarded_by = %s,
                discard_reason = %s,
                pre_discard_status = %s
            WHERE id = %s
            """,
            (
                AUDIT_STATUS_DISCARDED,
                datetime.now().isoformat(),
                normalized_reviewer,
                normalized_reason,
                current_status,
                audit_id,
            ),
        )
        conn.commit()

        # Do not delete the associated arquivo_salvo.
        # This preserves user feedback stored in the file when an audit is soft-deleted.
    finally:
        conn.close()

    return {
        "id": audit_id,
        "status": AUDIT_STATUS_DISCARDED,
        "previous_status": current_status,
        "discarded_by": normalized_reviewer,
        "reason": normalized_reason,
    }


def restore_audit(
    get_connection: ConnectionFactory,
    audit_id: int,
    *,
    restored_by: str,
) -> dict:
    """Reverte o soft-delete de uma auditoria descartada.

    Usa `pre_discard_status` para restaurar o status anterior. Se a coluna
    estiver vazia (auditoria descartada antes do fix de 2026-04-14), cai
    para `AUDIT_STATUS_PENDING_APPROVAL` como default seguro.
    """
    normalized_reviewer = str(restored_by or "").strip() or "Auditoria"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, status, pre_discard_status FROM audits WHERE id = %s",
            (audit_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Auditoria {audit_id} nao encontrada.")

        if isinstance(row, dict):
            current_status = row.get("status")
            pre_discard_status = row.get("pre_discard_status")
        else:
            current_status = row[1]
            pre_discard_status = row[2]

        if current_status != AUDIT_STATUS_DISCARDED:
            return {
                "id": audit_id,
                "status": current_status,
                "already_restored": True,
            }

        target_status = pre_discard_status or AUDIT_STATUS_PENDING_APPROVAL

        cursor.execute(
            """
            UPDATE audits
            SET status = %s,
                discarded_at = NULL,
                discarded_by = NULL,
                discard_reason = NULL,
                pre_discard_status = NULL
            WHERE id = %s
            """,
            (target_status, audit_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": audit_id,
        "status": target_status,
        "previous_status": AUDIT_STATUS_DISCARDED,
        "restored_by": normalized_reviewer,
    }


def finalize_contestation_review(
    get_connection: ConnectionFactory,
    audit_id: int,
    *,
    verdict: str,
    defense: str,
    reviewed_by: str,
    updated_details: Optional[list] = None,
) -> dict:
    normalized_verdict = str(verdict or "").strip().lower()
    if normalized_verdict not in (
        AUDIT_CONTESTATION_VERDICT_ACCEPTED,
        AUDIT_CONTESTATION_VERDICT_REJECTED,
    ):
        raise ValueError("Veredito de contestacao invalido.")

    normalized_defense = str(defense or "").strip()
    if not normalized_defense:
        raise ValueError("Defesa tecnica e obrigatoria.")

    normalized_reviewer = str(reviewed_by or "").strip() or "Auditoria"
    current_audit = get_audit_by_id(get_connection, audit_id)
    if current_audit is None:
        raise ValueError("Auditoria nao encontrada.")
    if current_audit.get("status") != AUDIT_STATUS_CONTESTATION_PENDING_REVIEW:
        raise ValueError("A auditoria nao esta em revisao tecnica.")

    # Both accepted and rejected contestations go to the dashboard (approved).
    # When accepted, the updated_details are applied to the audit.
    # The contestation_verdict field records the original decision for audit trail.
    target_status = AUDIT_STATUS_APPROVED

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Only accepted contestations may rewrite criteria and score. Rejected
        # contestations preserve the original audit and store the technical defense.
        extra_updates = ""
        params = [
            target_status,
            normalized_verdict,
            normalized_defense,
            normalized_reviewer,
        ]
        if (
            normalized_verdict == AUDIT_CONTESTATION_VERDICT_ACCEPTED
            and updated_details is not None
        ):
            if not isinstance(updated_details, list):
                raise ValueError("Detalhes atualizados da contestacao devem ser uma lista.")
            # Detect if a fatal flag originally zeroed the audit despite criteria successes
            was_fatal_zeroed = False
            if current_audit.get("score") == 0.0:
                original_sum = sum(float(d.get("obtainedScore", 0)) for d in (current_audit.get("details") or []))
                if original_sum > 0.0:
                    was_fatal_zeroed = True

            new_score = 0.0
            new_max = 0.0
            normalized_details = []
            for d in updated_details:
                if not isinstance(d, dict):
                    raise ValueError("Detalhe de criterio invalido.")
                item = dict(d or {})
                status = _normalize_binary_detail_status(item.get("status", "pass"))
                item["status"] = status
                try:
                    weight = float(item.get("weight", 1) or 0)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Peso de criterio invalido.") from exc
                if weight < 0:
                    raise ValueError("Peso de criterio invalido.")
                obtained = 0.0
                if status == "pass":
                    obtained = weight
                    new_max += weight
                    new_score += obtained
                    item["obtainedScore"] = obtained
                else:
                    new_max += weight
                    item["obtainedScore"] = 0.0
                normalized_details.append(item)
            
            if was_fatal_zeroed:
                new_score = 0.0
                
            extra_updates = ",\n                details_json = %s,\n                score = %s,\n                max_score = %s"
            params.extend([json_dumps(normalized_details), new_score, new_max])

        params.append(audit_id)
        cursor.execute(
            f"""
            UPDATE audits
            SET status = %s,
                contestation_verdict = %s,
                review_defense = %s,
                reviewed_by = %s,
                reviewed_at = CURRENT_TIMESTAMP{extra_updates}
            WHERE id = %s
            """,
            tuple(params),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "audit_id": audit_id,
        "status": target_status,
        "contestation_verdict": normalized_verdict,
        "review_defense": normalized_defense,
        "reviewed_by": normalized_reviewer,
    }


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
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "operator_name": row["operator_name"],
                    "operator_id": row["operator_id"] or "",
                    "score": row["score"],
                    "max_score": row["max_score"],
                    "summary": row["summary"],
                    "details": row["details_json"],
                    "transcription": json_loads(row["transcription_json"], []) if "transcription_json" in row.keys() else [],
                    "alert_id": row["alert_id"] if "alert_id" in row.keys() else None,
                    "alert_label": row["alert_label"] if "alert_label" in row.keys() else None,
                    "sector_id": row["sector_id"] if "sector_id" in row.keys() else None,
                    "status": row["status"] if "status" in row.keys() else None,
                    "contestation_reason": row["contestation_reason"] if "contestation_reason" in row.keys() else None,
                    "contested_criteria": json_loads(row["contested_criteria"], None) if "contested_criteria" in row.keys() else None,
                    "contestation_verdict": row["contestation_verdict"] if "contestation_verdict" in row.keys() else None,
                    "review_defense": row["review_defense"] if "review_defense" in row.keys() else None,
                    "reviewed_by": row["reviewed_by"] if "reviewed_by" in row.keys() else None,
                    "reviewed_at": row["reviewed_at"] if "reviewed_at" in row.keys() else None,
                    "supervisor": row["supervisor"] or "",
                    "escala": row["escala"] or "",
                    "audio_available": audio_available,
                    "audio_url": f"/api/audit/{row['id']}/audio" if audio_available else None,
                    "audio_mime_type": mime_type,
                    "audio_size_bytes": size_bytes,
                    "feedback": feedback,
                }
            )

        return results
    finally:
        conn.close()

def list_pending_dispatch_audits(get_connection, older_than_hours: Optional[int] = None) -> list[dict]:
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

def upsert_audit_draft(get_connection, input_hash: str, user_id: str, details_json: str, transcription_json: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_drafts (input_hash, user_id, details_json, transcription_json, updated_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (input_hash, user_id) 
            DO UPDATE SET 
                details_json = EXCLUDED.details_json,
                transcription_json = EXCLUDED.transcription_json,
                updated_at = EXCLUDED.updated_at
            """,
            (input_hash, user_id, details_json, transcription_json)
        )
        conn.commit()
    finally:
        conn.close()

def get_audit_draft(get_connection, input_hash: str, user_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM audit_drafts WHERE input_hash = %s AND user_id = %s",
            (input_hash, user_id)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
