import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from core.audit_pipeline import (
    AuditPipelineContext,
    attach_pipeline_context_to_audio_quality,
)
from db.domain_constants import (
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_PENDING,
    SOURCE_TYPE_AUDIO,
)

logger = logging.getLogger(__name__)


def _selected_transcription_strategy(audio_quality: Any) -> str:
    if not isinstance(audio_quality, dict):
        return ""
    provider = audio_quality.get("transcription_provider")
    if not isinstance(provider, dict):
        return ""
    return str(provider.get("selected_strategy") or "").strip().lower()


def _satisfies_transcription_policy(audio_quality: Any) -> bool:
    # Politica atual: fast e o engine padrao. Aceita qualquer transcricao com
    # estrategia valida selecionada (fast, hybrid_dual, gpt4o_diarize, whisper...).
    # O gate rejeita apenas transcricao ausente/vazia.
    if not isinstance(audio_quality, dict):
        return False
    provider = audio_quality.get("transcription_provider")
    if not isinstance(provider, dict):
        return False
    return bool(_selected_transcription_strategy(audio_quality))


class AuditCacheGatekeeper:
    """
    Serviço focado na validação de cache de auditorias e na verificação de regras
    de qualidade de transcrição para itens provenientes do cache.
    """

    @classmethod
    def check_existing_audit(
        cls,
        db_connection,
        audit_input_hash: str,
        pipeline_context: AuditPipelineContext,
        media_bytes: bytes,
        mime_type: str,
        filename: str,
        queue_input_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Verifica se a auditoria já existe no banco. Se existir, valida a qualidade da
        transcrição. Se a transcrição precisar de revisão, bloqueia o fluxo e retorna
        para triagem manual. Caso contrário, re-persiste ou recupera a auditoria e
        marca como auditada.

        Retorna:
            Dict: Metadados para interromper e retornar o status do _audit_single_item,
            ou None caso o fluxo deva seguir normalmente para a transcrição/IA.
        """
        from repositories import audits
        from core.automation import (
            _mark_item_status,
            _automatic_audio_transcription_review_reasons,
            _audit_on_transcription_risk_enabled,
            _discard_impossible_transcription_enabled,
            AuditPersistenceError,
            database,
        )
        from core.automation_disposition import Disposition, execute_discard
        from core.transcription_quality import transcription_is_empty

        existing = audits.get_audit_by_hash(db_connection, audit_input_hash)
        if not existing:
            return None

        logger.info("Item '%s' ja auditado (hash encontrado). Marcando fila como auditada.", filename)
        
        if pipeline_context.source_type == SOURCE_TYPE_AUDIO:
            existing.audio_quality = attach_pipeline_context_to_audio_quality(
                getattr(existing, "audio_quality", None),
                pipeline_context,
            )
            audio_quality = getattr(existing, "audio_quality", None)
            selected_strategy = _selected_transcription_strategy(audio_quality)
            if not _satisfies_transcription_policy(audio_quality):
                logger.info(
                    "Automacao: cache de '%s' ignorado porque a transcricao em cache nao tem "
                    "estrategia valida (selected_strategy=%s).",
                    filename,
                    selected_strategy or "ausente",
                )
                return None

            review_reasons = _automatic_audio_transcription_review_reasons(audio_quality)

            # So transcricao GENUINAMENTE VAZIA (sem texto) e impossivel de auditar -> DESCARTA
            # permanente. Qualidade ruim mas com conteudo NAO descarta (segue p/ o auditor).
            if transcription_is_empty(audio_quality) and _discard_impossible_transcription_enabled():
                return execute_discard(
                    None,
                    Disposition.DISCARD_IMPOSSIBLE,
                    motivo="transcricao_impossivel",
                    status_result="discarded_impossible_transcription",
                    queue_input_hash=queue_input_hash,
                    filename=filename,
                    sector_id=getattr(pipeline_context, "sector_id", None),
                    operator_name=getattr(pipeline_context, "operator_name", None),
                )

            # Se já auditamos antes, mas agora a regra exige que haja uma transcrição melhor (premium)
            # bloqueia e exige intervenção manual (triagem). Gateado por
            # AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK (default ON): se ligado, audita mesmo assim.
            if review_reasons and not _audit_on_transcription_risk_enabled():
                _mark_item_status(
                    queue_input_hash,
                    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
                    "Transcricao em cache requer revisao manual antes da auditoria automatica",
                    motivos_revisao_append=TranscriptionFallbackGatekeeper._queue_motivos_for_transcription_review(review_reasons),
                    metadata_merge={
                        "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                        "audit_input_hash": audit_input_hash,
                        "cached_audit_id": getattr(existing, "id", None),
                        "audit_pipeline": pipeline_context.to_audit_metadata(),
                        "audio_quality_review": TranscriptionFallbackGatekeeper._audio_quality_triage_metadata(getattr(existing, "audio_quality", None)),
                    },
                )
                logger.info(
                    "Automacao: '%s' voltou para triagem manual porque a transcricao em cache requer revisao (%s).",
                    filename,
                    ", ".join(review_reasons),
                )
                return {"status": "blocked_transcription_quality", "reasons": review_reasons}
            
            # Re-persiste artefatos (pode estar faltando arquivo no storage mesmo existindo no banco)
            audit_id = database.persist_audit_artifacts(
                existing,
                from_cache=True,
                input_hash=audit_input_hash,
                audio_bytes=media_bytes,
                audio_mime_type=mime_type,
                original_filename=filename,
                criado_por="automacao",
            )
        else:
            # Fluxo de PDF: Recupera apenas o ID sem salvar arquivo de áudio
            existing_record = audits.get_audit_media_record_by_hash(db_connection, audit_input_hash)
            audit_id = existing_record.get("id") if existing_record else None
            
        if not audit_id:
            raise AuditPersistenceError(
                f"Auditoria em cache sem id recuperavel para '{filename}'."
            )
            
        _mark_item_status(
            queue_input_hash,
            REVIEW_QUEUE_STATUS_AUDITED,
            metadata_merge={
                "audit_synced_from_existing": True,
                "audit_id": audit_id,
                "audit_input_hash": audit_input_hash,
                "audit_pipeline": pipeline_context.to_audit_metadata(),
            },
        )
        return {"status": "audited", "audit_id": audit_id}


class TranscriptionFallbackGatekeeper:
    """
    Serviço focado em tratar e padronizar exceções originadas pelo motor de Inteligência
    Artificial (e.g. timeout da API, falha do modelo hybrid_dual) e avaliar se a
    transcrição recém gerada possui qualidade suficiente para ser validada automaticamente.
    """

    @staticmethod
    def _queue_motivos_for_transcription_review(reasons: list[str]) -> list[str]:
        motivos = ["transcricao_requer_revisao"]
        for reason in reasons:
            normalized = str(reason or "").strip().lower().replace(":", "_")
            if not normalized:
                continue
            motivo = normalized if normalized.startswith("transcricao") else f"transcricao_{normalized}"
            if motivo not in motivos:
                motivos.append(motivo)
        return motivos

    @staticmethod
    def _audio_quality_triage_metadata(audio_quality: Any) -> dict[str, Any]:
        if not isinstance(audio_quality, dict):
            return {}
        keys = ("transcription_quality", "transcription_provider", "diarization", "review_priority", "review_reasons")
        return {key: audio_quality.get(key) for key in keys if key in audio_quality}

    @classmethod
    def check_new_audit_quality(
        cls,
        result: Any,
        queue_input_hash: str,
        filename: str,
        effective_audit_hash: str,
        pipeline_context: AuditPipelineContext,
    ) -> Optional[Dict[str, Any]]:
        """
        Avalia se a nova auditoria gerada pela IA possui alguma flag de baixa qualidade
        na transcrição que exija revisão humana antes da aplicação da nota.
        """
        from core.automation import (
            _mark_item_status,
            _automatic_audio_transcription_review_reasons,
            _audit_on_transcription_risk_enabled,
            _discard_impossible_transcription_enabled,
        )
        from core.automation_disposition import Disposition, execute_discard
        from core.transcription_quality import transcription_is_empty

        audio_quality = getattr(result, "audio_quality", None)
        selected_strategy = _selected_transcription_strategy(audio_quality)
        if not _satisfies_transcription_policy(audio_quality):
            return cls.handle_transcription_runtime_error(
                RuntimeError(
                    "transcricao valida obrigatoria para automacao; "
                    f"estrategia selecionada foi '{selected_strategy or 'ausente'}'."
                ),
                queue_input_hash,
                filename,
                pipeline_context,
            )

        review_reasons = _automatic_audio_transcription_review_reasons(audio_quality)

        # So transcricao GENUINAMENTE VAZIA (sem texto) -> DESCARTA permanente. Qualidade ruim
        # mas com conteudo (selector rejeitado, poucas falas) segue p/ o auditor, nao some.
        if transcription_is_empty(audio_quality) and _discard_impossible_transcription_enabled():
            return execute_discard(
                None,
                Disposition.DISCARD_IMPOSSIBLE,
                motivo="transcricao_impossivel",
                status_result="discarded_impossible_transcription",
                queue_input_hash=queue_input_hash,
                filename=filename,
                sector_id=getattr(pipeline_context, "sector_id", None),
                operator_name=getattr(pipeline_context, "operator_name", None),
            )

        # Transcricao IMPERFEITA (review_required): com AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK
        # ON (default) segue auditando; OFF (rollback) -> estaciona em triagem manual.
        if review_reasons and not _audit_on_transcription_risk_enabled():
            _mark_item_status(
                queue_input_hash,
                REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
                "Transcricao requer revisao manual antes da auditoria automatica",
                motivos_revisao_append=cls._queue_motivos_for_transcription_review(review_reasons),
                metadata_merge={
                    "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                    "audit_input_hash": effective_audit_hash,
                    "audit_pipeline": pipeline_context.to_audit_metadata(),
                    "audio_quality_review": cls._audio_quality_triage_metadata(audio_quality),
                },
            )
            logger.info(
                "Automacao: '%s' voltou para triagem manual porque a transcricao requer revisao (%s).",
                filename,
                ", ".join(review_reasons),
            )
            return {"status": "blocked_transcription_quality", "reasons": review_reasons}
        return None

    @classmethod
    def handle_transcription_runtime_error(
        cls,
        exc: RuntimeError,
        queue_input_hash: str,
        filename: str,
        pipeline_context: AuditPipelineContext,
        *,
        metadata: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Recebe o erro disparado pelo AI Engine e determina a consequência na fila.

        Falha de transcricao costuma ser transitoria (instabilidade do Azure): com
        AUTOMATION_TRANSCRIPTION_FAILURE_RETRY ON (default) re-tenta ate o limite e,
        esgotado, DESCARTA (recuperavel) em vez de prender. OFF (rollback) ->
        needs_manual_triage imediato (comportamento legado).
        """
        from core.automation import _mark_item_status, _transcription_failure_retry_enabled
        from core.automation_disposition import (
            Disposition,
            execute_discard,
            transient_retry_state,
        )

        error_text = str(exc)
        normalized_error = error_text.lower()

        if "hybrid_dual" in normalized_error or "transcricao" in normalized_error or "transcription" in normalized_error:
            is_premium_failure = "hybrid_dual" in normalized_error
            motivo = "transcricao_premium_falhou" if is_premium_failure else "transcricao_automatica_falhou"

            if _transcription_failure_retry_enabled():
                should_retry, next_count = transient_retry_state(metadata)
                if should_retry:
                    # AUTO_RESOLVED (re-auditavel), nao pending: senao audit_all_pending
                    # nao re-pega o item e ele fica preso sem auditar nem descartar.
                    _mark_item_status(
                        queue_input_hash,
                        REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
                        error_text[:1000],
                        motivos_revisao_append=[motivo],
                        metadata_merge={
                            "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                            "automation_transient_retries": next_count,
                            "transcription_error": error_text[:1000],
                        },
                    )
                    logger.info(
                        "Automacao: '%s' re-tentara apos falha de transcricao (tentativa %s): %s",
                        filename, next_count, error_text,
                    )
                    return {"status": "retry_transcription_failed", "reasons": [motivo]}
                return execute_discard(
                    None,
                    Disposition.DISCARD_RECOVERABLE,
                    motivo=motivo,
                    status_result="discarded_transcription_failed",
                    queue_input_hash=queue_input_hash,
                    filename=filename,
                    sector_id=getattr(pipeline_context, "sector_id", None),
                    operator_name=getattr(pipeline_context, "operator_name", None),
                )

            # Rollback (flag OFF): comportamento legado -> triagem manual.
            _mark_item_status(
                queue_input_hash,
                REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
                (
                    "Transcricao premium falhou; auditoria automatica bloqueada"
                    if is_premium_failure
                    else "Transcricao automatica falhou; auditoria automatica bloqueada"
                ),
                motivos_revisao_append=[motivo],
                metadata_merge={
                    "automation_last_error_at": datetime.now(timezone.utc).isoformat(),
                    "audit_pipeline": pipeline_context.to_audit_metadata(),
                    "transcription_error": error_text[:1000],
                },
            )
            logger.info(
                "Automacao: '%s' voltou para triagem manual porque a transcricao falhou: %s",
                filename,
                error_text,
            )
            return {
                "status": "blocked_transcription_quality",
                "reasons": ["premium_transcription_failed" if is_premium_failure else "transcription_failed"],
            }

        raise exc  # Re-lança se não for um erro conhecido de transcrição
