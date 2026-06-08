from __future__ import annotations
"""Shared mapping helpers for gestores exports and weight generation."""


from functools import lru_cache
from typing import Optional
import unicodedata

from db.scoring_loader import load_scoring_rules

SECTOR_MAP = {
    "bas": "BAS",
    "uti": "UTI",
    "transferencia": "TRANSFERÊNCIA",
    "distribuicao": "DISTRIBUIÇÃO",
    "fenix": "FÊNIX",
    "cadastro": "CADASTRO",
    "logistica_unilever": "UNILEVER",
    "logistica": "LOGÍSTICA",
    "mondelez": "MONDELEZ",
    "checklist": "CHECKLIST",
    "receptivo": "RECEPTIVO",
}

_ALERT_EXPORT_METADATA = {
    "UTI-PRIORITARIO-MOT": ("ALERTAS PRIORITÁRIOS", "Motorista"),
    "UTI-PRIORITARIO-CLI": ("ALERTAS PRIORITÁRIOS", "Cliente"),
    "UTI-POSICAO-MOT": ("POSIÇÃO EM ATRASO", "Motorista"),
    "UTI-POSICAO-CLI": ("POSIÇÃO EM ATRASO", "Cliente"),
    "UTI-PARADA-MOT": ("PARADA INDEVIDA", "Motorista"),
    "UTI-PARADA-CLI": ("PARADA INDEVIDA", "Cliente"),
    "UTI-DESVIO-MOT": ("DESVIO DE ROTA", "Motorista"),
    "UTI-DESVIO-CLI": ("DESVIO DE ROTA", "Cliente"),
    "UTI-PONTO-APOIO": ("PONTO DE APOIO", "Ponto de Apoio"),
    "BAS-PRIORITARIO-POLICIA": ("ACIONAMENTO POLICIAL", "Polícia"),
    "BAS-POLICIAL": ("ACIONAMENTO POLICIAL", "Polícia"),
    "CADASTRO-ANTECEDENTES": ("ANTECEDENTES", "Receptiva"),
    "UNILEVER-DEVOLUCAO": ("DEVOLUÇÃO", "Cliente"),
    "UNILEVER-CABINETS": ("CABINETS", "Cliente"),
    "UNILEVER-TRATATIVA": ("ATUAÇÃO TRATATIVA", "Cliente"),
    "UNILEVER-DISTRIBUICAO": ("DISTRIBUIÇÃO", "Cliente"),
    "UNILEVER-LOSSTREE": ("LOSS TREE", "Cliente"),
    "LOGISTICA-ESTADIA": ("ESTADIA", "Motorista"),
    "LOGISTICA-TEMPERATURA-MOT": ("CONTROLE DE TEMPERATURA", "Motorista"),
    "LOGISTICA-TEMPERATURA-CLI": ("CONTROLE DE TEMPERATURA", "Cliente"),
    "LOGISTICA-DESLIG-TEMP-MOT": ("DESLIGAMENTO (TEMPERATURA)", "Motorista"),
    "LOGISTICA-DESLIG-TEMP-CLI": ("DESLIGAMENTO (TEMPERATURA)", "Cliente"),
    "LOGISTICA-ATRASO-ENTREGA": ("ATRASO DE ENTREGA", "Motorista"),
    "LOGISTICA-PARADA": ("PARADA INDEVIDA (LOG)", "Motorista"),
    "LOGISTICA-DESVIO": ("DESVIO DE ROTA (LOG)", "Motorista"),
    "LOGISTICA-ATIVACAO-AE": ("ATIVAÇÃO DE AE", "Cliente"),
    "LOGISTICA-ATRASO": ("ATRASO", "Cliente"),
    "LOGISTICA-POSICAO": ("POSIÇÃO EM ATRASO (LOG)", "Motorista"),
    "LOGISTICA-TABORDA": ("OPERAÇÃO TABORDA", "Receptiva"),
    "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI": ("VIAGEM SEM ESPELHAMENTO", "Cliente"),
    "LOGISTICA-PERDA-POSICAO-CLI": ("PERDA DE POSIÇÃO", "Cliente"),
    "LOGISTICA-PARADA-EXCESSIVA-MOT": ("PARADA EXCESSIVA", "Motorista"),
    "LOGISTICA-PARADA-EXCESSIVA-CLI": ("PARADA EXCESSIVA", "Cliente"),
    "MONDELEZ-LOGISTICA-REVERSA": ("LOGÍSTICA REVERSA", "Receptiva"),
    "MONDELEZ-MONITORAMENTO-I": ("MONITORAMENTO I", "Receptiva"),
    "MONDELEZ-MONITORAMENTO-II": ("MONITORAMENTO II", "Receptiva"),
    "CHECKLIST-VEICULO": ("CHECKLIST", "Receptiva"),
    "RECEPTIVO-CHATBOT": ("PROCESSO CHATBOT", "Receptiva"),
}

_ALERT_ID_ALIASES = {
    "BAS-POLICIAL": "BAS-PRIORITARIO-POLICIA",
}

_ALERT_LABEL_ALIASES = {
    "Acionamento Policial": "BAS-PRIORITARIO-POLICIA",
    "Alerta Prioritario - Policia": "BAS-PRIORITARIO-POLICIA",
    "Alerta Prioritário - Polícia": "BAS-PRIORITARIO-POLICIA",
}


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").strip().lower())
    collapsed = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return collapsed.replace("\ufffd", "")


def _infer_contact_type(alert_id: str, alert_label: str) -> str:
    normalized_label = _normalize(alert_label)
    normalized_id = _normalize(alert_id)
    if "ponto de apoio" in normalized_label or "ponto-apoio" in normalized_id:
        return "Ponto de Apoio"
    if "policia" in normalized_label or "policial" in normalized_label:
        return "Polícia"
    if "receptiv" in normalized_label:
        return "Receptiva"
    if "cliente" in normalized_label or normalized_id.endswith("-cli"):
        return "Cliente"
    return "Motorista"


def resolve_alert_export_metadata(alert_id: str, alert_label: str) -> tuple[str, str]:
    canonical_id = _ALERT_ID_ALIASES.get(alert_id, alert_id)
    gestores_label, contact_type = _ALERT_EXPORT_METADATA.get(canonical_id, ("", ""))
    if gestores_label:
        return gestores_label, contact_type

    fallback_label = str(alert_label or alert_id or "NAO IDENTIFICADO").strip().upper()
    return fallback_label, _infer_contact_type(alert_id, alert_label)


@lru_cache(maxsize=1)
def get_gestores_alert_catalog() -> dict[str, dict[str, str]]:
    rules = load_scoring_rules()
    catalog: dict[str, dict[str, str]] = {}
    for alert in rules.get("alerts", []):
        alert_id = str(alert["id"])
        alert_label = str(alert.get("label", ""))
        gestores_label, contact_type = resolve_alert_export_metadata(alert_id, alert_label)
        catalog[alert_id] = {
            "alert_label": alert_label,
            "gestores_label": gestores_label,
            "contact_type": contact_type,
        }
    return catalog


@lru_cache(maxsize=1)
def get_gestores_alert_label_lookup() -> dict[str, str]:
    label_lookup: dict[str, str] = {}
    for alert_id, metadata in get_gestores_alert_catalog().items():
        label_lookup[_normalize(metadata["alert_label"])] = alert_id
    for alias_label, target_alert_id in _ALERT_LABEL_ALIASES.items():
        label_lookup[_normalize(alias_label)] = target_alert_id
    return label_lookup


def resolve_gestores_alert(
    *,
    alert_id: Optional[str],
    alert_label: Optional[str],
) -> tuple[str, str, Optional[str]]:
    raw_alert_id = str(alert_id or "").strip()
    raw_alert_label = str(alert_label or "").strip()
    catalog = get_gestores_alert_catalog()

    resolved_id = _ALERT_ID_ALIASES.get(raw_alert_id, raw_alert_id)
    metadata = catalog.get(resolved_id)
    if metadata:
        return metadata["gestores_label"], metadata["contact_type"], resolved_id

    resolved_id = get_gestores_alert_label_lookup().get(_normalize(raw_alert_label))
    if resolved_id:
        metadata = catalog.get(resolved_id)
        if metadata:
            return metadata["gestores_label"], metadata["contact_type"], resolved_id

    fallback_label = raw_alert_label.upper() if raw_alert_label else (resolved_id or raw_alert_id or "NAO IDENTIFICADO")
    fallback_contact = _infer_contact_type(raw_alert_id, raw_alert_label)
    return fallback_label, fallback_contact, resolved_id or raw_alert_id or None
