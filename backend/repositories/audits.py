"""Repository de auditorias: acesso à tabela `audits` no Postgres (Neon).

Papel no fluxo: a avaliação (manual via routers ou automática via
`core/automation.py`) persiste o resultado aqui com status `awaiting_pair`
("Arquivos Salvos") → o auditor promove manualmente para `pending_approval`
(painel do supervisor) → supervisor aprova/contesta → `approved` entra no
fechamento mensal, que lê deste módulo via `get_audits_for_export`.

Responsabilidades:
- CRUD de auditorias (save/get/update) + vínculo de áudio persistido;
- contagem de cota mensal por operador (alimenta o gate de 2/operador/mês —
  o limite em si é aplicado no router, ver `promote_audit_to_pending_approval`);
- máquina de estados de status (`_ALLOWED_STATUS_TRANSITIONS`);
- soft-delete (descarte/restauração) com trilha de auditoria;
- fluxo de contestação do supervisor (defesa técnica + veredito);
- export para o fechamento/BI (`get_audits_for_export`) — o formato dos campos
  retornados é CONTRATO consumido pelo BI; não alterar chaves/semântica;
- rascunhos de auditoria (`audit_drafts`): reexportados de `repositories.audit_drafts`.

CUSTO DE API: nenhum — este módulo só conversa com o PostgreSQL. Atenção ao
`update_audit_by_id`: ele apenas MONTA o `rag_payload` quando o auditor corrige
critérios; a chamada paga de embedding (Azure) é disparada pelo router em
background (v1.3.90), nunca daqui.

Convenções:
- Toda função pública recebe `get_connection` (ConnectionFactory) por injeção
  de dependência — facilita testes — e abre/fecha a própria conexão.
- Identidade de operador: `operator_id` tem prioridade; fallback para
  `operator_name` case-insensitive quando o id está vazio.
"""
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

# Helpers de normalização extraidos (v1.3.145); usados pelas funcoes que ficaram
# (save_audit, get_audits_for_export, finalize_*, _resolve_open_review_queue) e
# reexportados para compat (testes chamam os privados via repositories.audits).
from repositories.audits_helpers import (  # noqa: E402,F401
    _normalize_binary_detail_status,
    _normalize_sector_id,
    _normalize_operator_name,
    _normalize_operator_id,
)

# Cota mensal por operador extraida para modulo proprio (v1.3.145); reexportada
# para manter `repositories.audits.<nome>` patchavel e a fachada db.database valida.
from repositories.audits_quota import (  # noqa: E402,F401
    get_operator_audit_counts_for_month_bulk,
    get_operator_audit_count_for_month,
    get_supervisor_audit_count_for_month,
)

_REVIEW_DETAIL_STATUSES = {"pass", "fail"}


# ── Fila de revisão do supervisor (awaiting_pair → pending_approval) ─────────

def _resolve_open_review_queue(
    cursor: Any,
    *,
    operator_name: Optional[str],
    operator_id: Optional[str],
) -> list[dict]:
    """Lista as auditorias ABERTAS (awaiting_pair ou pending_approval) do operador.

    Matching de identidade: id quando disponível; auditorias antigas sem
    operator_id casam pelo nome (case-insensitive). Retorna [{"id", "status"}]
    em ordem crescente de id (FIFO). Sem identidade nenhuma, retorna [].
    """
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
    """Retorna um snapshot SOMENTE-LEITURA da fila de revisão aberta do operador.

    Historicamente esta função promovia automaticamente itens ``awaiting_pair``
    para ``pending_approval`` para manter a fila do supervisor em dois itens
    por operador. Esse comportamento foi removido: a promoção agora é ação
    manual do auditor pelo endpoint dedicado
    ``POST /api/audit/{audit_id}/promote-to-pending-approval``.

    A função foi mantida (e ainda é chamada pelos call sites existentes)
    porque os chamadores dependem do snapshot de ``pending_ids`` /
    ``awaiting_ids``. Ela NÃO altera mais status de auditoria — apesar do nome
    "rebalance", hoje é apenas consulta.
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
    """Promove UMA auditoria de ``awaiting_pair`` para ``pending_approval``.

    Substituto manual da lógica de auto-promoção que antes vivia em
    :func:`rebalance_operator_review_queue`. Retorna {"audit_id", "status"}
    da auditoria atualizada, ou levanta ``ValueError`` se ela não existe ou
    não está em ``awaiting_pair``.

    IMPORTANTE — gate de cota: o limite de 2 auditorias/operador/mês no painel
    do supervisor (commit 77299af5) NÃO é validado aqui; ele é aplicado pelo
    endpoint chamador (`routers/audit.py::promote_audit_endpoint`) usando
    `get_supervisor_audit_count_for_month` antes de invocar esta função.
    Chamadas diretas a este repository pulam a cota.

    O UPDATE repete `status = awaiting_pair` no WHERE como proteção contra
    corrida (promoção dupla concorrente vira no-op).
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
    """Salva a auditoria já com status ``awaiting_pair`` (entrada da fila de revisão).

    Porta de entrada usada pelos fluxos manual e automático: persiste via
    `save_audit` e, se houver `input_hash`, tenta reaproveitar o áudio já
    persistido por outra auditoria do mesmo hash (vínculo best-effort: falha
    só gera warning, nunca derruba o salvamento).

    Parâmetros relevantes:
        rebalance: quando True, consulta o snapshot da fila para informar o
            status efetivo no retorno (mantido por compatibilidade — a fila
            não é mais rebalanceada automaticamente; ver
            `rebalance_operator_review_queue`).

    Retorno: {"audit_id", "status", "pending_count", "open_count"}.
    Efeitos colaterais: INSERT em `audits` (+ UPDATE de áudio quando aplicável).
    """
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


# ── Persistência (INSERT / UPDATE de resultados) ─────────────────────────────

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
    """Insere uma auditoria nova em `audits` e retorna o id gerado.

    Serializa details/transcription/audio_quality como JSON e normaliza
    source_type, status e sector_id antes de gravar. O `audit_scope` é
    DERIVADO de source_type + audio_quality (ex.: documento vs ligação) —
    é ele que decide se a auditoria conta na cota e aparece no export.

    Parâmetros relevantes:
        input_hash: hash do insumo (áudio/documento) — chave de deduplicação
            e de reaproveitamento de áudio entre auditorias.
        status: default `DEFAULT_AUDIT_STATUS`; fluxo de revisão usa
            `awaiting_pair` via `enqueue_audit_for_supervisor_review`.
        colaborador_id: FK para `colaboradores` quando resolvida pelo chamador.

    Efeito colateral: INSERT + commit. Não dispara chamadas de API.
    """
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
    """Retorna o id da auditoria MAIS RECENTE com este input_hash (inclui descartadas)."""
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
    """UPDATE dos campos de resultado (score/summary/JSONs) — commit fica a cargo do chamador."""
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
    """Atualiza os resultados de avaliação da auditoria mais recente com este input_hash.

    Usado em re-avaliações do mesmo insumo (não cria linha nova). Retorna o id
    atualizado ou None se nenhuma auditoria tem esse hash.
    """
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
    """Atualiza os resultados de avaliação de uma auditoria existente pelo id.

    Variante de `update_audit_result` para quando o chamador já conhece o id.
    Retorna o id atualizado ou None se a auditoria não existe.
    """
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
    """Atualiza uma auditoria salva pelo id após correções manuais do auditor.

    Antes de gravar, compara o status de cada critério com o que estava salvo:
    diferenças viram texto de correção e alimentam o `rag_payload` (feedback
    para o RAG aprender com o auditor), incluindo um trecho da transcrição
    (até 2000 chars) como exemplo.

    Retorna:
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


# ── Consulta por hash/id e metadados de áudio ────────────────────────────────

def get_audit_by_hash(get_connection: ConnectionFactory, input_hash: str) -> Optional[AuditResult]:
    """Retorna a auditoria mais recente (não descartada) deste input_hash como AuditResult.

    É o lookup do cache de deduplicação: mesmo insumo já auditado → reaproveita
    o resultado em vez de pagar nova transcrição/avaliação.
    """
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
    """Metadados de áudio (storage path, filename, mime, tamanho) da auditoria mais recente do hash.

    Somente leitura; ignora descartadas. Usado para reaproveitar o áudio já
    persistido ao enfileirar nova auditoria do mesmo insumo.
    """
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
    """Metadados de áudio de uma auditoria pelo id, com backfill via input_hash.

    NÃO é somente leitura: se a auditoria não tem `audio_storage_path` mas
    outra auditoria com o mesmo `input_hash` tem, copia os campos de áudio
    para esta linha (UPDATE + commit) antes de retornar — é aqui que o
    fallback detectado em `_resolve_audio_hash_fallback` vira persistência,
    no momento em que o áudio é efetivamente servido.
    """
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
    """Grava os metadados de áudio persistido na auditoria; True se alguma linha mudou."""
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
    """Carrega uma auditoria completa pelo id, enriquecida para exibição.

    Faz LEFT JOIN com `colaboradores` (por operator_id, fallback nome) para
    trazer supervisor/escala, resolve disponibilidade de áudio (caminho próprio
    ou fallback por input_hash, sem persistir) e desserializa os campos JSON.
    Inclui descartadas — o filtro de status é responsabilidade do chamador.
    Retorna dict no formato consumido pelos routers, ou None se não existe.
    """
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
            # --- Identificação / data ---
            "id": row["id"],                                  # PK da auditoria (tabela audits)
            "timestamp": row["timestamp"],                    # quando a auditoria foi criada
            "audio_date": row["audit_date"] if "audit_date" in row.keys() else None,  # data real da ligação (audit_date), não a da auditoria
            # --- Operador auditado ---
            "operator_name": row["operator_name"] or "",      # nome do operador
            "operator_id": row["operator_id"] or "",          # id de telefonia do operador (prioritário p/ matching)
            # --- Resultado da avaliação ---
            "score": row["score"],                            # nota obtida
            "max_score": row["max_score"],                    # nota máxima possível
            "summary": row["summary"] or "",                  # resumo textual da avaliação
            "details": json_loads(row["details_json"], []),   # lista de critérios avaliados (status/peso/comentário)
            "transcription": json_loads(row["transcription_json"], []),  # transcrição diarizada (segmentos)
            "input_hash": row["input_hash"] or "",            # hash do conteúdo do arquivo (dedupe da gravação)
            # --- Classificação (setor/alerta) ---
            "alert_id": row["alert_id"] if "alert_id" in row.keys() else None,        # id do alerta auditado
            "alert_label": row["alert_label"] if "alert_label" in row.keys() else None,  # rótulo legível do alerta
            "sector_id": row["sector_id"] if "sector_id" in row.keys() else None,     # setor da auditoria
            # --- Vínculo de RH (via JOIN colaboradores) ---
            "supervisor": row["supervisor"] if "supervisor" in row.keys() else "",    # supervisor do operador (cadastro)
            "escala": row["escala"] if "escala" in row.keys() else "",                # escala/turno do operador (cadastro)
            # --- Tipo/escopo ---
            "source_type": normalize_source_type(row["source_type"], default=DEFAULT_SOURCE_TYPE),  # audio | pdf
            "audit_scope": get_audit_scope(row),              # escopo da auditoria (call_quality)
            # --- Áudio (disponibilidade + metadados) ---
            "audio_quality": json_loads(row["audio_quality"], None),  # score/diagnóstico de qualidade do áudio
            "audio_available": audio_available,               # há áudio servível (caminho próprio ou fallback por hash)
            "audio_url": f"/api/audit/{row['id']}/audio" if audio_available else None,  # endpoint de streaming (None se sem áudio)
            "audio_mime_type": mime_type,                     # mime do áudio (ex.: audio/wav)
            "audio_original_filename": original_filename,      # nome original do arquivo
            "audio_size_bytes": size_bytes,                   # tamanho do áudio em bytes
            "ai_feedback": row["ai_feedback"] if "ai_feedback" in row.keys() else None,  # feedback técnico da IA p/ o operador
            # --- Estado / fluxo de contestação ---
            "status": row["status"] if "status" in row.keys() else None,  # awaiting_pair|pending_approval|approved|contestation_*|discarded
            "contestation_reason": row["contestation_reason"] if "contestation_reason" in row.keys() else None,  # motivo da contestação (supervisor)
            "contested_criteria": json_loads(row["contested_criteria"], None) if "contested_criteria" in row.keys() else None,  # critérios contestados
            "contestation_verdict": row["contestation_verdict"] if "contestation_verdict" in row.keys() else None,  # veredito (accepted|rejected)
            "review_defense": row["review_defense"] if "review_defense" in row.keys() else None,  # defesa técnica do auditor
            "reviewed_by": row["reviewed_by"] if "reviewed_by" in row.keys() else None,  # quem finalizou a revisão
            "reviewed_at": row["reviewed_at"] if "reviewed_at" in row.keys() else None,  # quando a revisão foi finalizada
        }
    finally:
        conn.close()


# ── Máquina de estados de status ─────────────────────────────────────────────
# Transições permitidas em update_audit_status: {status_atual: {alvos válidos}}.
# Status AUSENTE do mapa (ex.: contested, discarded, legados) não é restringido
# (get retorna None → transição liberada); status presente com set vazio é
# terminal. Descarte/restauração não passam por aqui (têm funções próprias).
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
    # Estados terminais — nenhuma transição adicional via update_audit_status
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
    """Muda o status de uma auditoria validando a transição na máquina de estados.

    Regras de validação (todas levantam ValueError):
    - status desconhecido após normalização;
    - contestação (`contested`) exige `reason`; filas abertas (awaiting_pair/
      pending_approval) NÃO aceitam reason; demais status descartam o reason;
    - transição precisa estar em `_ALLOWED_STATUS_TRANSITIONS`.

    Efeito colateral: UPDATE + commit. Para status FORA do fluxo de revisão,
    os campos de revisão (verdict/defense/reviewed_by/reviewed_at) são zerados
    junto; dentro do fluxo, são preservados (o veredito é trilha de auditoria).
    """
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

        # Valida a transição a partir do status de origem (fix C1)
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
        # Preserva os campos de revisão para status que fazem parte do fluxo de revisão
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


# ── Descarte e restauração (soft-delete) ─────────────────────────────────────

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

    Guarda o status anterior em `pre_discard_status` para o `restore_audit`
    devolver a auditoria ao ponto em que estava. Idempotente: descartar de
    novo retorna {"already_discarded": True} sem alterar nada.
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

        # Não deletar o arquivo_salvo associado.
        # Isso preserva o feedback do usuário guardado no arquivo quando a
        # auditoria sofre soft-delete.
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


# ── Contestação (revisão técnica do supervisor) ──────────────────────────────

def finalize_contestation_review(
    get_connection: ConnectionFactory,
    audit_id: int,
    *,
    verdict: str,
    defense: str,
    reviewed_by: str,
    updated_details: Optional[list] = None,
) -> dict:
    """Encerra a revisão técnica de uma contestação (aceita ou rejeitada).

    Pré-condições (ValueError se violadas): veredito ∈ {accepted, rejected},
    defesa técnica não vazia e auditoria em `contestation_pending_review`.

    Parâmetros relevantes:
        updated_details: lista de critérios corrigidos — só é aplicada quando
            o veredito é ACEITO; rejeição preserva a avaliação original.
        defense: justificativa técnica obrigatória do revisor (vai para
            `review_defense`).

    Recalcula score/max_score a partir dos pesos dos critérios (modelo binário
    pass/fail) quando aceita. Caso a auditoria original tenha sido zerada por
    fatal flag (score 0 com soma de critérios > 0), o zero é MANTIDO mesmo com
    critérios aprovados — a contestação corrige critérios, não anula a falha
    fatal.

    Efeito colateral: UPDATE + commit (status final sempre `approved`; o campo
    `contestation_verdict` registra a decisão para a trilha de auditoria).
    """
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

    # Contestações aceitas E rejeitadas vão para o dashboard (approved).
    # Quando aceita, os updated_details são aplicados à auditoria.
    # O campo contestation_verdict registra a decisão original para a trilha de auditoria.
    target_status = AUDIT_STATUS_APPROVED

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Só contestações ACEITAS podem reescrever critérios e score. Rejeitadas
        # preservam a auditoria original e armazenam apenas a defesa técnica.
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
            # Detecta se uma fatal flag zerou a auditoria original apesar de critérios aprovados
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



# Rascunhos de auditoria (tabela `audit_drafts`): implementacao extraida para
# repositories.audit_drafts; reexportada aqui p/ compat (callers e o patch
# `repositories.audits.{upsert,get}_audit_draft` em test_audit_edit_persistence).
from repositories.audit_drafts import upsert_audit_draft, get_audit_draft  # noqa: E402,F401

# Export para fechamento/BI e listagens (read-only): extraído para
# repositories.audits_export (v1.3.167); reexportado p/ compat (get_audit_by_id
# usa _resolve_audio_hash_fallback; routers/review e a fachada db.database usam
# get_audits_for_export / list_pending_dispatch_audits como atributo de módulo).
from repositories.audits_export import (  # noqa: E402,F401
    _resolve_audio_hash_fallback,
    get_audits_for_export,
    list_pending_dispatch_audits,
)
