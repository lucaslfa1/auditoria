"""Router da triagem/classificação de ligações (módulo de pré-auditoria).

Expõe os endpoints sob ``/api/classify`` usados pela tela de Triagem do frontend:

- ``POST /api/classify``: recebe vários áudios, classifica setor/alerta/operador
  via IA, detecta duplicatas (no batch e contra a fila/auditorias já existentes),
  guarda o áudio classificado para auditoria em lote e sincroniza a fila de
  revisão de classificação.
- ``POST /api/classify/clear-cache``: invalida os caches dos critérios.
- ``PATCH /api/classify/{input_hash}``: correção manual de setor/alerta de um
  item da fila de triagem.

CUSTO DE API: ``POST /api/classify`` aciona ``classify_multiple_audios``, que faz
chamadas pagas ao Azure (transcrição + GPT-4o de classificação) para cada arquivo
NÃO duplicado. Itens detectados como duplicata são respondidos sem reprocessar
(sem custo). Os demais endpoints (clear-cache, PATCH) só tocam cache/banco e não
têm custo de API.
"""

import hashlib
import logging
import os
import sys

from typing import Optional, Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import db.database as database
from repositories import operators
from core.automation import store_classified_audio
from core.classification import MAX_FILES_PER_REQUEST, ClassificationResult, classify_multiple_audios, load_audit_criteria_catalog, clear_classification_caches
from db.domain_constants import REVIEW_QUEUE_STATUS_AUDITED
from routers.auth import require_authenticated_user
from routers.common import ensure_supported_upload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["classifier"])


class ClassificationCorrectionPayload(BaseModel):
    """Corpo do PATCH de correção manual de classificação na triagem.

    ``sector_id`` e ``alert_id`` são obrigatórios; os demais campos (operador,
    supervisor, escala) são opcionais e usados só para enriquecer o registro.
    """

    sector_id: str
    alert_id: str
    operator_name: Optional[str] = None
    operator_id: Optional[str] = None
    supervisor: Optional[str] = None
    escala: Optional[str] = None


def _get_classify_multiple_audios_runner():
    """Resolve a função de classificação, respeitando monkeypatch em ``main``.

    Se ``main``/``backend.main`` tiver um ``classify_multiple_audios`` injetado
    (ex.: testes que monkeypatcham o módulo principal), usa esse; senão usa a
    importação direta. Permite que os testes substituam a chamada de IA.
    """
    main_module = sys.modules.get("main") or sys.modules.get("backend.main")
    if main_module is not None:
        patched_runner = getattr(main_module, "classify_multiple_audios", None)
        if patched_runner is not None:
            return patched_runner
    return classify_multiple_audios


def _duplicate_payload(reason: str) -> dict:
    """Monta o trecho de payload que marca um item como duplicata na resposta.

    ``reason`` é o motivo da duplicação (ex.: "duplicate_in_batch",
    "already_in_queue", "already_audited"). ``duplicate_label`` é o rótulo fixo
    exibido na UI.
    """
    return {
        "duplicate": True,
        "duplicate_reason": reason,
        "duplicate_label": "Ligacao repetida",
    }


def _queue_item_to_classification_payload(item: dict, *, duplicate_reason: str) -> dict:
    """Converte um item da fila de revisão de classificação no payload de resposta.

    Recebe a linha existente da ``fila_revisao_classificacao`` (``item``) e a
    formata no mesmo shape que a UI espera para um resultado de classificação,
    resolvendo os labels de setor/alerta pelo catálogo de critérios e marcando-o
    como duplicata com o ``duplicate_reason`` informado.

    Não tem efeito colateral além de ler o catálogo (cacheado).
    """
    catalog = load_audit_criteria_catalog()
    sector_id = item.get("setor_previsto") or "desconhecido"
    alert_id = item.get("alerta_previsto") or "desconhecido"
    sector = catalog.get(str(sector_id).lower())
    sector_label = str(sector["label"]) if sector else "Nao Identificado"
    alert_label = "Nao Identificado"
    if sector:
        for alert in sector.get("alerts", []):
            if alert["id"] == alert_id:
                alert_label = str(alert["label"])
                break

    needs_review = item.get("status") == "pending" or bool(item.get("motivos_revisao"))
    payload = {
        "filename": item.get("nome_arquivo", ""),
        "input_hash": item.get("input_hash"),
        "sector_id": sector_id,
        "sector_label": sector_label,
        "alert_id": alert_id,
        "alert_label": alert_label,
        "confidence": item.get("confianca") if item.get("confianca") is not None else 0.0,
        "operator_name": item.get("operador_previsto"),
        "operator_id": None,
        "operator_telefonia": None,
        "operator_rh": None,
        "id_huawei": None,
        "matricula": None,
        "error": item.get("erro"),
        "needs_review": needs_review,
        "review_reasons": item.get("motivos_revisao") or [],
        "review_priority": item.get("prioridade") or "low",
        "status": item.get("status"),
    }
    payload.update(_duplicate_payload(duplicate_reason))
    return payload


@router.post("/api/classify")
async def classify_audios(
    _user: dict = Depends(require_authenticated_user),
    files: list[UploadFile] = File(...),
    force_reclassify: bool = Form(False),
):
    """Classifica um lote de áudios na triagem (setor/alerta/operador via IA).

    Para cada arquivo: valida o formato (só áudio, ``allow_pdf=False``), calcula o
    hash SHA-256 e detecta duplicatas em três níveis — (1) repetido dentro do
    próprio batch, (2) já presente na fila de revisão de classificação, (3) já
    auditado em ``audits``. Quando ``force_reclassify=False``, itens duplicados não
    são reclassificados (economiza chamada de IA) e voltam com o payload existente.

    Os arquivos novos são classificados em lote por ``classify_multiple_audios``
    (CUSTO DE API: Azure transcrição + GPT-4o). Para cada um, persiste o áudio
    classificado em storage, sincroniza a fila de revisão e registra o resultado
    de classificação (com acerto vs. referência, quando há gabarito). Por fim
    enriquece cada resultado com dados de RH do operador (busca em colaboradores).

    Params:
        files: lista de uploads de áudio (limite ``MAX_FILES_PER_REQUEST``).
        force_reclassify: se True, reprocessa mesmo itens já vistos/auditados.

    Retorno: ``{"results": [...]}`` com um item por arquivo enviado (na ordem).
    Efeitos colaterais: leitura/escrita no banco, escrita de áudio em storage,
    chamadas pagas à IA. Erros de validação viram HTTP 400; falhas internas, 500.
    """
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400,
            detail=f"Máximo de {MAX_FILES_PER_REQUEST} arquivos por requisição.",
        )

    try:
        file_data = []
        classify_indices: list[int] = []
        file_hashes: dict[int, str] = {}
        duplicate_info: dict[int, dict] = {}
        existing_payloads: dict[int, dict] = {}
        vistos_neste_batch: set[str] = set()
        for idx, file in enumerate(files):
            ensure_supported_upload(file, allow_pdf=False)
            content = await file.read()

            # Pre-compute hash for duplicate detection
            file_hash = hashlib.sha256(content).hexdigest()
            file_hashes[idx] = file_hash

            # Detectar duplicatas dentro do mesmo batch (evita IntegrityError no INSERT)
            if file_hash in vistos_neste_batch:
                duplicate_info[idx] = _duplicate_payload("duplicate_in_batch")
                existing_payloads[idx] = {
                    "filename": file.filename, "input_hash": file_hash, "status": "duplicado",
                    "sector_id": "desconhecido", "sector_label": "Nao Identificado",
                    "alert_id": "desconhecido", "alert_label": "Nao Identificado",
                    "confidence": 0.0, "operator_name": None,
                    "operator_id": None, "operator_telefonia": None, "operator_rh": None,
                    "id_huawei": None, "matricula": None,
                    "error": None, "needs_review": False,
                    "review_reasons": [], "review_priority": "low",
                    "duplicate": True, "duplicate_reason": "duplicate_in_batch",
                    "duplicate_label": "Ligacao repetida",
                }
                continue
            vistos_neste_batch.add(file_hash)

            if not force_reclassify:
                try:
                    existing_queue = database.obter_fila_revisao_classificacao_por_hash(file_hash)
                    if existing_queue:
                        duplicate_reason = (
                            "already_audited"
                            if existing_queue.get("status") == REVIEW_QUEUE_STATUS_AUDITED
                            else "already_in_queue"
                        )
                        duplicate_info[idx] = _duplicate_payload(duplicate_reason)
                        existing_payloads[idx] = _queue_item_to_classification_payload(
                            existing_queue,
                            duplicate_reason=duplicate_reason,
                        )
                        continue

                    # Check if already audited
                    conn = database.get_connection()
                    try:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id, status FROM audits WHERE input_hash = %s LIMIT 1", (file_hash,))
                        audit_row = cursor.fetchone()
                    finally:
                        conn.close()

                    if audit_row:
                        duplicate_info[idx] = _duplicate_payload("already_audited")
                except Exception:
                    pass  # Duplicate check is best-effort

            file_data.append((file.filename or "", content))
            classify_indices.append(idx)

        fresh_results = await _get_classify_multiple_audios_runner()(file_data) if file_data else []
        indexed_results: dict[int, ClassificationResult] = {
            index: result for index, result in zip(classify_indices, fresh_results)
        }

        for index, (filename, content) in zip(classify_indices, file_data):
            result = indexed_results[index]
            try:
                arquivo_hash = hashlib.sha256(content).hexdigest()
                # Store audio for later batch auditing
                audio_path = store_classified_audio(arquivo_hash, filename, content)
                database.sincronizar_fila_revisao_classificacao(
                    input_hash=arquivo_hash,
                    nome_arquivo=filename,
                    setor_previsto=result.sector_id,
                    alerta_previsto=result.alert_id,
                    confianca=result.confidence,
                    operador_previsto=result.operator_name,
                    erro=result.error,
                    precisa_revisao=getattr(result, "needs_review", False),
                    prioridade=getattr(result, "review_priority", "low"),
                    motivos_revisao=getattr(result, "review_reasons", []),
                    metadata={
                        "filename_upload": filename,
                        "classified_audio_path": audio_path,
                        "transcription": getattr(result, "transcription", None),
                    },
                )

                ligacao_referencia = database.get_ligacao_auditada_por_hash(arquivo_hash)
                if not ligacao_referencia:
                    continue

                setor_referencia = ligacao_referencia.get("setor_referencia")
                alerta_referencia = ligacao_referencia.get("alerta_referencia")
                acertou_setor = (result.sector_id == setor_referencia) if setor_referencia else None
                acertou_alerta = (result.alert_id == alerta_referencia) if alerta_referencia else None

                database.registrar_resultado_classificacao(
                    ligacao_id=ligacao_referencia["id"],
                    setor_previsto=result.sector_id,
                    alerta_previsto=result.alert_id,
                    confianca=result.confidence,
                    operador_previsto=result.operator_name,
                    modelo=(os.getenv("AZURE_OPENAI_DEPLOYMENT") or "gpt-4o").strip(),
                    versao_prompt="classificacao_v1",
                    acertou_setor=acertou_setor,
                    acertou_alerta=acertou_alerta,
                    erro=result.error,
                    metadata={"filename_upload": filename},
                )
            except Exception as persist_error:
                logger.warning("Classification persistence warning: %s", persist_error)

        enriched_results = []
        for idx, _file in enumerate(files):
            if idx in existing_payloads:
                enriched_results.append(existing_payloads[idx])
                continue

            result = indexed_results[idx]
            item = {
                "filename": result.filename,
                "input_hash": file_hashes.get(idx),
                "sector_id": result.sector_id,
                "sector_label": result.sector_label,
                "alert_id": result.alert_id,
                "alert_label": result.alert_label,
                "confidence": result.confidence,
                "operator_name": result.operator_name,
                "operator_id": None,
                "operator_telefonia": None,
                "operator_rh": None,
                "id_huawei": result.id_huawei,
                "matricula": result.matricula,
                "error": result.error,
                "needs_review": getattr(result, "needs_review", False),
                "review_reasons": getattr(result, "review_reasons", []),
                "review_priority": getattr(result, "review_priority", "low"),
            }

            if result.operator_name:
                try:
                    rh_match = operators.buscar_colaborador_por_nome(database.get_connection, result.operator_name)
                    if rh_match:
                        item["operator_id"] = rh_match.get("preferredId", "")
                        item["operator_telefonia"] = rh_match.get("idTelefonia", "")
                        item["operator_rh"] = rh_match
                        logger.info(
                            "[classify] Operador '%s' -> RH: %s (ID: %s)",
                            result.operator_name, rh_match["name"], rh_match.get("preferredId", "N/A"),
                        )
                    else:
                        logger.info("[classify] Operador '%s' -> sem vinculo em colaboradores", result.operator_name)
                except Exception as exc:
                    logger.warning("[classify] Erro ao buscar operador: %s", exc)

            # Inject duplicate detection info
            dup = duplicate_info.get(idx, {})
            item["duplicate"] = dup.get("duplicate", False)
            item["duplicate_reason"] = dup.get("duplicate_reason", None)
            item["duplicate_label"] = dup.get("duplicate_label", None)

            enriched_results.append(item)

        return {"results": enriched_results}
    except ValueError as exc:
        logger.warning("Classification validation error: %s", exc)
        raise HTTPException(status_code=400, detail="Dados de entrada inválidos para classificação.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Classification error: %s", exc)
        raise HTTPException(status_code=500, detail="Erro interno ao classificar arquivos.")


@router.post("/api/classify/clear-cache")
async def clear_cache(user: dict = Depends(require_authenticated_user)):
    """Invalida o cache dos critérios de avaliação para forçar reload do YAML."""
    clear_classification_caches()
    logger.info("Classification criteria cache cleared by user %s", user.get("email") or user.get("username") or "unknown")
    return {"message": "Cache de critérios invalidado com sucesso."}


@router.patch("/api/classify/{input_hash}")
async def correct_classification(
    input_hash: str,
    payload: ClassificationCorrectionPayload,
    user: dict = Depends(require_authenticated_user),
):
    """Corrige manualmente o setor/alerta de um item da fila de triagem.

    Valida que ``input_hash``, ``sector_id`` e ``alert_id`` foram informados e que
    o par setor/alerta existe no catálogo de critérios (senão HTTP 400). Atualiza
    a linha na fila de revisão de classificação (HTTP 404 se não existir) marcando
    o revisor (username/sub/email do usuário autenticado). Quando há ligação de
    referência (gabarito) pelo hash, também registra o resultado de classificação
    manual (``modelo="manual_triage"``).

    Sem custo de API (correção humana, só banco). Retorna ``{"result": {...}}`` com
    o item já corrigido. Efeito colateral: escrita no banco.
    """
    sector_id = str(payload.sector_id or "").strip().lower()
    alert_id = str(payload.alert_id or "").strip()
    if not input_hash or not sector_id or not alert_id:
        raise HTTPException(status_code=400, detail="Hash, setor e alerta sao obrigatorios.")

    catalog = load_audit_criteria_catalog()
    sector = catalog.get(sector_id)
    if not sector:
        raise HTTPException(status_code=400, detail="Setor invalido para correcao manual.")

    sector_alerts = sector.alerts if hasattr(sector, "alerts") else sector.get("alerts", [])
    alert = next(
        (
            item for item in sector_alerts
            if (item.id if hasattr(item, "id") else item.get("id")) == alert_id
        ),
        None,
    )
    if not alert:
        raise HTTPException(status_code=400, detail="Alerta invalido para o setor informado.")

    sector_label = str(sector.label if hasattr(sector, "label") else sector.get("label", ""))
    alert_label = str(alert.label if hasattr(alert, "label") else alert.get("label", ""))

    reviewed_by = (
        user.get("username")
        or user.get("sub")
        or user.get("email")
        or "usuario_autenticado"
    )

    updated = database.corrigir_classificacao_fila_revisao(
        input_hash,
        setor_previsto=sector_id,
        alerta_previsto=alert_id,
        operador_previsto=payload.operator_name,
        operator_id=payload.operator_id,
        revisado_por=reviewed_by,
        supervisor=payload.supervisor,
        escala=payload.escala,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Classificacao nao encontrada na fila de triagem.")

    # Se temos transcrição e houve de fato uma correção (setor ou alerta mudaram),
    # alimentamos o aprendizado (ai_feedback) para calibrar as próximas classificações.
    metadata = updated.get("metadata") or {}
    transcription = metadata.get("transcription")
    previous_class = metadata.get("manual_review_previous") or {}
    prev_sector = previous_class.get("setor_previsto")
    prev_alert = previous_class.get("alerta_previsto")

    has_changed = (prev_sector != sector_id) or (prev_alert != alert_id)

    if transcription and has_changed:
        try:
            from core.ai_feedback import add_feedback

            prev_sector_label = prev_sector or "desconhecido"
            prev_alert_label = prev_alert or "desconhecido"

            if prev_sector:
                p_sec = catalog.get(prev_sector)
                if p_sec:
                    prev_sector_label = str(p_sec.label if hasattr(p_sec, "label") else p_sec.get("label", prev_sector))
                    if prev_alert:
                        p_alerts = p_sec.alerts if hasattr(p_sec, "alerts") else p_sec.get("alerts", [])
                        p_al = next((a for a in p_alerts if (a.id if hasattr(a, "id") else a.get("id")) == prev_alert), None)
                        if p_al:
                            prev_alert_label = str(p_al.label if hasattr(p_al, "label") else p_al.get("label", prev_alert))

            situacao = f"A IA previu incorretamente o setor '{prev_sector_label}' (id: {prev_sector}) e o alerta '{prev_alert_label}' (id: {prev_alert}) na triagem automática."
            correcao = f"O auditor corrigiu para o setor '{sector_label}' (id: {sector_id}) e o alerta '{alert_label}' (id: {alert_id})."

            add_feedback(
                tipo="classificacao",
                situacao=situacao,
                correcao=correcao,
                justificativa="Correção manual de triagem pelo auditor.",
                criado_por=reviewed_by,
                setor=sector_id,
                criterio_id=alert_id,
                exemplo_transcricao=transcription,
            )
            logger.info("AI feedback of type 'classificacao' created for input_hash %s", input_hash)
        except Exception as fb_error:
            logger.warning("Falha ao salvar feedback de calibração automática: %s", fb_error)

    ligacao_referencia = database.get_ligacao_auditada_por_hash(input_hash)
    if ligacao_referencia:
        try:
            database.registrar_resultado_classificacao(
                ligacao_id=ligacao_referencia["id"],
                setor_previsto=sector_id,
                alerta_previsto=alert_id,
                confianca=updated.get("confianca"),
                operador_previsto=updated.get("operador_previsto"),
                modelo="manual_triage",
                versao_prompt="classificacao_manual_v1",
                acertou_setor=None,
                acertou_alerta=None,
                erro=None,
                metadata={
                    "source": "triagem_ui",
                    "manual_review": True,
                    "reviewed_by": reviewed_by,
                },
            )
        except Exception as persist_error:
            logger.warning("Manual classification persistence warning: %s", persist_error)

    return {
        "result": {
            "filename": updated["nome_arquivo"],
            "input_hash": updated["input_hash"],
            "sector_id": sector_id,
            "sector_label": sector_label,
            "alert_id": alert_id,
            "alert_label": alert_label,
            "confidence": updated.get("confianca"),
            "operator_name": updated.get("operador_previsto"),
            "error": updated.get("erro"),
            "needs_review": False,
            "review_reasons": [],
            "review_priority": "low",
            "status": updated.get("status"),
        }
    }
