"""Equivalência de alertas entre setores operacionais (mesmos POPs 4.1.x).

Os setores operacionais (transferência, UTI, BAS, distribuição, Fênix) e a
logística compartilham os mesmos "tipos" de ocorrência (parada excessiva,
perda de posição, prioritário/polícia, desvio de rota...), só que cada setor
nomeia o alerta com seu próprio prefixo (ex.: `UTI-POSICAO-MOT` ↔
`DISTRIBUICAO-POSICAO-MOT`). Este módulo concentra a lógica que, dado um
alert_id de um setor, encontra o alerta equivalente em outro.

Extraído de `core/classification.py` (v1.3.137) sem mudança de comportamento;
os nomes continuam reexportados de `core.classification` para compatibilidade
(inclusive testes que acessam `classification._OPERATIONAL_SECTORS`).

Monkeypatch: `_get_catalog_alert`/`_apply_alert_match` resolvem
`load_audit_criteria_catalog` em RUNTIME via `core.classification` para honrar
os patches dos testes (e evitar import circular no carregamento).
"""

import re as _re
import unicodedata

_OPERATIONAL_SECTORS = {"transferencia", "uti", "bas", "distribuicao", "fenix"}
_OPERATIONAL_ALERT_PREFIXES = {
    "uti": "UTI",
    "transferencia": "TRANSFERENCIA",
    "distribuicao": "DISTRIBUICAO",
    "fenix": "FENIX",
    "bas": "BAS",
}

_LOGISTICA_KIND_ALERTS = {
    ("VIAGEM-SEM-ESPELHAMENTO", "CLI"): "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI",
    ("PERDA-POSICAO", "CLI"): "LOGISTICA-PERDA-POSICAO-CLI",
    ("PARADA-EXCESSIVA", "MOT"): "LOGISTICA-PARADA-EXCESSIVA-MOT",
    ("PARADA-EXCESSIVA", "CLI"): "LOGISTICA-PARADA-EXCESSIVA-CLI",
    ("POSICAO", "CLI"): "LOGISTICA-PERDA-POSICAO-CLI",
}


def _get_catalog_alert(sector_id: str, alert_id: str) -> tuple[str, str, str] | None:
    """Busca exata do alerta dentro de um setor do catálogo → (sector_id, alert_id, label) ou None."""
    from core import classification as _clf  # runtime: honra monkeypatch de load_audit_criteria_catalog

    sector_id = str(sector_id or "").strip().lower()
    alert_id = str(alert_id or "").strip()
    for alert in _clf.load_audit_criteria_catalog().get(sector_id, {}).get("alerts", []):
        if alert["id"] == alert_id:
            return sector_id, alert_id, str(alert["label"])
    return None


def _apply_alert_match(classification: dict, alert_match: tuple[str, str, str]) -> dict:
    """Aplica (setor, alerta, label) encontrados no catálogo ao dict de classificação."""
    from core import classification as _clf  # runtime: honra monkeypatch de load_audit_criteria_catalog

    sector_id, alert_id, alert_label = alert_match
    catalog = _clf.load_audit_criteria_catalog()
    classification["sector_id"] = sector_id
    classification["sector_label"] = str(catalog.get(sector_id, {}).get("label") or sector_id)
    classification["alert_id"] = alert_id
    classification["alert_label"] = alert_label
    return classification


def _normalize_alert_token(value: str | None) -> str:
    """Normaliza texto p/ comparação de alertas: MAIÚSCULO, sem acento, separado por '-'."""
    normalized = unicodedata.normalize("NFD", str(value or "").strip().upper())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = _re.sub(r"[^A-Z0-9]+", "-", normalized)
    return normalized.strip("-")


def _infer_alert_actor_suffix(*values: str | None) -> str:
    """Infere quem é o interlocutor do alerta: 'CLI' (cliente/destinatário) ou 'MOT' (motorista, default)."""
    joined = " ".join(_normalize_alert_token(value) for value in values if value)
    if "-CLI" in f"-{joined}-" or "CLIENTE" in joined or "DESTINATARIO" in joined or "EMBARCADOR" in joined:
        return "CLI"
    return "MOT"


def _extract_operational_alert_kind(value: str | None) -> str | None:
    """Extrai o "tipo" genérico do alerta (PARADA, DESVIO, POSICAO, PRIORITARIO...)
    de um id/label qualquer — base para achar o equivalente em outro setor."""
    token = _normalize_alert_token(value)
    if not token:
        return None
    if "ESPELHAMENTO" in token:
        return "VIAGEM-SEM-ESPELHAMENTO"
    if "PERDA" in token and ("POSICAO" in token or "SINAL" in token):
        return "PERDA-POSICAO"
    if "PARADA" in token and "EXCESSIVA" in token:
        return "PARADA-EXCESSIVA"
    if "POLICIA" in token or "POLICIAL" in token:
        return "PRIORITARIO-POLICIA"
    if "PONTO-APOIO" in token or ("PONTO" in token and "APOIO" in token):
        return "PONTO-APOIO"
    if "PRIORITARIO" in token or "VIOLACAO" in token or "PANICO" in token or "DESENGATE" in token:
        return "PRIORITARIO"
    if "POSICAO" in token or "SINAL" in token:
        return "POSICAO"
    if "PARADA" in token:
        return "PARADA"
    if "DESVIO" in token or "ROTA" in token:
        return "DESVIO"
    return None


def _operational_alert_suffix(kind: str, actor: str = "MOT") -> str:
    """Monta o sufixo do alert_id setorial a partir do tipo + ator (ex.: PARADA + CLI → PARADA-CLI)."""
    kind = _normalize_alert_token(kind)
    actor = "CLI" if str(actor or "").upper() == "CLI" else "MOT"
    if kind in {"PRIORITARIO-POLICIA", "PONTO-APOIO"}:
        return kind
    if kind in {"PRIORITARIO", "POSICAO", "PARADA", "DESVIO"}:
        return f"{kind}-{actor}"
    return kind


def _get_equivalent_alert_for_sector(
    sector_id: str,
    kind_or_alert_id: str,
    *,
    actor: str = "MOT",
) -> tuple[str, str, str] | None:
    """Encontra no setor dado o alerta equivalente a um alert_id/tipo de OUTRO setor.

    Ex.: UTI-POSICAO-MOT + sector_id='distribuicao' → DISTRIBUICAO-POSICAO-MOT.
    Tenta match direto, depois reconstrói pelo tipo (`_extract_operational_alert_kind`)
    usando o prefixo do setor; logística tem mapa próprio. Retorna None se não houver equivalente.
    """
    sector_id = str(sector_id or "").strip().lower()
    if not sector_id:
        return None

    direct_match = _get_catalog_alert(sector_id, kind_or_alert_id)
    if direct_match:
        return direct_match

    kind = _extract_operational_alert_kind(kind_or_alert_id)
    if not kind:
        return None

    if sector_id in _OPERATIONAL_ALERT_PREFIXES:
        prefix = _OPERATIONAL_ALERT_PREFIXES[sector_id]
        candidate = f"{prefix}-{_operational_alert_suffix(kind, actor)}"
        match = _get_catalog_alert(sector_id, candidate)
        if match:
            return match

    if sector_id == "logistica":
        actor = "CLI" if str(actor or "").upper() == "CLI" else "MOT"
        specific_candidate = _LOGISTICA_KIND_ALERTS.get((kind, actor))
        if specific_candidate:
            match = _get_catalog_alert(sector_id, specific_candidate)
            if match:
                return match
        base_kind = kind.split("-", 1)[0]
        candidate = f"LOGISTICA-{base_kind}"
        return _get_catalog_alert(sector_id, candidate)

    return None
