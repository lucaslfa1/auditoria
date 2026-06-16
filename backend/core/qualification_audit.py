"""Override de auditoria para o critério de "Qualificação do Atendimento".

Em setores que NÃO são de risco, o motivo registrado pela telefonia Huawei
(ex.: ``huawei_call_reason``) já comprova a qualificação do atendimento.
Este módulo detecta critérios de qualificação na checklist e, quando há um
motivo Huawei presente, aplica benevolência: marca o critério como ``pass``
com evidência do motivo externo, sem penalizar o operador (resultado
persistido é binário).

Não chama a IA: trabalha sobre metadata já disponível e a lista de critérios.
Sem custo de API (só CPU).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from schemas import AuditAlert, AuditCriterion


@dataclass(frozen=True)
class QualificationEvaluation:
    """Resultado de uma avaliação de qualificação por motivo Huawei.

    Campos: ``comment`` (texto pronto para o auditor), ``huawei_reason``
    (motivo cru extraído da metadata) e ``expected_terms`` (termos esperados
    do motivo, vindos da regra casada ou dos alvos de motivo do setor).
    Imutável (frozen)."""
    comment: str
    huawei_reason: str
    expected_terms: list[str]


@dataclass(frozen=True)
class _ReasonRule:
    name: str
    alert_terms: tuple[str, ...]
    reason_terms: tuple[str, ...]


_QUALIFICATION_RULES: tuple[_ReasonRule, ...] = (
    _ReasonRule("antecedentes", ("antecedente",), ("antecedente",)),
    _ReasonRule("controle_temperatura", ("temperatura",), ("controle temperatura", "temperatura")),
    _ReasonRule("parada", ("parada",), ("parada",)),
    _ReasonRule("desvio", ("desvio",), ("desvio",)),
    _ReasonRule("fim_viagem", ("fim viagem", "fim de viagem"), ("fim viagem", "fim de viagem")),
    _ReasonRule("devolucao", ("devolucao",), ("devolucao",)),
    _ReasonRule("atuacao_tratativa", ("atuacao tratativa", "tratativa"), ("atuacao tratativa", "tratativa")),
    _ReasonRule("distribuicao", ("distribuicao",), ("distribuicao",)),
    _ReasonRule("cabinets", ("cabinet", "cabinets"), ("cabinet", "cabinets")),
    _ReasonRule("loss_tree", ("loss tree",), ("loss tree",)),
    _ReasonRule("atraso", ("atraso",), ("atraso",)),
    _ReasonRule("ativacao_ae", ("ativacao ae", "ativacao de ae"), ("ativacao ae", "ae")),
    _ReasonRule("espelhamento", ("espelhamento",), ("espelhamento",)),
    _ReasonRule("perda_posicao", ("perda posicao", "posicao em atraso"), ("perda posicao", "posicao")),
    _ReasonRule("taborda", ("taborda",), ("taborda",)),
    _ReasonRule("checklist", ("checklist",), ("checklist", "atendimento horario", "atendimento do horario")),
    _ReasonRule(
        "receptivo_chatbot",
        ("chatbot",),
        ("envio comandos", "envio de comandos", "embarque macros", "embarque de macros", "fim viagem", "desligar sirene", "desbloqueio"),
    ),
)

_HUAWEI_REASON_KEYS = (
    "huawei_call_reason",
    "huawei_talk_reason",
    "huawei_talk_remark",
    "callReason",
    "talkReason",
    "talkRemark",
    "motivo",
)


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _contains_phrase(text: str, phrase: str) -> bool:
    normalized_text = f" {_normalize_text(text)} "
    normalized_phrase = _normalize_text(phrase)
    if not normalized_phrase:
        return False
    return f" {normalized_phrase} " in normalized_text


def is_qualification_criterion(criterion: AuditCriterion) -> bool:
    """Retorna ``True`` se o critério é o de "Qualificação do Atendimento",
    identificado pelo label normalizado conter tanto "qualificacao" quanto
    "atendimento"."""
    label = _normalize_text(getattr(criterion, "label", ""))
    return "qualificacao" in label and "atendimento" in label


def _qualification_criterion_ids(criteria_list: Iterable[AuditCriterion]) -> list[str]:
    return [
        str(getattr(criterion, "id", "") or "").strip()
        for criterion in criteria_list
        if str(getattr(criterion, "id", "") or "").strip() and is_qualification_criterion(criterion)
    ]


def _extract_source_metadata(audio_quality: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(audio_quality, dict):
        return {}

    metadata: dict[str, Any] = {}
    audit_pipeline = audio_quality.get("audit_pipeline")
    if isinstance(audit_pipeline, dict):
        source_metadata = audit_pipeline.get("source_metadata")
        if isinstance(source_metadata, dict):
            metadata.update(source_metadata)
        metadata.update({k: v for k, v in audit_pipeline.items() if k not in {"source_metadata", "classification", "context_repair"}})

    metadata.update({k: v for k, v in audio_quality.items() if k in _HUAWEI_REASON_KEYS})
    return metadata


def _get_huawei_reason(metadata: dict[str, Any]) -> str:
    for key in _HUAWEI_REASON_KEYS:
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return ""


def _coerce_reason_targets(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"[,;/|]+", value) if part.strip()]
    return []


def _reason_targets_from_metadata_or_sector(metadata: dict[str, Any], sector_id: Optional[str]) -> list[str]:
    targets = _coerce_reason_targets(metadata.get("native_reason_targets"))
    if targets:
        return targets

    try:
        from core.automation_rules import AUTOMATION_RULES

        rule = AUTOMATION_RULES.get(_normalize_text(sector_id).replace(" ", "_"), {})
        return [str(item).strip() for item in rule.get("motivos_alvo", []) if str(item).strip()]
    except Exception:
        return []


def _is_risk_sector(sector_id: Optional[str]) -> bool:
    try:
        from core.huawei_direction import OUTBOUND_ONLY_RISK_SECTORS, normalize_huawei_sector

        normalized = normalize_huawei_sector(sector_id)
        return normalized in OUTBOUND_ONLY_RISK_SECTORS
    except Exception:
        return _normalize_text(sector_id).replace(" ", "_") in {"uti", "bas", "distribuicao", "fenix", "transferencia"}


def _alert_text(alert: Optional[AuditAlert], metadata: dict[str, Any]) -> str:
    parts = []
    if alert is not None:
        parts.extend([
            getattr(alert, "id", ""),
            getattr(alert, "label", ""),
            getattr(alert, "context", ""),
        ])
    parts.extend([
        metadata.get("alert_id"),
        metadata.get("alert_label"),
        metadata.get("classification"),
    ])
    return _normalize_text(" ".join(str(part or "") for part in parts))


def _matched_rule_for_alert(alert_blob: str) -> Optional[_ReasonRule]:
    for rule in _QUALIFICATION_RULES:
        if any(_contains_phrase(alert_blob, term) for term in rule.alert_terms):
            return rule
    return None


def evaluate_qualification(
    *,
    criteria_list: list[AuditCriterion],
    alert: Optional[AuditAlert],
    audio_quality: Optional[dict[str, Any]],
    sector_id: Optional[str],
) -> Optional[QualificationEvaluation]:
    """Decide se a qualificação do atendimento pode ser validada pelo motivo
    Huawei e, em caso afirmativo, devolve a avaliação.

    Retorna ``None`` (sem override) quando: não há critério de qualificação na
    checklist; o setor é de risco (``_is_risk_sector``); ou não há motivo Huawei
    na metadata. Caso contrário, casa o alerta com uma regra
    (``_QUALIFICATION_RULES``) para derivar os termos esperados (ou cai nos
    alvos de motivo do setor) e monta o comentário. Parâmetros keyword-only.
    Sem efeitos colaterais.
    """
    if not _qualification_criterion_ids(criteria_list):
        return None
    if _is_risk_sector(sector_id):
        return None

    metadata = _extract_source_metadata(audio_quality)
    reason = _get_huawei_reason(metadata)
    if not reason:
        return None

    alert_blob = _alert_text(alert, metadata)
    matched_rule = _matched_rule_for_alert(alert_blob)

    if matched_rule is not None:
        expected_terms = list(matched_rule.reason_terms)
    else:
        expected_terms = _reason_targets_from_metadata_or_sector(metadata, sector_id)

    expected_text = ", ".join(expected_terms) if expected_terms else "tipo identificado na auditoria"
    # Compliance: o resultado persistido deve ser binario. Quando a qualificacao
    # depende apenas de metadata externa da Huawei, mantemos evidencia para o
    # auditor e aplicamos benevolencia para nao penalizar o operador.
    comment = f"Qualificação validada por motivo Huawei: {reason}"

    return QualificationEvaluation(
        comment=comment,
        huawei_reason=reason,
        expected_terms=expected_terms,
    )


def apply_qualification_result_override(
    payload: dict[str, Any],
    criteria_list: list[AuditCriterion],
    *,
    alert: Optional[AuditAlert],
    audio_quality: Optional[dict[str, Any]],
    sector_id: Optional[str],
) -> dict[str, Any]:
    """Aplica o override de qualificação ao payload de resultado da auditoria.

    Chama ``evaluate_qualification``; se não houver avaliação, devolve o
    ``payload`` inalterado. Caso haja, retorna uma CÓPIA do payload com a lista
    ``details`` ajustada: cada critério de qualificação vira ``status=pass`` com
    evidência do motivo Huawei (método ``external_metadata``), e critérios de
    qualificação ausentes em ``details`` são adicionados. Não muta o payload
    original. Parâmetros ``alert``/``audio_quality``/``sector_id`` são
    keyword-only. Sem efeitos colaterais externos.
    """
    evaluation = evaluate_qualification(
        criteria_list=criteria_list,
        alert=alert,
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    if evaluation is None:
        return payload

    qualification_ids = set(_qualification_criterion_ids(criteria_list))
    normalized = dict(payload)
    raw_details = normalized.get("details")
    details = [dict(item) for item in raw_details if isinstance(item, dict)] if isinstance(raw_details, list) else []
    existing_ids = {str(item.get("criterionId") or "").strip() for item in details}

    override = {
        "status": "pass",
        "comment": evaluation.comment,
        "timestamp": "",
        "evidence_text": f"Motivo Huawei: {evaluation.huawei_reason}",
        "evidence_validation": {
            "status": "pass",
            "matched": False,
            "method": "external_metadata",
            "source": "huawei_call_reason",
        },
    }

    updated_details: list[dict[str, Any]] = []
    for item in details:
        criterion_id = str(item.get("criterionId") or "").strip()
        if criterion_id in qualification_ids:
            updated_details.append({"criterionId": criterion_id, **override})
        else:
            updated_details.append(item)

    for criterion_id in sorted(qualification_ids - existing_ids):
        updated_details.append({"criterionId": criterion_id, **override})

    normalized["details"] = updated_details
    return normalized
