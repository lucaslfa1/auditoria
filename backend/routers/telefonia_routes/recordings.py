"""Endpoints da fila de gravações da Telefonia (listar, remover, áudio) e debug OBS.

Movidos de routers/telefonia.py sem mudança de comportamento: helpers e
constantes do módulo continuam no orquestrador e são acessados em runtime
via `tf.<nome>` (preserva monkeypatch e estado compartilhado).
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import db.database as database
from db.domain_constants import (
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
)
from repositories import classification_review, configuration
from repositories.common import json_loads
from routers import telefonia as tf
from routers.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/recordings")
async def listar_gravacoes(
    limit: Optional[int] = None,
    operator: Optional[str] = None,
    _user: dict = Depends(require_admin),
) -> Dict[str, Any]:
    """Lista itens recentes vindos da Huawei na fila de revisao de triagem."""
    try:
        fila = classification_review.listar_fila_revisao_classificacao(database.get_connection,
            limit=limit,
            status="all",
            origem="huawei_sync",
            order_by="recent"
        )
    except Exception:
        logger.exception("Falha ao listar fila de revisao")
        fila = []

    vindos_huawei = []
    search_term = operator.strip().lower() if operator else None

    for item in (fila or []):
        if not tf._is_visible_telefonia_recording(item):
            continue

        parsed_item = tf._recording_item_from_queue(item)
        if search_term:
            op_name = str(parsed_item.get("operator_name") or "").strip().lower()
            if search_term not in op_name:
                continue

        vindos_huawei.append(parsed_item)

    return {"items": vindos_huawei, "total": len(vindos_huawei)}
@router.delete("/recordings")
def remover_todas_gravacoes(_user: dict = Depends(require_admin)):
    """
    Remove da tela e da fila todas as ligações que ainda não foram para triagem
    (que não estão em status terminal nem em triagem manual).
    """
    conn = database.get_connection()
    try:
        cursor = conn.cursor()

        # Pega as hashes e os IDs do Huawei para apagar em lote
        cursor.execute(
            """
            SELECT input_hash, metadata_json
            FROM fila_revisao_classificacao
            WHERE status NOT IN ('audited', 'monthly_capped', 'reviewed', 'needs_manual_triage', 'blocked_operator')
            """
        )
        rows = cursor.fetchall()

        hashes_to_delete = []
        huawei_ids_to_delete = []

        for row in rows:
            input_hash = row["input_hash"]
            raw_meta = row["metadata_json"]
            meta = json_loads(raw_meta, {})
            if not isinstance(meta, dict):
                meta = {}

            if meta.get("archived"):
                continue

            # Apenas apagar gravações que vieram da integração Huawei
            if str(meta.get("origem") or "").lower() != "huawei_sync":
                continue

            # Depois do envio, a posse visual passa para a Triagem. O botao
            # "Limpar Pendentes" da Telefonia nao deve apagar esses itens.
            if meta.get("telefonia_triage_requested_at") or meta.get("telefonia_triage_requested_by"):
                continue

            # Não excluir itens que já estão na Triagem prontos para revisão manual
            if meta.get("classification_status") == "done":
                continue

            hashes_to_delete.append(input_hash)
            if meta.get("huawei_call_id"):
                huawei_ids_to_delete.append(str(meta.get("huawei_call_id")))

        if hashes_to_delete:
            cursor.execute(
                """
                DELETE FROM fila_revisao_classificacao
                WHERE input_hash = ANY(%s)
                """,
                (hashes_to_delete,)
            )

        if huawei_ids_to_delete:
            cursor.execute(
                "DELETE FROM huawei_sync_logs WHERE call_id = ANY(%s)",
                (huawei_ids_to_delete,)
            )

        conn.commit()
        return {"status": "ok", "message": f"{len(hashes_to_delete)} ligações removidas com sucesso.", "deleted": len(hashes_to_delete)}
    except Exception as exc:
        logger.exception("Falha ao remover todas as gravacoes: %s", exc)
        raise HTTPException(status_code=500, detail="Erro ao limpar gravações pendentes.")
    finally:
        conn.close()

@router.delete("/recordings/{input_hash}")
def remover_gravacao(input_hash: str, _user: dict = Depends(require_admin)):
    """
    Remove uma gravacao da fila.
    - Se estiver auditada/cota mensal: apenas marca como arquivada para sumir da tela.
    - Se estiver pendente ou em outro status: apaga do banco para permitir novo download.
    """
    item = tf._get_recording_queue_item_or_404(input_hash, require_audio=False)
    status = str(item.get("status") or "").strip().lower()
    metadata = tf._queue_metadata(item)
    huawei_call_id = str(metadata.get("huawei_call_id") or "").strip()

    if status in {REVIEW_QUEUE_STATUS_AUDITED, REVIEW_QUEUE_STATUS_MONTHLY_CAPPED}:
        # Apenas "oculta" do frontend marcando metadata.archived=true.
        # Nao mexemos no status de fila (que e dominio reservado a estados validos).
        ok = classification_review.atualizar_status_fila_revisao_classificacao(database.get_connection,
            input_hash,
            status=status,
            metadata_merge={
                "archived": True,
                "archived_at": tf._utc_now_iso(),
            },
        )
        if not ok:
            raise HTTPException(status_code=404, detail="Gravacao nao encontrada.")
        return {"status": "ok", "message": "Ligacao auditada foi ocultada da fila.", "action": "archived"}

    # Exclui de fato para que a coleta possa baixa-la novamente (se for oficial).
    # is_oficial vem do LATERAL JOIN em obter_fila_revisao_classificacao_por_hash;
    # default True garante que ao redownload nao seja bloqueado quando o campo
    # nao puder ser calculado (ex: testes legados sem o JOIN).
    conn = database.get_connection()
    try:
        cursor = conn.cursor()

        is_oficial = bool(item.get("is_oficial", True))

        cursor.execute(
            "DELETE FROM fila_revisao_classificacao WHERE input_hash = %s",
            (input_hash,),
        )
        if huawei_call_id:
            if is_oficial:
                # Permite que o proximo sync redescubra esta chamada na Huawei.
                cursor.execute(
                    "DELETE FROM huawei_sync_logs WHERE call_id = %s",
                    (huawei_call_id,),
                )
            else:
                # Option A: Operador sem cadastro. Se reimportarmos, volta com erro.
                # Portanto, ignoramos permanentemente no sync log.
                cursor.execute(
                    """
                    INSERT INTO huawei_sync_logs (call_id, status, failure_reason, sincronizado_em)
                    VALUES (%s, 'skipped_operator', 'operador_huawei_nao_cadastrado', CURRENT_TIMESTAMP)
                    ON CONFLICT (call_id) DO UPDATE
                    SET status = 'skipped_operator',
                        failure_reason = 'operador_huawei_nao_cadastrado',
                        sincronizado_em = CURRENT_TIMESTAMP;
                    """,
                    (huawei_call_id,)
                )
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "message": "Ligacao excluida.", "action": "deleted"}

@router.get("/recordings/{input_hash}/audio")
def obter_audio_gravacao(
    input_hash: str,
    _user: dict = Depends(require_admin),
):
    """Serve o audio classificado de uma gravacao da fila para player autenticado."""
    item = tf._get_recording_queue_item_or_404(input_hash)
    media_path = tf._recording_media_path(item)
    if not media_path or not tf._recording_is_audio(item):
        raise HTTPException(status_code=404, detail="Audio da gravacao nao encontrado.")

    stream = tf.open_classified_audio_stream(media_path, input_hash=input_hash)
    if stream is None:
        raise HTTPException(status_code=404, detail="Arquivo de audio da gravacao nao encontrado.")

    iterator, content_length = stream
    filename = str(item.get("nome_arquivo") or media_path or "gravacao.wav")
    safe_name = tf._safe_filename(filename, fallback="gravacao.wav")
    headers = {"Content-Disposition": f'inline; filename="{safe_name}"'}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return StreamingResponse(
        iterator,
        media_type=tf.get_mime_type(filename) or "audio/wav",
        headers=headers,
    )


@router.get("/debug/obs")
async def debug_obs_root(user: dict = Depends(require_admin)):
    """Lista as primeiras 30 pastas/chaves na raiz do OBS para descobrirmos o formato."""
    from core.huawei_obs_client import HuaweiOBSClient
    import db.database as database

    ak = str(configuration.get_config_value(database.get_connection, "huawei_obs_ak", "") or "").strip()
    sk = str(configuration.get_config_value(database.get_connection, "huawei_obs_sk", "") or "").strip()
    bucket = str(configuration.get_config_value(database.get_connection, "huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(configuration.get_config_value(database.get_connection, "huawei_obs_endpoint", "") or "").strip()

    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}

    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)
    try:
        keys = await client._list_keys(prefix="")
        return {
            "bucket": bucket,
            "root_keys": keys[:30] if keys else [],
            "message": "Sucesso" if keys else "Bucket parece estar vazio na raiz!"
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/debug/obs/search")
async def debug_obs_search(user: dict = Depends(require_admin)):
    """Procura pastas uteis no OBS."""
    from core.huawei_obs_client import HuaweiOBSClient
    import db.database as database
    from datetime import datetime, timezone

    ak = str(configuration.get_config_value(database.get_connection, "huawei_obs_ak", "") or "").strip()
    sk = str(configuration.get_config_value(database.get_connection, "huawei_obs_sk", "") or "").strip()
    bucket = str(configuration.get_config_value(database.get_connection, "huawei_obs_bucket", "") or "").strip()
    endpoint_url = str(configuration.get_config_value(database.get_connection, "huawei_obs_endpoint", "") or "").strip()

    if not all([ak, sk, bucket]):
        return {"error": "Credenciais OBS ausentes no banco"}

    client = HuaweiOBSClient(ak=ak, sk=sk, bucket=bucket, endpoint=endpoint_url)

    agora = datetime.now(timezone.utc)
    date_str = agora.strftime("%Y%m%d")

    prefixes_to_test = [
        f"Voice/{date_str}/",
        f"voice/{date_str}/",
        f"Recordings/{date_str}/",
        f"recordings/{date_str}/",
        f"Contact_Record/",
        "Voice/",
        "Recordings/"
    ]

    results = {}

    for prefix in prefixes_to_test:
        try:
            keys = await client._list_keys(prefix=prefix)
            results[prefix] = keys[:10] if keys else []
        except Exception as e:
            results[prefix] = f"Error: {e}"

    return {
        "bucket": bucket,
        "search_results": results
    }
