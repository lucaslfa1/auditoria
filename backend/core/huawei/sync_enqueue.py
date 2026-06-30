"""Enfileiramento das midias baixadas pelo sync Huawei na fila de triagem.

Persiste o audio/PDF baixado (dedupe por sha256), monta o metadata com a
verdade cadastral do operador e sincroniza o item na fila de revisao de
classificacao (respeitando tombstones). Codigo movido de core/huawei_sync.py
sem alteracao de logica; os nomes compartilhados e patchaveis resolvem em
runtime via core.huawei_sync.

DISPARO: chamado pela Fase 1 do `core.huawei_sync.executar_sync_huawei`, logo
apos baixar a midia. O item enfileirado em `fila_revisao_classificacao` e depois
classificado pela Fase 2 (`sync_classification`) e auditado pela esteira da
automacao.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def _enfileirar_audio(
    audio_bytes: bytes,
    filename: str,
    operador: dict,
    extra_metadata: Optional[dict] = None,
    is_manual: bool = False,
) -> Dict[str, Any]:
    from core import huawei_sync as hs

    operator_truth = hs._operator_truth_snapshot(operador)
    sector_id = operator_truth.get("setor_id") or operator_truth.get("setor") or "desconhecido"
    sector_label = operator_truth.get("setor") or sector_id or "Não Identificado"
    classification = hs.ClassificationResult(
        filename=filename,
        sector_id=sector_id,
        sector_label=sector_label,
        alert_id="desconhecido",
        alert_label="Aguardando classificação",
        confidence=0.0,
        operator_name=operator_truth.get("nome") or operador.get("nome"),
        error=None,
        needs_review=True,
        review_reasons=["aguardando_triagem"],
        review_priority="medium",
        id_huawei=operator_truth.get("id_huawei"),
        matricula=operator_truth.get("matricula"),
    )

    audio_metadata = dict(extra_metadata or {})
    audio_metadata.update(
        {
            "operator_name_real": operator_truth.get("nome"),
            "operator_sector_real": operator_truth.get("setor"),
            "operator_sector_id": operator_truth.get("setor_id"),
            "operator_escala": operator_truth.get("escala"),
            "operator_matricula": operator_truth.get("matricula"),
            "operator_id_huawei_real": operator_truth.get("id_huawei"),
        }
    )
    audio_metadata.setdefault("classification_status", "pending")

    return hs._enfileirar_classificado(
        audio_bytes,
        filename,
        operador,
        classification,
        source_type=hs.SOURCE_TYPE_AUDIO,
        extra_metadata=audio_metadata,
        is_manual=is_manual,
    )

async def _enfileirar_pdf(
    pdf_bytes: bytes,
    filename: str,
    operador: dict,
) -> Dict[str, Any]:
    from core import huawei_sync as hs

    classification = await hs._classificar_pdf_huawei(pdf_bytes, filename, operador)
    return hs._enfileirar_classificado(
        pdf_bytes,
        filename,
        operador,
        classification,
        source_type=hs.SOURCE_TYPE_PDF,
    )

def _enfileirar_classificado(
    media_bytes: bytes,
    filename: str,
    operador: dict,
    classification: "ClassificationResult",
    *,
    source_type: str,
    extra_metadata: Optional[dict] = None,
    is_manual: bool = False,
) -> Dict[str, Any]:
    from core import huawei_sync as hs

    input_hash = hashlib.sha256(media_bytes).hexdigest()

    existing = hs.database.obter_fila_revisao_classificacao_por_hash(input_hash)
    if existing:
        return {"status": "duplicate", "input_hash": input_hash, "filename": filename}

    media_path = hs.store_classified_audio(input_hash, filename, media_bytes)
    operator_truth = hs._operator_truth_snapshot(operador)
    detected_operator_name = (
        getattr(classification, "operator_name", None)
        or operator_truth.get("nome")
        or operador.get("nome")
    )
    detected_id_huawei = (
        getattr(classification, "id_huawei", None)
        or operator_truth.get("id_huawei")
        or operador.get("id_huawei")
    )
    detected_matricula = getattr(classification, "matricula", None) or operator_truth.get("matricula")
    detected_operator_id = detected_id_huawei or detected_matricula or operator_truth.get("id_huawei")
    metadata = {
        "filename_upload": filename,
        "classified_audio_path": media_path,
        "classified_file_path": media_path,
        "source_type": source_type,
        "origem": "huawei_sync",
        "operator_id": detected_operator_id,
        "id_huawei": detected_id_huawei,
        "matricula": detected_matricula,
        "escala": operator_truth.get("escala"),
        "operator_name": detected_operator_name,
        "operator_name_real": operator_truth.get("nome"),
        "operator_sector_real": operator_truth.get("setor"),
        "operator_sector_id": operator_truth.get("setor_id"),
        "operator_escala": operator_truth.get("escala"),
        "operator_matricula": detected_matricula,
        "operator_id_huawei_real": detected_id_huawei,
        "operator_supervisor": operator_truth.get("supervisor"),
        "is_manual": is_manual,
    }
    if extra_metadata:
        metadata.update({k: v for k, v in extra_metadata.items() if v not in (None, "")})

    # D' (guardrail D'): se a classificacao trouxe extras (sugestao IA original
    # / cadastro do operador), propaga pro metadata. Auditor ve no UI.
    classification_extras = getattr(classification, "metadata_extras", None) or {}
    if classification_extras:
        metadata.update({k: v for k, v in classification_extras.items() if v not in (None, "")})

    # Fluxo unificado (v1.3.92): manual e auto entram com o mesmo status
    # (pending/auto_resolved decidido por precisa_revisao). A distincao visual
    # fica no badge "Auto" do frontend (metadata.is_manual + metadata.origem).
    status_override = None

    review_id = hs.database.sincronizar_fila_revisao_classificacao(
        input_hash=input_hash,
        nome_arquivo=filename,
        setor_previsto=classification.sector_id,
        alerta_previsto=classification.alert_id,
        confianca=getattr(classification, "confidence", 0.0),
        operador_previsto=detected_operator_name,
        erro=getattr(classification, "error", None),
        precisa_revisao=getattr(classification, "needs_review", False),
        prioridade=getattr(classification, "review_priority", "low"),
        motivos_revisao=getattr(classification, "review_reasons", []),
        metadata=metadata,
        status_override=status_override,
    )
    if review_id is None:
        try:
            from core.media_storage import classified_media_hash, delete_media

            media_hash = classified_media_hash(input_hash) or input_hash
            delete_media(media_hash, fallback_path=media_path)
        except Exception:
            logger.warning(
                "Sync Huawei: falha ao remover midia de item com tombstone permanente (hash=%s).",
                input_hash,
                exc_info=True,
            )
        return {"status": "skipped_tombstone", "input_hash": input_hash, "filename": filename}
    return {"status": "queued", "input_hash": input_hash, "filename": filename}
