"""Normalização, validação e scoring do payload de avaliação devolvido pela IA.

Pós-processamento puro (sem rede/banco) do JSON cru do modelo: traduz para o
contrato canônico tolerando variações de chave, valida o contrato mínimo,
confronta evidências com a transcrição e mede a cobertura de evidência (gate
do retry). Extraído de `core.audit_evaluator`, que reexporta
`_is_valid_evaluation_payload`, `_normalize_validate_and_score_evaluation` e
`_evidence_coverage_is_acceptable` p/ compat (usados pelas funções `evaluate_*`
e por `test_qualification_audit`).
"""
import logging
import os
import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.evidence_validation import (
    summarize_evidence_coverage,
    validate_evidence_against_transcription,
)
from schemas import AuditAlert, AuditCriterion

logger = logging.getLogger(__name__)


def _normalize_evaluation_lookup_text(value: Any) -> str:
    """Normaliza texto para lookup: minúsculas, sem acentos, espaços colapsados."""
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return " ".join(normalized.split())


def _build_criterion_label_lookup(criteria_list: list[AuditCriterion]) -> dict[str, str]:
    """Mapa label-normalizado → criterionId (fallback quando a IA devolve o label no lugar do ID)."""
    lookup: dict[str, str] = {}
    for criterion in criteria_list:
        normalized_label = _normalize_evaluation_lookup_text(criterion.label)
        if normalized_label:
            lookup[normalized_label] = criterion.id
    return lookup


def _iter_raw_evaluation_details(raw_details: Any) -> list[dict[str, Any]]:
    """Extrai os details aceitando lista de dicts OU dict {criterionId: detail}.

    No formato dict, a chave do mapa vira `criterionId` quando o item não o
    traz. Qualquer outro formato retorna lista vazia (payload será reprovado
    adiante pelo gate de validade).
    """
    if isinstance(raw_details, list):
        return [item for item in raw_details if isinstance(item, dict)]

    if isinstance(raw_details, dict):
        normalized_items: list[dict[str, Any]] = []
        for key, value in raw_details.items():
            if not isinstance(value, dict):
                continue
            candidate = dict(value)
            candidate.setdefault("criterionId", key)
            normalized_items.append(candidate)
        return normalized_items

    return []


class _NormalizedEvaluationDetail(BaseModel):
    """Forma canônica de um detail (1 critério avaliado) após o saneamento.

    `evidence_validation` é preenchido depois, por
    `validate_evidence_against_transcription` (diagnóstico da evidência).
    """

    model_config = ConfigDict(extra="ignore")

    criterionId: str = Field(min_length=1)
    status: Literal["pass", "fail"]
    comment: str = ""
    timestamp: str = ""
    evidence_text: str = ""
    evidence_validation: Optional[dict[str, Any]] = None


class _NormalizedEvaluationPayload(BaseModel):
    """Payload completo de avaliação saneado (contrato interno pós-normalização)."""

    model_config = ConfigDict(extra="ignore")

    summary: str = ""
    ai_feedback: Optional[str] = None
    details: list[_NormalizedEvaluationDetail] = Field(default_factory=list)
    fatal_flags: list[str] = Field(default_factory=list)


def _coerce_normalized_evaluation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validação Pydantic final: details inválidos são descartados UM A UM.

    A falha de um item não derruba o payload inteiro; o gate de completude
    fica a cargo de `_is_valid_evaluation_payload` e do `evidence_quality`
    (critérios ausentes forçam revisão/retry).
    """
    valid_details: list[dict[str, Any]] = []
    for item in payload.get("details", []):
        try:
            valid_details.append(_NormalizedEvaluationDetail.model_validate(item).model_dump(exclude_none=True))
        except ValidationError:
            continue

    normalized = {
        **payload,
        "details": valid_details,
        "fatal_flags": [
            str(flag).strip()
            for flag in (payload.get("fatal_flags") if isinstance(payload.get("fatal_flags"), list) else [])
            if str(flag).strip()
        ],
    }
    return _NormalizedEvaluationPayload.model_validate(normalized).model_dump(exclude_none=True)


def _normalize_evaluation_payload(raw_payload: Any, criteria_list: list[AuditCriterion]) -> dict[str, Any]:
    """Traduz o JSON cru da IA para o contrato canônico, tolerando variações.

    Tolerâncias acumuladas de produção (o modelo nem sempre respeita o schema,
    especialmente no caminho sem response_format estrito):
    - chaves alternativas PT/EN para details/summary/feedback/fatal_flags
      (ex.: `criterios`, `resumo`, `flags_fatais`, `justificativa`);
    - criterionId resolvido pelo ID ou, em último caso, pelo label
      normalizado; item com critério fora do catálogo é DESCARTADO;
    - status reduzido ao par pass/fail (mapeamento comentado no corpo).
    """
    if not isinstance(raw_payload, dict):
        return {"summary": "", "ai_feedback": None, "details": [], "fatal_flags": []}

    valid_ids = {criterion.id for criterion in criteria_list}
    label_lookup = _build_criterion_label_lookup(criteria_list)

    details_source = raw_payload.get("details")
    if details_source is None:
        for alternative_key in ("criteria", "criterios", "checklist", "items", "itens"):
            if alternative_key in raw_payload:
                details_source = raw_payload.get(alternative_key)
                break

    normalized_details: list[dict[str, str]] = []
    for item in _iter_raw_evaluation_details(details_source):
        criterion_id = str(
            item.get("criterionId")
            or item.get("criterion_id")
            or item.get("criterio_id")
            or item.get("id")
            or ""
        ).strip()

        if criterion_id not in valid_ids:
            raw_label = str(
                item.get("label")
                or item.get("criterion")
                or item.get("criterio")
                or item.get("name")
                or item.get("titulo")
                or ""
            ).strip()
            criterion_id = label_lookup.get(_normalize_evaluation_lookup_text(raw_label), "")

        if criterion_id not in valid_ids:
            continue

        status = str(
            item.get("status")
            or item.get("resultado")
            or item.get("result")
            or item.get("avaliacao")
            or item.get("outcome")
            or ""
        ).strip().lower()

        # 'na'/'pending_manual' viram pass (critério inaplicável não pune o
        # operador); 'partial' e valores desconhecidos punem como fail.
        if status in {"na", "pending_manual"}:
            status = "pass"
        elif status == "partial":
            status = "fail"
        elif status not in {"pass", "fail"}:
            status = "fail"
        comment = str(
            item.get("comment")
            or item.get("comentario")
            or item.get("justificativa")
            or item.get("observacao")
            or item.get("observation")
            or item.get("reason")
            or ""
        ).strip()

        timestamp = str(
            item.get("timestamp")
            or item.get("trecho")
            or item.get("momento")
            or item.get("time_range")
            or item.get("intervalo")
            or ""
        ).strip()

        evidence_text = str(
            item.get("evidence_text")
            or item.get("trecho_transcricao")
            or item.get("citacao")
            or item.get("quote")
            or ""
        ).strip()

        detail_entry = {
            "criterionId": criterion_id,
            "status": status,
            "comment": comment,
        }
        if timestamp:
            detail_entry["timestamp"] = timestamp
        if evidence_text:
            detail_entry["evidence_text"] = evidence_text
        evidence_validation = item.get("evidence_validation")
        if isinstance(evidence_validation, dict):
            detail_entry["evidence_validation"] = evidence_validation

        normalized_details.append(detail_entry)

    fatal_flags = raw_payload.get("fatal_flags")
    if fatal_flags is None:
        fatal_flags = raw_payload.get("flags_fatais", [])

    if not isinstance(fatal_flags, list):
        fatal_flags = []

    return _coerce_normalized_evaluation_payload({
        "summary": str(
            raw_payload.get("summary")
            or raw_payload.get("resumo")
            or raw_payload.get("analysis_summary")
            or raw_payload.get("analise_geral")
            or ""
        ).strip(),
        "ai_feedback": str(
            raw_payload.get("ai_feedback")
            or raw_payload.get("feedback")
            or raw_payload.get("feedback_operador")
            or ""
        ).strip() or None,
        "details": normalized_details,
        "fatal_flags": [str(flag).strip() for flag in fatal_flags if str(flag).strip()],
    })


def _is_valid_evaluation_payload(payload: Any, criteria_list: list[AuditCriterion]) -> bool:
    """Contrato mínimo para aceitar a avaliação (reprovar => retry ou erro).

    Exige: summary não vazio; `details` em lista (não vazia quando há
    critérios); e, por item, criterionId pertencente ao catálogo + status
    pass/fail + presença do campo comment.
    """
    if not isinstance(payload, dict):
        return False

    summary = str(payload.get("summary", "") or "").strip()
    if not summary:
        return False

    details = payload.get("details")
    if not isinstance(details, list):
        return False
    if criteria_list and len(details) == 0:
        return False

    allowed = {"pass", "fail"}
    valid_ids = {criterion.id for criterion in criteria_list}
    for item in details:
        if not isinstance(item, dict):
            return False
        criterion_id = str(item.get("criterionId", "") or "").strip()
        status = str(item.get("status", "") or "").strip()
        if not criterion_id or criterion_id not in valid_ids:
            return False
        if status not in allowed:
            return False
        if "comment" not in item:
            return False

    return True


def _normalize_validate_and_score_evaluation(
    raw_payload: Any,
    criteria_list: list[AuditCriterion],
    transcription: list[dict],
    *,
    alert: Optional[AuditAlert] = None,
    audio_quality: Optional[dict[str, Any]] = None,
    sector_id: Optional[str] = None,
) -> dict[str, Any]:
    """Pós-processamento completo do payload: normaliza, valida evidência, mede cobertura.

    Etapas: (1) normalização tolerante; (2) confronto literal das evidências
    com a transcrição (`evidence_validation` por item); (3) override do
    critério de qualificação Huawei (fail-open: indisponível => só warning);
    (4) agregado `evidence_quality` — critérios oficiais AUSENTES na resposta
    contam como evidência faltante e forçam `review_recommended`.

    Retorna o payload enriquecido com `evidence_quality`, insumo do gate de
    retry e da revisão humana. Processamento local (sem rede/banco).
    """
    normalized_payload = _normalize_evaluation_payload(raw_payload, criteria_list)
    normalized_payload = validate_evidence_against_transcription(normalized_payload, transcription)
    try:
        from core.qualification_audit import apply_qualification_result_override

        normalized_payload = apply_qualification_result_override(
            normalized_payload,
            criteria_list,
            alert=alert,
            audio_quality=audio_quality,
            sector_id=sector_id,
        )
    except Exception as exc:
        logger.warning("Qualification criterion override unavailable: %s", exc)
    evidence_quality = summarize_evidence_coverage(normalized_payload)
    expected_ids = {
        str(criterion.id or "").strip()
        for criterion in criteria_list
        if str(criterion.id or "").strip()
    }
    present_ids = {
        str(item.get("criterionId") or "").strip()
        for item in normalized_payload.get("details", [])
        if isinstance(item, dict) and str(item.get("criterionId") or "").strip()
    }
    missing_ids = sorted(expected_ids - present_ids)
    # Critério oficial ausente na resposta = a IA "pulou" parte do checklist:
    # rebaixa a qualidade da evidência e recomenda revisão (alimenta o retry).
    if missing_ids:
        evidence_quality = dict(evidence_quality)
        evaluable = int(evidence_quality.get("evaluable_details") or 0) + len(missing_ids)
        matched = int(evidence_quality.get("matched_evidence") or 0)
        evidence_quality["expected_details"] = len(expected_ids)
        evidence_quality["missing_criteria_count"] = len(missing_ids)
        evidence_quality["missing_criteria_ids"] = missing_ids[:20]
        evidence_quality["evaluable_details"] = evaluable
        evidence_quality["missing_evidence"] = int(evidence_quality.get("missing_evidence") or 0) + len(missing_ids)
        evidence_quality["matched_ratio"] = round((matched / evaluable) if evaluable else 1.0, 3)
        evidence_quality["review_recommended"] = True
        evidence_quality["reason"] = "criterios_ausentes_na_resposta"
        evidence_quality["quality"] = "muito_baixa" if len(missing_ids) >= 2 else "baixa"
    else:
        evidence_quality = dict(evidence_quality)
        evidence_quality["expected_details"] = len(expected_ids)
        evidence_quality["missing_criteria_count"] = 0
        evidence_quality["missing_criteria_ids"] = []
    normalized_payload["evidence_quality"] = evidence_quality
    return normalized_payload


# ── Cobertura de evidência: gate que decide o retry ─────────────────────────

def _evidence_coverage_is_acceptable(payload: dict[str, Any]) -> bool:
    """Decide se a cobertura de evidência dispensa a 2ª chamada (caminho Azure).

    Reprova quando: falta critério oficial na resposta; TODOS os details
    avaliáveis vieram sem evidência; ou a razão de evidências casadas fica
    abaixo de `AUDIT_MIN_MATCHED_EVIDENCE_RATIO`. Sem details avaliáveis,
    aprova (não há o que comprovar).
    """
    evidence_quality = payload.get("evidence_quality")
    if not isinstance(evidence_quality, dict):
        evidence_quality = summarize_evidence_coverage(payload)
    if int(evidence_quality.get("missing_criteria_count") or 0) > 0:
        return False
    evaluable = int(evidence_quality.get("evaluable_details") or 0)
    if evaluable == 0:
        return True
    if int(evidence_quality.get("missing_evidence") or 0) == evaluable:
        return False
    matched_ratio = float(evidence_quality.get("matched_ratio") or 0.0)
    return matched_ratio >= _get_min_matched_evidence_ratio()


def _get_min_matched_evidence_ratio() -> float:
    """Razão mínima de evidências casadas com a transcrição — `AUDIT_MIN_MATCHED_EVIDENCE_RATIO`, clamp 0–1 (default 0.72)."""
    raw = os.getenv("AUDIT_MIN_MATCHED_EVIDENCE_RATIO", "0.72")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        parsed = 0.72
    return max(0.0, min(parsed, 1.0))
