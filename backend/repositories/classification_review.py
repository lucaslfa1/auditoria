import contextlib
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Any

from db.domain_constants import (
    REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES,
    REVIEW_QUEUE_READY_STATUSES,
    REVIEW_QUEUE_STATUS_ALL,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    REVIEW_QUEUE_STATUS_REVIEWED,
    REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
)
from repositories.common import (
    extract_returning_id,
    json_loads,
    normalize_quality_reference,
    normalize_review_priority,
    normalize_review_status,
)


ConnectionFactory = Callable[[], Any]
PROTECTED_SYNC_STATUSES = (
    REVIEW_QUEUE_STATUS_REVIEWED,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
)

AUDIT_TASK_BLOCKED_STATUSES = {
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
}


def _normalize_sector_id(value: Optional[str]) -> Optional[str]:
    normalized = str(value or "").strip().lower()
    return normalized or None


def _normalize_metadata_value(value: Optional[object]) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json_loads(value, {})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_metadata_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def upsert_ligacao_auditada(
    get_connection: ConnectionFactory,
    nome_arquivo: str,
    caminho_relativo: str,
    hash_arquivo: str,
    grupo: Optional[str] = None,
    subgrupo: Optional[str] = None,
    setor_referencia: Optional[str] = None,
    alerta_referencia: Optional[str] = None,
    qualidade_referencia: Optional[str] = None,
    observacao: Optional[str] = None,
) -> int:
    if not nome_arquivo or not caminho_relativo or not hash_arquivo:
        raise ValueError("nome_arquivo, caminho_relativo e hash_arquivo são obrigatórios")

    now = datetime.now().isoformat()
    qualidade_normalizada = normalize_quality_reference(qualidade_referencia)
    setor_normalizado = _normalize_sector_id(setor_referencia)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ligacoes_auditadas (
                nome_arquivo, caminho_relativo, hash_arquivo,
                grupo, subgrupo, setor_referencia, alerta_referencia,
                qualidade_referencia, observacao, criado_em, atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(hash_arquivo) DO UPDATE SET
                nome_arquivo = excluded.nome_arquivo,
                caminho_relativo = excluded.caminho_relativo,
                grupo = excluded.grupo,
                subgrupo = excluded.subgrupo,
                setor_referencia = excluded.setor_referencia,
                alerta_referencia = excluded.alerta_referencia,
                qualidade_referencia = excluded.qualidade_referencia,
                observacao = excluded.observacao,
                atualizado_em = excluded.atualizado_em
            """,
            (
                nome_arquivo,
                caminho_relativo,
                hash_arquivo,
                grupo,
                subgrupo,
                setor_normalizado,
                alerta_referencia,
                qualidade_normalizada,
                observacao or "",
                now,
                now,
            ),
        )
        cursor.execute("SELECT id FROM ligacoes_auditadas WHERE hash_arquivo = %s", (hash_arquivo,))
        ligacao_id = cursor.fetchone()[0]
        conn.commit()
        return int(ligacao_id)
    finally:
        conn.close()


def get_ligacao_auditada_por_hash(get_connection: ConnectionFactory, hash_arquivo: str) -> Optional[dict]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ligacoes_auditadas WHERE hash_arquivo = %s", (hash_arquivo,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "nome_arquivo": row["nome_arquivo"],
            "caminho_relativo": row["caminho_relativo"],
            "hash_arquivo": row["hash_arquivo"],
            "grupo": row["grupo"],
            "subgrupo": row["subgrupo"],
            "setor_referencia": row["setor_referencia"],
            "alerta_referencia": row["alerta_referencia"],
            "qualidade_referencia": row["qualidade_referencia"],
            "observacao": row["observacao"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }
    finally:
        conn.close()


def registrar_resultado_classificacao(
    get_connection: ConnectionFactory,
    ligacao_id: int,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    modelo: Optional[str] = None,
    versao_prompt: Optional[str] = None,
    acertou_setor: Optional[bool] = None,
    acertou_alerta: Optional[bool] = None,
    erro: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> int:
    now = datetime.now().isoformat()
    setor_previsto_normalizado = _normalize_sector_id(setor_previsto)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resultados_classificacao (
                ligacao_id, setor_previsto, alerta_previsto, confianca,
                operador_previsto, modelo, versao_prompt,
                acertou_setor, acertou_alerta, erro, metadata_json, executado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                ligacao_id,
                setor_previsto_normalizado,
                alerta_previsto,
                confianca,
                operador_previsto,
                modelo,
                versao_prompt,
                None if acertou_setor is None else int(acertou_setor),
                None if acertou_alerta is None else int(acertou_alerta),
                erro,
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
            ),
        )
        resultado_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return int(resultado_id)
    finally:
        conn.close()


def _unlink_item_media(input_hash: str, media_path: Optional[str], *, logger=None) -> None:
    import logging
    from storage.audit_storage import resolve_stored_audit_audio_path

    if logger is None:
        logger = logging.getLogger(__name__)
    if not media_path:
        return

    try:
        file_obj = resolve_stored_audit_audio_path(media_path)
        if file_obj:
            file_obj.unlink(missing_ok=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("Erro ao apagar arquivo fisico para hash %s: %s", input_hash, e)


def _purgar_item_fila(
    cursor,
    input_hash: str,
    metadata: dict,
    *,
    sync_log_action: str = "delete",
    tombstone_motivo: Optional[str] = None,
    loop_limit: int = 3,
    logger=None,
) -> tuple[Optional[str], Optional[tuple[int, str]]]:
    """Remove o item da fila (libera o UNIQUE input_hash) e trata o huawei_sync_logs
    conforme `sync_log_action`:
      - "delete": apaga a linha (limpeza por idade) -> permite re-entrada via novo download.
      - "tombstone_recoverable": marca 'discarded_recoverable' (rebaixa ate o limite anti-loop).
      - "tombstone_permanent": marca 'discarded_permanent' (tombstone; nunca rebaixa).

    Retorna (media_path, tombstone_result) onde tombstone_result=(attempts, status) ou None.
    """
    if not isinstance(metadata, dict):
        metadata = {}

    huawei_call_id = metadata.get("huawei_call_id")
    media_path = metadata.get("classified_audio_path") or metadata.get("classified_file_path")

    cursor.execute(
        "DELETE FROM fila_revisao_classificacao WHERE input_hash = %s",
        (input_hash,),
    )
    tombstone_result: Optional[tuple[int, str]] = None
    if huawei_call_id:
        if sync_log_action == "delete":
            cursor.execute(
                "DELETE FROM huawei_sync_logs WHERE call_id = %s",
                (str(huawei_call_id),),
            )
        else:
            from db.database import huawei_sync_log_tombstone
            tombstone_result = huawei_sync_log_tombstone(
                cursor,
                str(huawei_call_id),
                permanent=(sync_log_action == "tombstone_permanent"),
                motivo=tombstone_motivo,
                loop_limit=loop_limit,
            )
    return media_path, tombstone_result


def limpar_fila_revisao_classificacao_antiga(get_connection: ConnectionFactory, hours_old: int = 24) -> dict:
    """
    Remove somente itens explicitamente arquivados/descartaveis ha mais de X horas.

    A fila de revisao guarda trabalho operacional dos auditores; por isso a
    limpeza automatica nao remove estados pendentes, bloqueados ou em triagem
    manual apenas por idade.
    """
    from datetime import datetime, timedelta, timezone
    import logging

    logger = logging.getLogger(__name__)
    cutoff_date = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT input_hash, metadata_json
            FROM fila_revisao_classificacao
            WHERE atualizado_em < %s
              AND (
                    COALESCE(metadata_json::jsonb ->> 'archived', 'false') = 'true'
                 OR COALESCE(metadata_json::jsonb ->> 'cleanup_discardable', 'false') = 'true'
              )
            """,
            (cutoff_date,)
        )
        rows = cursor.fetchall()

        deleted_count = 0
        media_to_unlink: list[tuple[str, str]] = []
        for row in rows:
            input_hash = row["input_hash"]
            raw_meta = row["metadata_json"]

            metadata = json_loads(raw_meta, {})
            if not isinstance(metadata, dict):
                metadata = {}

            media_path, _ = _purgar_item_fila(cursor, input_hash, metadata, logger=logger)
            if media_path:
                media_to_unlink.append((input_hash, media_path))
            deleted_count += 1
            
        conn.commit()
        for input_hash, media_path in media_to_unlink:
            _unlink_item_media(input_hash, media_path, logger=logger)
        return {"deleted": deleted_count}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def descartar_item_automacao(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    motivo: str,
    tombstone: bool = False,
    tombstone_motivo: Optional[str] = None,
    loop_limit: int = 3,
    log_fields: Optional[dict] = None,
) -> dict:
    """Descarta um item da fila no modo automacao: remove a linha da fila em transacao,
    marca o huawei_sync_logs como descartado (tombstone) e apaga a midia apos commit.
    No-op idempotente se o item ja nao existir.

    tombstone=True  -> 'discarded_permanent' (impossivel de auditar; nunca rebaixa).
    tombstone=False -> 'discarded_recoverable' (pode voltar num proximo sync ate o limite
                       anti-loop `loop_limit`, quando vira permanent). Substitui o antigo
                       DELETE do sync_log: a linha agora persiste para contar tentativas.
    """
    import logging

    logger = logging.getLogger(__name__)
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")
    log_fields = log_fields or {}
    sync_log_action = "tombstone_permanent" if tombstone else "tombstone_recoverable"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT input_hash, metadata_json FROM fila_revisao_classificacao WHERE input_hash = %s",
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            logger.warning("descartar_item_automacao: item %s ja removido; no-op.", input_hash)
            conn.rollback()
            return {"discarded": False, "reason": "not_found"}

        metadata = json_loads(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}

        media_path, tombstone_result = _purgar_item_fila(
            cursor,
            input_hash,
            metadata,
            sync_log_action=sync_log_action,
            tombstone_motivo=tombstone_motivo or motivo,
            loop_limit=loop_limit,
            logger=logger,
        )
        conn.commit()
        attempts = tombstone_result[0] if tombstone_result else None
        final_status = tombstone_result[1] if tombstone_result else None
        logger.info(
            "descartar_item_automacao: descartado input_hash=%s arquivo=%s setor=%s operador=%s "
            "motivo=%s call_id=%s tombstone=%s attempts=%s status=%s",
            input_hash,
            log_fields.get("nome_arquivo"),
            log_fields.get("setor_previsto"),
            log_fields.get("operador_previsto"),
            motivo,
            log_fields.get("huawei_call_id") or metadata.get("huawei_call_id"),
            tombstone,
            attempts,
            final_status,
        )
        _unlink_item_media(input_hash, media_path, logger=logger)
        return {"discarded": True, "tombstone": final_status, "attempts": attempts}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sincronizar_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    input_hash: str,
    nome_arquivo: str,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    erro: Optional[str] = None,
    precisa_revisao: bool = False,
    prioridade: str = REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    motivos_revisao: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    status_override: Optional[str] = None,
) -> Optional[int]:
    if not input_hash or not nome_arquivo:
        raise ValueError("input_hash e nome_arquivo são obrigatórios")

    now = datetime.now().isoformat()
    motivos_json = json.dumps(motivos_revisao or [], ensure_ascii=False)
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    huawei_call_id = str(metadata_dict.get("huawei_call_id") or "").strip()
    origem_metadata = str(metadata_dict.get("origem") or "").strip().lower()
    
    if status_override:
        status = status_override
    else:
        status = REVIEW_QUEUE_STATUS_PENDING if precisa_revisao else REVIEW_QUEUE_STATUS_AUTO_RESOLVED
        
    setor_previsto_normalizado = _normalize_sector_id(setor_previsto)
    prioridade_normalizada = normalize_review_priority(
        prioridade,
        default=REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY if not precisa_revisao else REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if origem_metadata == "huawei_sync" and huawei_call_id:
            cursor.execute(
                """
                SELECT 1
                FROM huawei_sync_logs
                WHERE call_id = %s
                  AND status = 'discarded_permanent'
                LIMIT 1
                """,
                (huawei_call_id,),
            )
            if cursor.fetchone():
                conn.rollback()
                return None

        cursor.execute(
            "SELECT id, status FROM fila_revisao_classificacao WHERE input_hash = %s",
            (input_hash,),
        )
        row = cursor.fetchone()

        if row:
            current_status = normalize_review_status(row.get("status"))
            if current_status in PROTECTED_SYNC_STATUSES:
                return int(row["id"])
            cursor.execute(
                """
                UPDATE fila_revisao_classificacao
                SET nome_arquivo = %s, setor_previsto = %s, alerta_previsto = %s, confianca = %s,
                    operador_previsto = %s, erro = %s, prioridade = %s, motivos_json = %s,
                    metadata_json = %s, status = %s, atualizado_em = %s
                WHERE input_hash = %s
                """,
                (
                    nome_arquivo,
                    setor_previsto_normalizado,
                    alerta_previsto,
                    confianca,
                    operador_previsto,
                    erro,
                    prioridade_normalizada,
                    motivos_json,
                    metadata_json,
                    status,
                    now,
                    input_hash,
                ),
            )
            conn.commit()
            return int(row["id"])

        cursor.execute(
            """
            INSERT INTO fila_revisao_classificacao (
                input_hash, nome_arquivo, setor_previsto, alerta_previsto,
                confianca, operador_previsto, erro, prioridade,
                motivos_json, metadata_json, status, criado_em, atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                input_hash,
                nome_arquivo,
                setor_previsto_normalizado,
                alerta_previsto,
                confianca,
                operador_previsto,
                erro,
                prioridade_normalizada,
                motivos_json,
                metadata_json,
                status,
                now,
                now,
            ),
        )
        review_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return review_id
    finally:
        conn.close()


def tentar_iniciar_processamento_auditoria(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    status: str,
    metadata_merge: dict,
    inflight_timeout_seconds: int = 600,
    ignore_status_block: bool = False,
) -> dict:
    """Marca uma gravação como em processamento com lock transacional.

    A rota de auditoria em background pode receber dois cliques quase
    simultâneos. O `FOR UPDATE` serializa essas chamadas para que apenas uma
    delas saia com permissao de criar a task.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    timeout = timedelta(seconds=max(1, int(inflight_timeout_seconds or 600)))
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            FOR UPDATE
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return {"started": False, "reason": "not_found"}

        current_status = normalize_review_status(row["status"])
        metadata = _normalize_metadata_value(row["metadata_json"])
        if current_status in AUDIT_TASK_BLOCKED_STATUSES and not ignore_status_block:
            conn.rollback()
            return {
                "started": False,
                "reason": "blocked_status",
                "status": current_status,
            }

        task_status = str(metadata.get("audit_task_status") or "").strip().lower()
        started_at = _parse_metadata_datetime(metadata.get("audit_task_started_at"))
        if task_status == "processing" and started_at and (now - started_at) < timeout:
            conn.rollback()
            return {
                "started": False,
                "reason": "processing",
                "status": current_status,
                "started_at": metadata.get("audit_task_started_at"),
            }

        metadata.update(metadata_merge or {})
        normalized_status = normalize_review_status(status or current_status)
        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET status = %s,
                metadata_json = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                normalized_status,
                json.dumps(metadata, ensure_ascii=False),
                now_text,
                input_hash,
            ),
        )
        conn.commit()
        return {
            "started": True,
            "status": normalized_status,
            "started_at": metadata.get("audit_task_started_at"),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def atualizar_status_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    status: str,
    erro: Optional[str] = None,
    motivos_revisao_append: Optional[list[str]] = None,
    metadata_merge: Optional[dict] = None,
) -> bool:
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    status_normalizado = normalize_review_status(status)
    if status_normalizado in {REVIEW_QUEUE_STATUS_ALL, REVIEW_QUEUE_STATUS_READY_FOR_AUDIT}:
        raise ValueError("status de consulta nao pode ser persistido")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT erro, motivos_json, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        motivos_existentes = json_loads(row["motivos_json"], [])
        if not isinstance(motivos_existentes, list):
            motivos_existentes = []
        novos_motivos = [str(item).strip() for item in (motivos_revisao_append or []) if str(item).strip()]
        motivos_atualizados = list(dict.fromkeys([*motivos_existentes, *novos_motivos]))

        metadata_atual = _normalize_metadata_value(row["metadata_json"])
        if metadata_merge:
            metadata_atual.update(metadata_merge)

        erro_atualizado = row["erro"] if erro is None else erro

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET status = %s,
                erro = %s,
                motivos_json = %s,
                metadata_json = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                status_normalizado,
                erro_atualizado,
                json.dumps(motivos_atualizados, ensure_ascii=False),
                json.dumps(metadata_atual, ensure_ascii=False),
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def corrigir_classificacao_fila_revisao(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    setor_previsto: str,
    alerta_previsto: str,
    operador_previsto: Optional[str] = None,
    operator_id: Optional[str] = None,
    revisado_por: Optional[str] = None,
) -> Optional[dict]:
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")
    if not setor_previsto or not alerta_previsto:
        raise ValueError("setor_previsto e alerta_previsto sao obrigatorios")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        metadata_atual = _normalize_metadata_value(row["metadata_json"])
        previous_classification = {
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "erro": row["erro"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "status": row["status"],
        }
        metadata_atual["manual_review_source"] = "triagem_ui"
        metadata_atual["manual_reviewed_at"] = datetime.now().isoformat()
        metadata_atual["manual_reviewed_by"] = revisado_por or ""
        metadata_atual["manual_review_previous"] = previous_classification
        # v1.3.96: correcao manual finaliza a classificacao do item. Frontend
        # (RemoteTriageQueue.tsx) le metadata.classification_status para
        # decidir se mostra o botao "Triar"; sem este flip o botao reaparece
        # mesmo com setor/alerta ja preenchidos.
        metadata_atual["classification_status"] = "done"
        metadata_atual["classification_error"] = None
        metadata_atual["manual_review_current"] = {
            "setor_previsto": _normalize_sector_id(setor_previsto),
            "alerta_previsto": alerta_previsto,
            "operador_previsto": operador_previsto,
            "operator_id": operator_id,
            "status": REVIEW_QUEUE_STATUS_REVIEWED,
        }
        if operator_id:
            metadata_atual["operator_id"] = operator_id

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET setor_previsto = %s,
                alerta_previsto = %s,
                operador_previsto = COALESCE(NULLIF(%s, ''), operador_previsto),
                erro = NULL,
                prioridade = %s,
                motivos_json = %s,
                metadata_json = %s,
                status = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                _normalize_sector_id(setor_previsto),
                alerta_previsto,
                str(operador_previsto or "").strip(),
                REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
                json.dumps([], ensure_ascii=False),
                json.dumps(metadata_atual, ensure_ascii=False),
                REVIEW_QUEUE_STATUS_REVIEWED,
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()

        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        updated = cursor.fetchone()
        if not updated:
            return None

        result = {
            "id": updated["id"],
            "input_hash": updated["input_hash"],
            "nome_arquivo": updated["nome_arquivo"],
            "setor_previsto": updated["setor_previsto"],
            "alerta_previsto": updated["alerta_previsto"],
            "confianca": updated["confianca"],
            "operador_previsto": updated["operador_previsto"],
            "erro": updated["erro"],
            "prioridade": updated["prioridade"],
            "motivos_revisao": json_loads(updated["motivos_json"], []),
            "metadata": json_loads(updated["metadata_json"], {}),
            "status": updated["status"],
            "criado_em": updated["criado_em"],
            "atualizado_em": updated["atualizado_em"],
        }
    finally:
        conn.close()

    # === GATILHO DE APRENDIZADO (RLHF) ===
    # Se a IA errou e o humano corrigiu, gera feedback automáticocom embedding
    # para alimentar o RAG semântico nas próximas classificações.
    try:
        ia_alerta = previous_classification.get("alerta_previsto")
        ia_setor = previous_classification.get("setor_previsto")
        # Só aciona se a IA deu uma resposta diferente da correção humana
        if ia_alerta and ia_alerta != alerta_previsto and ia_alerta != "desconhecido":
            transcricao = metadata_atual.get("transcription", "") or ""
            from core.rag_triagem import disparar_feedback_rag_background
            disparar_feedback_rag_background(
                tipo="classificacao",
                situacao=f"A IA classificou como setor='{ia_setor}' alerta='{ia_alerta}'.",
                correcao=f"O correto e setor='{_normalize_sector_id(setor_previsto)}' alerta='{alerta_previsto}'.",
                justificativa="Correcao manual do auditor na fila de triagem.",
                setor=_normalize_sector_id(setor_previsto),
                criado_por=revisado_por or "sistema_rlhf",
                exemplo_transcricao=transcricao[:2000] if transcricao else None,
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Falha ao acionar RAG RLHF: %s", exc)

    return result


def listar_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    limit: Optional[int] = None,
    status: Optional[str] = REVIEW_QUEUE_STATUS_PENDING,
    sector_id: Optional[str] = None,
    origem: Optional[str] = None,
    order_by: str = "priority",
) -> list[dict]:
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


def registrar_resultado_auditoria(
    get_connection: ConnectionFactory,
    ligacao_id: int,
    nota: Optional[float] = None,
    nota_maxima: Optional[float] = None,
    resumo: Optional[str] = None,
    detalhes: Optional[list[dict]] = None,
) -> int:
    now = datetime.now().isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO resultados_auditoria (
                ligacao_id, nota, nota_maxima, resumo, detalhes_json, executado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (ligacao_id, nota, nota_maxima, resumo, json.dumps(detalhes or [], ensure_ascii=False), now),
        )
        resultado_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return int(resultado_id)
    finally:
        conn.close()


def get_resumo_ligacoes_auditadas(get_connection: ConnectionFactory, setor: Optional[str] = None) -> dict:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        setor_normalizado = _normalize_sector_id(setor)

        filtros: list[str] = []
        params: list = []
        if setor_normalizado:
            filtros.append("setor_referencia = %s")
            params.append(setor_normalizado)
        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""

        cursor.execute(f"SELECT COUNT(*) AS total FROM ligacoes_auditadas {where_clause}", params)
        total_ligacoes = int(cursor.fetchone()["total"] or 0)

        qualidade = {"boa": 0, "ruim": 0, "zerada": 0, "indefinida": 0}
        cursor.execute(
            f"""
            SELECT qualidade_referencia, COUNT(*) AS total
            FROM ligacoes_auditadas
            {where_clause}
            GROUP BY qualidade_referencia
            """,
            params,
        )
        for row in cursor.fetchall():
            chave = row["qualidade_referencia"] or "indefinida"
            qualidade[chave] = int(row["total"] or 0)

        cursor.execute(
            f"""
            SELECT COALESCE(setor_referencia, 'indefinido') AS setor, COUNT(*) AS total
            FROM ligacoes_auditadas
            {where_clause}
            GROUP BY COALESCE(setor_referencia, 'indefinido')
            ORDER BY total DESC
            """,
            params,
        )
        por_setor = [{"setor": row["setor"], "total": int(row["total"] or 0)} for row in cursor.fetchall()]

        if setor_normalizado:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT rc.ligacao_id) AS total
                FROM resultados_classificacao rc
                INNER JOIN ligacoes_auditadas la ON la.id = rc.ligacao_id
                WHERE la.setor_referencia = %s
                """,
                (setor_normalizado,),
            )
        else:
            cursor.execute("SELECT COUNT(DISTINCT ligacao_id) AS total FROM resultados_classificacao")
        classificadas = int(cursor.fetchone()["total"] or 0)

        if setor_normalizado:
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN rc.acertou_setor = 1 THEN 1 ELSE 0 END) AS acertos_setor,
                    SUM(CASE WHEN rc.acertou_alerta = 1 THEN 1 ELSE 0 END) AS acertos_alerta,
                    COUNT(CASE WHEN rc.acertou_setor IS NOT NULL THEN 1 END) AS total_comparacao_setor,
                    COUNT(CASE WHEN rc.acertou_alerta IS NOT NULL THEN 1 END) AS total_comparacao_alerta
                FROM resultados_classificacao rc
                INNER JOIN ligacoes_auditadas la ON la.id = rc.ligacao_id
                WHERE la.setor_referencia = %s
                """,
                (setor_normalizado,),
            )
        else:
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN acertou_setor = 1 THEN 1 ELSE 0 END) AS acertos_setor,
                    SUM(CASE WHEN acertou_alerta = 1 THEN 1 ELSE 0 END) AS acertos_alerta,
                    COUNT(CASE WHEN acertou_setor IS NOT NULL THEN 1 END) AS total_comparacao_setor,
                    COUNT(CASE WHEN acertou_alerta IS NOT NULL THEN 1 END) AS total_comparacao_alerta
                FROM resultados_classificacao
                """
            )
        metricas = cursor.fetchone()
        total_comp_setor = int(metricas["total_comparacao_setor"] or 0)
        total_comp_alerta = int(metricas["total_comparacao_alerta"] or 0)
        taxa_acerto_setor = round((int(metricas["acertos_setor"] or 0) / total_comp_setor) * 100, 2) if total_comp_setor else None
        taxa_acerto_alerta = round((int(metricas["acertos_alerta"] or 0) / total_comp_alerta) * 100, 2) if total_comp_alerta else None
    finally:
        conn.close()

    return {
        "total_ligacoes": total_ligacoes,
        "classificadas": classificadas,
        "qualidade": qualidade,
        "por_setor": por_setor,
        "taxa_acerto_setor": taxa_acerto_setor,
        "taxa_acerto_alerta": taxa_acerto_alerta,
    }


def listar_ligacoes_auditadas(
    get_connection: ConnectionFactory,
    limit: int = 100,
    qualidade: Optional[str] = None,
    setor: Optional[str] = None,
) -> list[dict]:
    limite = max(1, min(int(limit), 500))
    qualidade_normalizada = normalize_quality_reference(qualidade) if qualidade else None
    setor_normalizado = _normalize_sector_id(setor)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        filtros = []
        params: list = []
        if qualidade_normalizada and qualidade_normalizada != "indefinida":
            filtros.append("la.qualidade_referencia = %s")
            params.append(qualidade_normalizada)
        if setor_normalizado:
            filtros.append("la.setor_referencia = %s")
            params.append(setor_normalizado)
        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""

        query = f"""
            SELECT
                la.id, la.nome_arquivo, la.caminho_relativo, la.hash_arquivo, la.grupo, la.subgrupo,
                la.setor_referencia, la.alerta_referencia, la.qualidade_referencia, la.observacao,
                la.criado_em, la.atualizado_em,
                rc.setor_previsto, rc.alerta_previsto, rc.confianca, rc.operador_previsto,
                rc.acertou_setor, rc.acertou_alerta, rc.erro, rc.executado_em AS classificacao_em
            FROM ligacoes_auditadas la
            LEFT JOIN resultados_classificacao rc
                ON rc.id = (
                    SELECT id FROM resultados_classificacao sub
                    WHERE sub.ligacao_id = la.id
                    ORDER BY sub.id DESC
                    LIMIT 1
                )
            {where_clause}
            ORDER BY la.id DESC
            LIMIT %s
        """
        params.append(limite)
        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "nome_arquivo": row["nome_arquivo"],
            "caminho_relativo": row["caminho_relativo"],
            "hash_arquivo": row["hash_arquivo"],
            "grupo": row["grupo"],
            "subgrupo": row["subgrupo"],
            "setor_referencia": row["setor_referencia"],
            "alerta_referencia": row["alerta_referencia"],
            "qualidade_referencia": row["qualidade_referencia"],
            "observacao": row["observacao"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
            "classificacao": {
                "setor_previsto": row["setor_previsto"],
                "alerta_previsto": row["alerta_previsto"],
                "confianca": row["confianca"],
                "operador_previsto": row["operador_previsto"],
                "acertou_setor": None if row["acertou_setor"] is None else bool(row["acertou_setor"]),
                "acertou_alerta": None if row["acertou_alerta"] is None else bool(row["acertou_alerta"]),
                "erro": row["erro"],
                "executado_em": row["classificacao_em"],
            },
        }
        for row in rows
    ]
