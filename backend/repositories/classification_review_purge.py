"""Purga e descarte de itens da fila de triagem (`fila_revisao_classificacao`).

Remove linhas da fila liberando o UNIQUE `input_hash`, gerencia o tombstone
permanente em `huawei_sync_logs` (`discarded_permanent`) e apaga a mídia
física do storage (melhor esforço, após o commit). Dois modos:
- limpeza por idade (`limpar_fila_revisao_classificacao_antiga`): só itens
  explicitamente arquivados/descartáveis;
- descarte em modo automação (`descartar_item_automacao`): braço de descarte da
  esteira binária, definitivo por call_id.

Extraído de `repositories/classification_review.py` (v1.3.143); os nomes seguem reexportados de
`repositories.classification_review` (e da fachada `db.database`).

Os imports de `db.database.huawei_sync_log_tombstone` e
`storage.audit_storage.resolve_stored_audit_audio_path` são feitos em RUNTIME
dentro das funções (evita import circular e preserva o monkeypatch dos testes).
"""

from typing import Callable, Optional, Any

from repositories.common import harden_jsonb_nul_cast, json_loads


ConnectionFactory = Callable[[], Any]


def _unlink_item_media(input_hash: str, media_path: Optional[str], *, logger=None) -> None:
    """Apaga do storage o áudio classificado de um item purgado (melhor esforço).

    Falha de I/O vira apenas warning: o item já saiu da fila e a mídia órfã
    será recolhida depois pela limpeza de storage da automação.
    """
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
    sync_log_action: str = "tombstone_permanent",
    tombstone_motivo: Optional[str] = None,
    loop_limit: int = 3,
    logger=None,
) -> tuple[Optional[str], Optional[tuple[int, str]]]:
    """Remove o item da fila (libera o UNIQUE input_hash) e trata o huawei_sync_logs
    conforme `sync_log_action`:
      - "delete": legado; hoje tambem vira tombstone para bloquear reentrada.
      - "tombstone_recoverable": legado; hoje tambem deve bloquear reentrada.
      - "tombstone_permanent": marca 'discarded_permanent' (tombstone; nunca rebaixa).

    Roda dentro da transação do caller (recebe cursor; NÃO faz commit) — a
    mídia física só deve ser apagada pelo caller após o commit.
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
    Remove somente itens explicitamente arquivados/descartáveis há mais de X horas.

    Elegibilidade: `metadata.archived` ou `metadata.cleanup_discardable` = true.
    A fila de revisão guarda trabalho operacional dos auditores; por isso a
    limpeza automática NÃO remove estados pendentes, bloqueados ou em triagem
    manual apenas por idade.

    O `huawei_sync_logs` correspondente vira tombstone permanente quando há
    call_id Huawei; limpeza/arquivo descartado não deve voltar em novo sync.
    A mídia física é removida após o commit (melhor esforço). Retorna
    {"deleted": n}.
    """
    from datetime import datetime, timedelta, timezone
    import logging

    logger = logging.getLogger(__name__)
    cutoff_date = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            harden_jsonb_nul_cast(
            """
            SELECT input_hash, metadata_json
            FROM fila_revisao_classificacao
            WHERE atualizado_em < %s
              AND (
                    COALESCE(metadata_json::jsonb ->> 'archived', 'false') = 'true'
                 OR COALESCE(metadata_json::jsonb ->> 'cleanup_discardable', 'false') = 'true'
              )
            """
            ),
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

            media_path, _ = _purgar_item_fila(
                cursor,
                input_hash,
                metadata,
                sync_log_action="tombstone_permanent",
                tombstone_motivo="limpeza_fila_antiga",
                logger=logger,
            )
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
    tombstone: bool = True,
    tombstone_motivo: Optional[str] = None,
    loop_limit: int = 3,
    log_fields: Optional[dict] = None,
) -> dict:
    """Descarta um item da fila no modo automação: remove a linha da fila em transação,
    marca o huawei_sync_logs como descartado (tombstone) e apaga a mídia após o commit.
    No-op idempotente se o item já não existir.

    tombstone=True  -> 'discarded_permanent' (impossível de auditar; nunca rebaixa).
    tombstone=False -> compatibilidade legada. A regra operacional atual é:
                       item descartado nunca deve voltar em novo sync.

    Braço de descarte da esteira binária v1.3.103 (chamado via
    `core/automation_disposition.execute_discard`). Retorna
    {"discarded": bool, "tombstone": status final ou None, "attempts": n ou None}.
    """
    import logging

    logger = logging.getLogger(__name__)
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")
    log_fields = log_fields or {}
    sync_log_action = "tombstone_permanent"

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
