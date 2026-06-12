"""Classificacao automatica (Fase 2) dos itens baixados pelo sync Huawei.

Transcreve/classifica audio e PDF via pipeline do Triagem (Whisper/Azure + GPT
com guardrails), persiste o resultado na fila de revisao e controla o
metadata.classification_status de cada item. Codigo movido de
core/huawei_sync.py sem alteracao de logica; os nomes compartilhados e
patchaveis resolvem em runtime via core.huawei_sync.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


async def _classificar_audio_huawei(
    audio_bytes: bytes,
    filename: str,
    operador: dict,
    native_call_reason: Optional[str] = None,
    native_call_reason_code: Optional[str] = None,
) -> "ClassificationResult":
    """Classificacao real (Whisper + GPT) reutilizando o pipeline do Triagem standalone.

    Espelha _classificar_pdf_huawei mas para audio: transcreve via Azure Speech,
    chama classify_with_gpt e aplica os mesmos guardrails do classify_audio.
    """
    from core import huawei_sync as hs

    mime_type = hs.get_mime_type(filename)
    try:
        transcription = await hs.transcribe_for_classification(audio_bytes, mime_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao transcrever audio Huawei %s", filename)
        return hs.finalize_classification_result(
            hs.ClassificationResult(
                filename=filename,
                sector_id=operador.get("setor") or "desconhecido",
                sector_label=operador.get("setor") or "Não Identificado",
                alert_id="erro",
                alert_label=f"Falha na transcricao ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )

    if not transcription or len(transcription.strip()) < 10:
        return hs.finalize_classification_result(
            hs.ClassificationResult(
                filename=filename,
                sector_id=operador.get("setor") or "desconhecido",
                sector_label=operador.get("setor") or "Não Identificado",
                alert_id="desconhecido",
                alert_label="Áudio curto/sem fala",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error="Short transcription",
            )
        )

    operator_name = str(operador.get("nome") or "").strip()
    operator_sector = str(operador.get("setor") or "").strip().lower()
    canonical_sector = hs._operator_sector_id(operador) or operator_sector
    classification_input = transcription
    native_reason = str(native_call_reason or "").strip()
    native_reason_code = str(native_call_reason_code or "").strip()
    if native_reason and canonical_sector and canonical_sector not in hs._AUDIO_DIRECTION_GATE_SECTORS:
        reason_code_line = f"\nCODIGO/MOTIVO TECNICO HUAWEI: {native_reason_code}" if native_reason_code else ""
        classification_input = (
            "TABULACAO NATIVA HUAWEI (motivo selecionado pelo operador no wrap-up): "
            f"{native_reason}{reason_code_line}\n\n"
            "Use essa tabulacao como sinal forte para setores fora de risco, mas valide "
            "contra a transcricao e o catalogo oficial.\n\n"
            f"TRANSCRICAO:\n{transcription}"
        )
    try:
        classification = await hs.classify_with_gpt(classification_input, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao classificar audio Huawei %s", filename)
        return hs.finalize_classification_result(
            hs.ClassificationResult(
                filename=filename,
                sector_id=operator_sector or "desconhecido",
                sector_label=operator_sector or "Não Identificado",
                alert_id="erro",
                alert_label=f"Falha na IA ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operator_name or None,
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )

    classification["_filename"] = filename
    classification = hs.align_classification_with_catalog(classification)
    classification.pop("_filename", None)
    classification = hs.enforce_temperature_guardrail(classification, transcription, filename)
    classification = hs.enforce_alert_hierarchy_guardrail(classification, transcription, filename)
    classification = hs.enforce_parada_desvio_guardrail(classification, transcription, filename)
    classification = hs.enforce_context_not_non_auditable_guardrail(classification, transcription, filename)

    from core.classification import parse_filename, resolve_operator_identity
    parsed = parse_filename(filename)
    resolved_operator = await asyncio.to_thread(
        resolve_operator_identity,
        classification.get("operator_name"),
        parsed.operator_name,
        operador.get("id_huawei") or parsed.id_huawei,
        operador.get("matricula"),
    )
    final_operator = resolved_operator.operator_name or operator_name or None
    final_id_huawei = resolved_operator.id_huawei or operador.get("id_huawei")
    final_matricula = resolved_operator.matricula or operador.get("matricula")
    # Resolver setor canonico (ex: "BASE PR - AZUL" -> "bas") antes do guardrail.
    # Sem isso, _resolve_db_sector_alias devolve None e a guarda nao consegue
    # corrigir alertas de outro setor (ex: LOGISTICA-PARADA em operador BAS).
    final_sector = canonical_sector or operator_sector or resolved_operator.db_sector or ""

    if final_sector:
        classification = hs.enforce_operator_and_direction_guardrails(
            classification,
            final_operator,
            db_sector=final_sector,
            parsed_filename=parsed,
        )
        catalog = hs.load_audit_criteria_catalog()
        current_sector = classification.get("sector_id")
        if current_sector in {"desconhecido", "erro", "", None} and final_sector in catalog:
            classification["sector_id"] = final_sector
            classification["sector_label"] = str(catalog[final_sector]["label"])

    try:
        confidence = float(classification.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    review_reasons = list(classification.get("review_reasons") or [])
    classifier_requested_review = bool(classification.get("needs_review"))
    if classifier_requested_review and not review_reasons:
        review_reasons.append("classificacao_requer_revisao")
    high_confidence_threshold = hs._get_huawei_auto_audit_confidence_threshold()
    needs_review = classifier_requested_review or confidence < high_confidence_threshold
    if confidence < high_confidence_threshold:
        review_reasons.append(hs._AUTOMATION_CONFIDENCE_REVIEW_REASON)

    # D' (guardrail D'): coleta os flags _ai_original_* / _operator_cadastro_sector
    # adicionados pelo enforce_operator_and_direction_guardrails para propagar
    # ao metadata da fila — pra que auditor veja sugestao IA original / cadastro.
    metadata_extras: dict = {}
    for key in (
        "_ai_original_sector_id",
        "_ai_original_alert_id",
        "_ai_original_alert_label",
        "_operator_cadastro_sector",
    ):
        value = classification.get(key)
        if value not in (None, ""):
            # Strip do underline para a key visivel no metadata
            metadata_extras[key.lstrip("_")] = value

    return hs.finalize_classification_result(
        hs.ClassificationResult(
            filename=filename,
            sector_id=classification.get("sector_id", "desconhecido"),
            sector_label=classification.get("sector_label", "Não Identificado"),
            alert_id=classification.get("alert_id", "desconhecido"),
            alert_label=classification.get("alert_label", "Não Identificado"),
            confidence=confidence,
            operator_name=classification.get("operator_name") or final_operator,
            direction=classification.get("direction"),
            id_huawei=final_id_huawei,
            matricula=final_matricula,
            direction_mismatch=classification.get("_direction_mismatch", False),
            needs_review=needs_review,

            review_reasons=review_reasons,
            review_priority=classification.get("review_priority", "low"),
            metadata_extras=metadata_extras,
        )
    )

async def _classificar_pdf_huawei(
    pdf_bytes: bytes,
    filename: str,
    operador: dict,
) -> "ClassificationResult":
    from core import huawei_sync as hs

    raw_text = hs.extract_text_from_pdf(pdf_bytes).strip()
    if len(raw_text) < 10:
        return hs.finalize_classification_result(
            hs.ClassificationResult(
                filename=filename,
                sector_id="desconhecido",
                sector_label="Não Identificado",
                alert_id="desconhecido",
                alert_label="PDF sem texto suficiente",
                confidence=0.0,
                operator_name=operador.get("nome"),
                id_huawei=operador.get("id_huawei"),
                error="Short PDF text",
            )
        )

    operator_name = str(operador.get("nome") or "").strip()
    operator_sector = str(operador.get("setor") or "").strip().lower()
    context = (
        f"OPERADOR CADASTRADO: {operator_name or 'N/A'}\n"
        f"SETOR CADASTRADO: {operator_sector or 'N/A'}\n\n"
        f"{raw_text}"
    )
    try:
        classification = await hs.classify_with_gpt(context, filename)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha ao classificar PDF Huawei %s", filename)
        return hs.finalize_classification_result(
            hs.ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label=f"Falha na IA ({type(exc).__name__})",
                confidence=0.0,
                operator_name=operator_name or None,
                id_huawei=operador.get("id_huawei"),
                error=str(exc),
            )
        )
    classification["_filename"] = filename
    classification = hs.align_classification_with_catalog(classification)
    classification.pop("_filename", None)

    if operator_sector:
        classification = hs.enforce_operator_and_direction_guardrails(
            classification,
            operator_name or None,
            db_sector=operator_sector,
        )
        catalog = hs.load_audit_criteria_catalog()
        current_sector = classification.get("sector_id")
        if current_sector in {"desconhecido", "erro", "", None} and operator_sector in catalog:
            classification["sector_id"] = operator_sector
            classification["sector_label"] = str(catalog[operator_sector]["label"])

    try:
        confidence = float(classification.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    return hs.finalize_classification_result(
        hs.ClassificationResult(
            filename=filename,
            sector_id=classification.get("sector_id", "desconhecido"),
            sector_label=classification.get("sector_label", "Não Identificado"),
            alert_id=classification.get("alert_id", "desconhecido"),
            alert_label=classification.get("alert_label", "Não Identificado"),
            confidence=confidence,
            operator_name=classification.get("operator_name") or operator_name or None,
            direction=classification.get("direction"),
            id_huawei=operador.get("id_huawei"),
            direction_mismatch=classification.get("_direction_mismatch", False),
        )
    )

async def _classificar_pendentes_async(
    *,
    concurrency: int,
    operator_by_id: Dict[str, dict],
    operator_by_name: Dict[str, dict],
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Dict[str, Any]:
    """Fase 2 do sync: classifica em paralelo todos os itens Huawei com
    metadata.classification_status='pending'. Atualiza setor/alerta/operador
    via corrigir_classificacao_fila_revisao (que ja dispara o RAG/RLHF) e
    marca classification_status='done' ou 'error' no metadata.
    """
    from core import huawei_sync as hs

    try:
        fila = hs.database.listar_fila_revisao_classificacao(
            limit=500,
            status="all",
            origem="huawei_sync",
        )
    except Exception:
        logger.exception("Fase 2 (classificacao): falha ao listar fila de revisao")
        return {"classificadas": 0, "erros": 0, "pendentes_restantes": 0}

    pendentes: List[dict] = []
    for item in fila or []:
        meta = item.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if str(meta.get("classification_status") or "").strip().lower() != "pending":
            continue
        pendentes.append(item)

    if not pendentes:
        return {
            "classificadas": 0,
            "erros": 0,
            "bloqueadas_pre_classificacao": 0,
            "pendentes_restantes": 0,
        }

    logger.info("Fase 2 sync Huawei: %d itens para classificar (concurrency=%d).", len(pendentes), concurrency)
    hs._notify_progress(progress_callback, "classifying", 0, len(pendentes))

    semaphore = asyncio.Semaphore(max(1, concurrency))
    classificadas = 0
    erros = 0
    bloqueadas_pre_classificacao = 0
    concluidos_total = 0

    async def _processar(item: dict) -> str:
        nonlocal classificadas, erros, bloqueadas_pre_classificacao, concluidos_total
        async with semaphore:
            try:
                if hs._cancel_requested(should_cancel):
                    return "cancelled"
                # Guardrail de orcamento: a classificacao via GPT e paga. Com o
                # teto diario atingido, o item fica como esta (pendente) e sera
                # classificado num ciclo futuro — nada e descartado nem marcado
                # como erro.
                if hs.cost_guard.budget_exceeded():
                    return "budget_exceeded"
                input_hash = str(item.get("input_hash") or "").strip()
                metadata = item.get("metadata") or {}
                if not isinstance(metadata, dict):
                    metadata = {}
                media_path = str(metadata.get("classified_audio_path") or metadata.get("classified_file_path") or "").strip()
                filename = str(item.get("nome_arquivo") or "gravacao.wav")
                if not input_hash or not media_path:
                    erros += 1
                    return "missing_path"

                # Gate nativo PRE-classificacao: nao gasta GPT com item que o
                # AutomationGatekeeper bloquearia depois pelas MESMAS regras
                # (setor fora da telefonia; receptiva/direcao desconhecida em
                # setor de risco). Disposicao identica a da automacao
                # (process_ready_item): flag default-ON descarta tombstone;
                # flag OFF manda para triagem manual.
                block = hs.AutomationGatekeeper.check_eligibility(item)
                if block:
                    block_reason, block_sector = block
                    try:
                        if hs._env_flag("AUTOMATION_DISCARD_NON_TELEPHONY", True):
                            hs.execute_discard(
                                item,
                                hs.Disposition.DISCARD_IMPOSSIBLE,
                                motivo=block_reason,
                                status_result="discarded_non_telephony",
                                queue_input_hash=input_hash,
                                filename=filename,
                                sector_id=block_sector,
                                metadata=metadata,
                            )
                        else:
                            motivo_revisao = (
                                "setor_nao_telefonia_automacao"
                                if block_reason == "setor_nao_telefonia"
                                else "direcao_invalida_automacao"
                            )
                            hs.database.atualizar_status_fila_revisao_classificacao(
                                input_hash,
                                status=hs.REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
                                erro=f"Bloqueado pre-classificacao: {block_reason}",
                                motivos_revisao_append=[motivo_revisao],
                                metadata_merge={
                                    "pre_classification_block_reason": block_reason,
                                    "pre_classification_block_sector": block_sector,
                                    "classification_status": "skipped_ineligible",
                                },
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.exception(
                            "Fase 2: falha ao aplicar bloqueio pre-classificacao de %s", filename
                        )
                        hs._marcar_classificacao_status(
                            input_hash, status="error",
                            erro=f"bloqueio_pre_classificacao_falhou: {exc}",
                        )
                        erros += 1
                        return "block_error"
                    bloqueadas_pre_classificacao += 1
                    logger.info(
                        "Fase 2: '%s' bloqueado pre-classificacao (motivo=%s, setor=%s) sem gastar GPT.",
                        filename, block_reason, block_sector,
                    )
                    return "blocked_pre_classification"
                try:
                    audio_bytes = hs.load_classified_audio(media_path, input_hash=input_hash)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Fase 2: falha ao ler audio %s (%s)", media_path, exc)
                    hs._marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                    erros += 1
                    return "io_error"
                if not audio_bytes:
                    hs._marcar_classificacao_status(input_hash, status="error", erro="audio_indisponivel")
                    erros += 1
                    return "no_bytes"

                operator_id = str(metadata.get("operator_id") or metadata.get("id_huawei") or "").strip()
                operator_name = str(metadata.get("operator_name") or item.get("operador_previsto") or "").strip()
                operador = (
                    (operator_by_id.get(operator_id) or operator_by_id.get(operator_id.lower()))
                    if operator_id else None
                ) or (
                    operator_by_name.get(hs._normalize_identity_text(operator_name))
                    if operator_name else None
                ) or {
                    "nome": operator_name,
                    "id_huawei": operator_id,
                    "setor": metadata.get("operator_sector_real") or item.get("setor_previsto") or "",
                    "escala": metadata.get("operator_escala") or metadata.get("escala") or "",
                    "matricula": metadata.get("operator_matricula") or metadata.get("matricula") or "",
                }
                operator_truth = hs._operator_truth_snapshot(operador)

                try:
                    result = await hs._classificar_audio_huawei(
                        audio_bytes,
                        filename,
                        operador,
                        native_call_reason=str(metadata.get("huawei_call_reason") or "").strip() or None,
                        native_call_reason_code=str(metadata.get("huawei_call_reason_code") or "").strip() or None,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Fase 2: erro ao classificar %s", filename)
                    hs._marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                    erros += 1
                    return "classify_error"

                sector_id = (
                    metadata.get("operator_sector_id")
                    or operator_truth.get("setor_id")
                    or getattr(result, "sector_id", None)
                    or "desconhecido"
                )
                alert_id = getattr(result, "alert_id", None) or "desconhecido"
                confidence = getattr(result, "confidence", 0.0) or 0.0
                try:
                    hs._aplicar_auto_classificacao(
                        input_hash,
                        sector_id=sector_id,
                        alert_id=alert_id,
                        operator_name=operator_truth.get("nome") or getattr(result, "operator_name", None) or operator_name or None,
                        confianca=confidence,
                        needs_review=bool(getattr(result, "needs_review", False)),
                        review_reasons=list(getattr(result, "review_reasons", []) or []),
                        review_priority=str(getattr(result, "review_priority", "low") or "low"),
                        erro=getattr(result, "error", None),
                        id_huawei=getattr(result, "id_huawei", None) or operator_truth.get("id_huawei"),
                        matricula=getattr(result, "matricula", None) or operator_truth.get("matricula"),
                    )
                    classificadas += 1
                    return "ok"
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Fase 2: falha ao persistir classificacao de %s", filename)
                    hs._marcar_classificacao_status(input_hash, status="error", erro=str(exc))
                    erros += 1
                    return "persist_error"
            finally:
                concluidos_total += 1
                hs._notify_progress(progress_callback, "classifying", concluidos_total, len(pendentes))

    await asyncio.gather(*[_processar(item) for item in pendentes])

    pendentes_restantes = max(
        0, len(pendentes) - classificadas - erros - bloqueadas_pre_classificacao
    )
    return {
        "classificadas": classificadas,
        "erros": erros,
        "bloqueadas_pre_classificacao": bloqueadas_pre_classificacao,
        "pendentes_restantes": pendentes_restantes,
    }

def _marcar_classificacao_status(
    input_hash: str,
    *,
    status: str,
    erro: Optional[str] = None,
) -> None:
    """Atualiza apenas metadata.classification_status mantendo status da fila."""
    from core import huawei_sync as hs

    metadata_merge: Dict[str, Any] = {"classification_status": status}
    if status == "error" and erro:
        metadata_merge["classification_error"] = erro[:500]
    if status == "done":
        metadata_merge["classification_error"] = None
    try:
        from db.database import get_connection

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT metadata_json FROM fila_revisao_classificacao WHERE input_hash = %s",
                (input_hash,),
            )
            row = cursor.fetchone()
            if not row:
                return
            meta_atual = hs.json_loads(row["metadata_json"], {})
            if not isinstance(meta_atual, dict):
                meta_atual = {}
            meta_atual.update(metadata_merge)
            cursor.execute(
                "UPDATE fila_revisao_classificacao SET metadata_json = %s, atualizado_em = %s WHERE input_hash = %s",
                (
                    json.dumps(meta_atual, ensure_ascii=False),
                    datetime.now().isoformat(),
                    input_hash,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao registrar classification_status=%s para %s", status, input_hash)

def _automation_skip_pending_on_low_confidence_enabled() -> bool:
    """Default ON: automação não rebaixa para 'pending' por baixa confiança.

    O item vai para auto_resolved (READY) e a esteira (_audit_single_item) decide:
    alerta conhecido audita, desconhecido descarta. OFF restaura o pending legado.
    """
    raw = os.getenv("AUTOMATION_SKIP_PENDING_ON_LOW_CONFIDENCE")
    if raw is None:
        return True
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_auto_classificacao_status(*, needs_review: bool, status_atual: str) -> str:
    """Decide o status final de um item de classificação AUTOMÁTICA.

    Status já tocado por humano/auditoria (qualquer coisa fora de
    {auto_resolved, pending}) é preservado.
    """
    status_atual = (status_atual or "").strip().lower()
    if needs_review and not _automation_skip_pending_on_low_confidence_enabled():
        return "pending"
    if status_atual in {"auto_resolved", "pending"}:
        return "auto_resolved"
    return status_atual or "auto_resolved"


def _aplicar_auto_classificacao(
    input_hash: str,
    *,
    sector_id: str,
    alert_id: str,
    operator_name: Optional[str],
    confianca: float,
    needs_review: bool,
    review_reasons: List[str],
    review_priority: str,
    erro: Optional[str],
    id_huawei: Optional[str] = None,
    matricula: Optional[str] = None,
) -> None:
    """Persiste o resultado de uma classificacao automatica (Whisper+GPT) sem
    promover o status para 'reviewed' (que e reservado para correcao humana).

    Mantem o status atual (auto_resolved / pending) salvo se a classificacao
    real exigir revisao manual e o item estava em auto_resolved — nesse caso
    rebaixa para pending para o auditor decidir.
    """
    from core import huawei_sync as hs
    from db.database import get_connection

    sector_norm = (sector_id or "").strip().lower() or "desconhecido"
    motivos = [str(m).strip() for m in (review_reasons or []) if str(m).strip()]
    prioridade = (review_priority or "low").strip().lower() or "low"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, motivos_json, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return

        meta_atual = hs.json_loads(row["metadata_json"], {})
        if not isinstance(meta_atual, dict):
            meta_atual = {}
        meta_atual["classification_status"] = "done"
        meta_atual["classification_error"] = None
        meta_atual["classified_by"] = "huawei_auto_classifier"
        if id_huawei:
            meta_atual["id_huawei"] = id_huawei
        if matricula:
            meta_atual["matricula"] = matricula

        try:
            motivos_existentes = json.loads(row["motivos_json"]) if row["motivos_json"] else []
            if not isinstance(motivos_existentes, list):
                motivos_existentes = []
        except Exception:  # noqa: BLE001
            motivos_existentes = []
        motivos_atualizados = list(dict.fromkeys([*motivos_existentes, *motivos]))

        status_atual = (row["status"] or "").strip().lower()
        # Automação não prende em pending por baixa confiança (flag default ON):
        # vai para auto_resolved (READY) e a esteira decide (conhecido audita,
        # desconhecido descarta). Ver _resolve_auto_classificacao_status.
        novo_status = hs._resolve_auto_classificacao_status(
            needs_review=needs_review, status_atual=status_atual
        )

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET setor_previsto = %s,
                alerta_previsto = %s,
                operador_previsto = COALESCE(NULLIF(%s, ''), operador_previsto),
                confianca = %s,
                erro = %s,
                prioridade = %s,
                motivos_json = %s,
                metadata_json = %s,
                status = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                sector_norm,
                alert_id or "desconhecido",
                str(operator_name or "").strip(),
                float(confianca or 0.0),
                erro,
                prioridade,
                json.dumps(motivos_atualizados, ensure_ascii=False),
                json.dumps(meta_atual, ensure_ascii=False),
                novo_status,
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()
    finally:
        conn.close()
