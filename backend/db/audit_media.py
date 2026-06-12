"""Mídia e persistência de auditoria — anexo de áudio e funil de artefatos.

Lógica extraída de `db.database` (que segue como fachada fina): gravação e
recuperação do áudio da auditoria no storage e o funil único de persistência
de uma auditoria concluída (`persist_audit_artifacts`). Chamadas a funções
que permanecem na fachada são resolvidas em runtime via `db.database`
(import tardio) para evitar import circular e preservar monkeypatches.
CUSTO DE API: zero — nenhuma chamada a serviços pagos; somente PostgreSQL.
"""

import logging
from datetime import datetime
from typing import Optional

from storage.audit_storage import resolve_stored_audit_audio_path, store_audit_audio_file
from db.domain_constants import (
    DEFAULT_AUDIT_STATUS,
    REVIEW_QUEUE_STATUS_AUDITED,
)
from repositories.common import normalize_source_type
from schemas import AuditResult


logger = logging.getLogger(__name__)


def _attach_audio_to_audit_record(
    audit_id: int,
    *,
    audio_bytes: bytes,
    audio_mime_type: Optional[str],
    original_filename: Optional[str],
    input_hash: Optional[str],
) -> Optional[dict]:
    """Grava o áudio da auditoria no storage e registra os metadados na linha do audit.

    Idempotente: se já existe áudio armazenado e o arquivo está acessível,
    reutiliza. Se o UPDATE no banco falhar após gravar o arquivo, desfaz a
    gravação (não deixa arquivo órfão).
    """
    from db import database as dbm

    if not audio_bytes:
        return None

    from repositories.audits import (
        get_audit_media_record_by_id as repository_get_audit_media_record_by_id,
        update_audit_audio_storage as repository_update_audit_audio_storage,
    )

    existing = repository_get_audit_media_record_by_id(dbm.get_connection, audit_id)
    if existing and existing.get("audio_storage_path"):
        existing_path = resolve_stored_audit_audio_path(existing.get("audio_storage_path"))
        if existing_path and existing_path.exists():
            return existing

    stored = store_audit_audio_file(
        audit_id=audit_id,
        audio_bytes=audio_bytes,
        mime_type=audio_mime_type,
        original_filename=original_filename,
        input_hash=input_hash,
        existing_relative_path=existing.get("audio_storage_path") if existing else None,
    )
    try:
        repository_update_audit_audio_storage(
            dbm.get_connection,
            audit_id,
            audio_storage_path=stored["audio_storage_path"],
            audio_original_filename=stored["audio_original_filename"],
            audio_mime_type=stored["audio_mime_type"],
            audio_size_bytes=stored["audio_size_bytes"],
        )
    except Exception:
        stored_path = resolve_stored_audit_audio_path(stored["audio_storage_path"])
        if stored_path and stored_path.exists():
            stored_path.unlink(missing_ok=True)
        raise

    return stored


def attach_audio_to_audit_record(
    audit_id: int,
    *,
    audio_bytes: bytes,
    audio_mime_type: Optional[str],
    original_filename: Optional[str],
    input_hash: Optional[str],
) -> Optional[dict]:
    """Versão pública de `_attach_audio_to_audit_record` (mesma semântica)."""
    return _attach_audio_to_audit_record(
        audit_id,
        audio_bytes=audio_bytes,
        audio_mime_type=audio_mime_type,
        original_filename=original_filename,
        input_hash=input_hash,
    )


def recover_audit_audio_from_classified_queue(
    audit_id: int,
    audit: Optional[dict] = None,
    media_record: Optional[dict] = None,
) -> Optional[dict]:
    """Recupera o áudio de uma auditoria sem mídia a partir da fila de classificados.

    Caminho de auto-reparo: localiza o item da fila vinculado à auditoria,
    carrega o áudio do storage classificado e anexa ao registro do audit.
    Qualquer falha devolve o `media_record` original (best-effort, só loga).
    """
    from db import database as dbm

    audit = audit or dbm.get_audit_by_id(audit_id)
    if not audit:
        return media_record

    audit_input_hash = str(audit.get("input_hash") or "").strip()
    try:
        queue_item = dbm.obter_fila_revisao_classificacao_por_auditoria(
            audit_id,
            audit_input_hash or None,
        )
    except Exception:
        logger.warning("Falha ao localizar fila de audio classificado para audit %s", audit_id, exc_info=True)
        return media_record

    metadata = queue_item.get("metadata") if isinstance(queue_item, dict) else None
    if not isinstance(metadata, dict):
        return media_record

    classified_audio_path = str(metadata.get("classified_audio_path") or "").strip()
    if not classified_audio_path:
        return media_record

    try:
        from core.automation import load_classified_audio
        from core.classification import get_mime_type

        audio_bytes = load_classified_audio(classified_audio_path)
    except Exception:
        logger.warning("Falha ao carregar audio classificado para audit %s", audit_id, exc_info=True)
        return media_record

    if not audio_bytes:
        return media_record

    fallback_filename = (media_record or {}).get("audio_original_filename")
    filename = str(queue_item.get("nome_arquivo") or fallback_filename or "").strip()
    mime_type = (media_record or {}).get("audio_mime_type") or get_mime_type(filename)
    try:
        # Via fachada (dbm) de propósito: testes patcham
        # `database.attach_audio_to_audit_record` — chamada direta furaria o patch.
        return dbm.attach_audio_to_audit_record(
            audit_id,
            audio_bytes=audio_bytes,
            audio_mime_type=mime_type,
            original_filename=filename or fallback_filename,
            input_hash=audit_input_hash or None,
        )
    except Exception:
        logger.warning("Falha ao recuperar audio classificado para audit %s", audit_id, exc_info=True)
        return media_record


def persist_audit_artifacts(
    result: AuditResult,
    *,
    from_cache: bool,
    input_hash: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    operator_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    sector_id: Optional[str] = None,
    ai_feedback: Optional[str] = None,
    status: str = DEFAULT_AUDIT_STATUS,
    audio_bytes: Optional[bytes] = None,
    audio_mime_type: Optional[str] = None,
    original_filename: Optional[str] = None,
    criado_por: str = "",
    sync_saved_file: bool = True,
) -> Optional[int]:
    """Funil ÚNICO de persistência de uma auditoria concluída (manual ou automática).

    Em uma passada: salva o audit (ou reaproveita cache), anexa o áudio,
    marca o item da fila como `audited` e espelha em Arquivos Salvos.
    Também normaliza `sector_id` (fix de acento, v1.3.106). Retorna o
    audit_id ou None quando nada foi salvo.
    """
    from db import database as dbm

    def _sync_queue_as_audited(audit_id: int) -> None:
        """Marca o item da fila como audited e grava o vínculo audit_id/hash no metadata."""
        if not input_hash:
            return
        try:
            dbm.atualizar_status_fila_revisao_classificacao(
                input_hash,
                status=REVIEW_QUEUE_STATUS_AUDITED,
                metadata_merge={
                    "audit_id": audit_id,
                    "audit_input_hash": input_hash,
                    "audited_at": datetime.now().isoformat(),
                },
            )
        except Exception:
            logger.warning(
                "Nao foi possivel atualizar a fila de triagem para auditado (hash=%s)",
                input_hash,
                exc_info=True,
            )

    normalized_source_type = normalize_source_type(result.source_type, default=None)

    if from_cache:
        if input_hash and audio_bytes and normalized_source_type == "audio":
            from repositories.audits import get_audit_media_record_by_hash as repository_get_audit_media_record_by_hash

            existing = repository_get_audit_media_record_by_hash(dbm.get_connection, input_hash)
            if existing:
                _attach_audio_to_audit_record(
                    existing["id"],
                    audio_bytes=audio_bytes,
                    audio_mime_type=audio_mime_type,
                    original_filename=original_filename,
                    input_hash=input_hash,
                )
                _sync_queue_as_audited(existing["id"])
                if sync_saved_file:
                    dbm._sync_arquivo_salvo_for_audit(existing["id"], criado_por=criado_por)
                return existing["id"]
        return None

    # ── Cross-reference with colaboradores ────────────────────────────
    # If the operator is known in our database, use the colaborador's
    # setor instead of whatever the classification guessed.
    # Also resolve colaborador_id for FK linkage.
    effective_sector_id = sector_id
    resolved_colaborador_id: Optional[int] = None
    operator_name = result.operatorName
    colab = None
    from repositories import operators
    if operator_name:
        colab = operators.buscar_colaborador_por_nome(dbm.get_connection, operator_name)
        if not colab and operator_id:
            # Fallback: try matching by Huawei/telefonia ID
            colab = operators.buscar_colaborador_por_id_huawei(dbm.get_connection, operator_id)
        if colab:
            colab_setor = (colab.get("setor") or "").strip()
            if colab_setor:
                effective_sector_id = colab_setor
            # Resolve the colaborador_id for FK linkage
            colab_id = colab.get("id")
            if colab_id:
                resolved_colaborador_id = int(colab_id)

    # ── Canonicaliza o sector_id no funil (somente escritas novas) ────
    # Resolve a forma crua ("FÊNIX", "célula") para o id canonico do catalogo via
    # sector_aliases. Mantem a forma crua se nenhuma regra casar (nao perde dado).
    # Fix do item 4 (acento/forma inconsistente em audits.sector_id); NAO reescreve
    # auditorias historicas.
    if effective_sector_id:
        try:
            from repositories import sector_aliases as _sector_aliases
            _canonical = _sector_aliases.resolve_canonical_sector(
                dbm.get_connection,
                setor=str(effective_sector_id),
                escala=(colab.get("escala") if colab else "") or "",
                supervisor=(colab.get("supervisor") if colab else "") or "",
                organizacao=(colab.get("organizacao_telefonia") if colab else "") or "",
            )
            if _canonical:
                effective_sector_id = _canonical
        except Exception:
            logger.warning(
                "Falha ao canonicalizar sector_id '%s'; mantendo forma crua",
                effective_sector_id,
                exc_info=True,
            )

    audit_id = dbm.save_audit(
        result,
        input_hash=input_hash,
        alert_id=alert_id,
        alert_label=alert_label,
        operator_id=operator_id,
        driver_name=driver_name,
        sector_id=effective_sector_id,
        ai_feedback=ai_feedback,
        status=status,
        colaborador_id=resolved_colaborador_id,
        criado_por=criado_por,
    )
    if audit_id and audio_bytes and normalized_source_type == "audio":
        _attach_audio_to_audit_record(
            audit_id,
            audio_bytes=audio_bytes,
            audio_mime_type=audio_mime_type,
            original_filename=original_filename,
            input_hash=input_hash,
        )
    if audit_id:
        try:
            from repositories import transcript_candidates

            transcript_candidates.persist_for_audit(
                dbm.get_connection,
                audit_id=audit_id,
                input_hash=input_hash,
                audio_quality=result.audio_quality,
            )
        except Exception:
            logger.warning(
                "Nao foi possivel persistir candidatos de transcricao (audit_id=%s)",
                audit_id,
                exc_info=True,
            )
        _sync_queue_as_audited(audit_id)
        if sync_saved_file:
            dbm._sync_arquivo_salvo_for_audit(audit_id, criado_por=criado_por)
    return audit_id
