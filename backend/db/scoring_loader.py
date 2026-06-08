"""Loader and validator for scoring_rules.yaml.

Reads the YAML scoring configuration and provides functions to:
- Load and cache the parsed rules
- Build seed data tuples compatible with database.py
- Validate the YAML structure
"""

import os
import logging
from pathlib import Path
from typing import Any, Optional
import math

import yaml

logger = logging.getLogger(__name__)

_YAML_PATH = Path(__file__).resolve().parent / "seeds" / "scoring_rules.bootstrap.yaml"
_cached_rules: Optional[dict] = None
_MAX_CRITERION_WEIGHT = 10.0


def _validate_loaded_rules(data: dict) -> list[str]:
    errors: list[str] = []

    if not isinstance(data, dict) or "alerts" not in data:
        return ["Invalid scoring_rules.yaml: missing 'alerts' key"]

    sr = data.get("scoring_rules")
    if not sr:
        errors.append("Missing 'scoring_rules' section")
    else:
        for key in ("pass", "fail"):
            if key not in sr:
                errors.append(f"Missing scoring_rules.{key}")

    sectors = data.get("sectors", [])
    if not sectors:
        errors.append("No sectors defined")
    sector_ids = set()
    for sector in sectors:
        sector_id = sector.get("id")
        if not sector_id:
            errors.append(f"Sector missing 'id': {sector}")
        elif sector_id in sector_ids:
            errors.append(f"Duplicate sector id: {sector_id}")
        else:
            sector_ids.add(sector_id)

    alerts = data.get("alerts", [])
    if not alerts:
        errors.append("No alerts defined")

    alert_ids = set()
    for alert in alerts:
        alert_id = alert.get("id")
        if not alert_id:
            errors.append(f"Alert missing 'id': {alert.get('label', '?')}")
            continue

        if alert_id in alert_ids:
            errors.append(f"Duplicate alert id: {alert_id}")
        alert_ids.add(alert_id)

        if alert.get("sector") not in sector_ids:
            errors.append(f"Alert {alert_id}: sector '{alert.get('sector')}' not in sectors")

        if not alert.get("label"):
            errors.append(f"Alert {alert_id}: missing 'label'")

        criteria = alert.get("criteria", [])
        if not criteria:
            errors.append(f"Alert {alert_id}: no criteria defined")
            continue

        total_weight = 0.0
        for index, criterion in enumerate(criteria):
            if not criterion.get("label"):
                errors.append(f"Alert {alert_id}, criterion {index}: missing 'label'")

            weight = criterion.get("weight")
            if weight is None or not isinstance(weight, (int, float)):
                errors.append(f"Alert {alert_id}, criterion {index}: invalid weight '{weight}'")
                continue
            if not math.isfinite(float(weight)):
                errors.append(f"Alert {alert_id}, criterion {index}: non-finite weight '{weight}'")
                continue
            if weight <= 0:
                errors.append(f"Alert {alert_id}, criterion {index}: weight must be > 0")
                continue
            if weight > _MAX_CRITERION_WEIGHT:
                errors.append(
                    f"Alert {alert_id}, criterion {index}: weight '{weight}' exceeds max {_MAX_CRITERION_WEIGHT}"
                )
                continue
            total_weight += float(weight)

        if total_weight <= 0:
            errors.append(f"Alert {alert_id}: total criteria weight must be > 0")

    return errors


def load_scoring_rules(path: Optional[str] = None) -> dict:
    """Load and cache scoring rules from YAML.

    Returns the parsed YAML as a dict with keys:
      scoring_rules, sectors, alerts
    """
    global _cached_rules
    if _cached_rules is not None and path is None:
        return _cached_rules

    yaml_path = Path(path) if path else _YAML_PATH
    if not yaml_path.exists():
        raise FileNotFoundError(f"Scoring rules not found: {yaml_path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Replicate UTI alerts to other risk sectors (BAS is kept separate as it only requires Police)
    target_risk_sectors = ["distribuicao", "fenix", "transferencia"]
    uti_alerts = [a for a in data.get("alerts", []) if a.get("sector") == "uti"]

    # Remove any existing alerts for these sectors to prevent duplicates
    data["alerts"] = [a for a in data.get("alerts", []) if a.get("sector") not in target_risk_sectors]

    import copy
    for target_sector in target_risk_sectors:
        for uti_alert in uti_alerts:
            new_alert = copy.deepcopy(uti_alert)
            new_alert["sector"] = target_sector
            # Replace the "UTI-" prefix with the target sector's prefix
            if new_alert["id"].startswith("UTI-"):
                new_alert["id"] = f"{target_sector.upper()}-" + new_alert["id"][4:]
            else:
                new_alert["id"] = f"{target_sector.upper()}-{new_alert['id']}"
            data["alerts"].append(new_alert)

    errors = _validate_loaded_rules(data)
    if errors:
        raise ValueError("Invalid scoring_rules.yaml: " + "; ".join(errors))

    if path is None:
        _cached_rules = data
    return data


def get_sectors(rules: Optional[dict] = None) -> list[dict]:
    """Return list of sector dicts from rules."""
    rules = rules or load_scoring_rules()
    return rules.get("sectors", [])


def get_alerts(rules: Optional[dict] = None) -> list[dict]:
    """Return list of alert dicts from rules."""
    rules = rules or load_scoring_rules()
    return rules.get("alerts", [])


def get_alert_by_id(alert_id: str, rules: Optional[dict] = None) -> Optional[dict]:
    """Return a single alert dict by its id, or None."""
    for alert in get_alerts(rules):
        if alert["id"] == alert_id:
            return alert
    return None


def build_seed_data_from_yaml(rules: Optional[dict] = None) -> list[tuple]:
    """Build alert seed data tuples from YAML.

    Returns list of (alert_id, sector_id, label, context, pop_ref, expected_direction,
                     [(crit_label, weight, desc, evaluation_type, deflator)])
    Compatible with the format expected by database._seed_audit_criteria().
    """
    rules = rules or load_scoring_rules()
    alerts = get_alerts(rules)
    result = []

    for alert in alerts:
        alert_id = alert["id"]
        sector_id = alert["sector"]
        label = alert["label"]
        context = alert.get("context", "")
        pop_ref = alert.get("pop_ref", "") or None
        expected_direction = alert.get("expected_direction", "") or None

        criteria_tuples = []
        for crit in alert.get("criteria", []):
            crit_label = crit["label"]
            weight = float(crit["weight"])
            deflator = float(crit.get("deflator", 0.0))
            desc = crit.get("description", "")
            eval_type = crit.get("evaluation_type", "auto")
            criteria_tuples.append((crit_label, weight, desc, eval_type, deflator))

        result.append((alert_id, sector_id, label, context, pop_ref, expected_direction, criteria_tuples))

    return result


def build_sectors_from_yaml(rules: Optional[dict] = None) -> list[tuple]:
    """Build sector seed data tuples from YAML.

    Returns list of (sector_id, label, description).
    """
    rules = rules or load_scoring_rules()
    sectors = get_sectors(rules)
    return [(s["id"], s["label"], s.get("description", "")) for s in sectors]


def validate_yaml(rules: Optional[dict] = None) -> list[str]:
    """Validate the scoring rules YAML structure.

    Returns a list of error messages. Empty list means valid.
    """
    errors = []
    try:
        rules = rules or load_scoring_rules()
    except Exception as e:
        return [f"Failed to load YAML: {e}"]
    return errors + _validate_loaded_rules(rules)


def get_scoring_summary() -> str:
    """Generate a human-readable summary of the scoring configuration."""
    rules = load_scoring_rules()
    lines = [
        "=" * 60,
        "RESUMO DA CONFIGURAÇÃO DE PONTUAÇÃO",
        f"Fonte: {_YAML_PATH.name}",
        "=" * 60,
        "",
    ]

    # Scoring rules
    sr = rules.get("scoring_rules", {})
    lines.append("Regras de pontuação:")
    for k, v in sr.items():
        lines.append(f"  {k}: {v}")
    lines.append("")

    # Sectors
    sectors = get_sectors(rules)
    lines.append(f"Setores ({len(sectors)}):")
    for s in sectors:
        lines.append(f"  {s['id']:25s} {s['label']}")
    lines.append("")

    # Alerts per sector
    alerts = get_alerts(rules)
    alerts_by_sector: dict[str, list] = {}
    for a in alerts:
        alerts_by_sector.setdefault(a["sector"], []).append(a)

    lines.append(f"Alertas ({len(alerts)} total):")
    for sid in sorted(alerts_by_sector):
        sector_alerts = alerts_by_sector[sid]
        lines.append(f"\n  [{sid}] ({len(sector_alerts)} alertas)")
        for a in sector_alerts:
            n_crit = len(a.get("criteria", []))
            total_w = sum(c["weight"] for c in a.get("criteria", []))
            pop = a.get("pop_ref", "")
            lines.append(f"    {a['id']:35s} {n_crit:2d} critérios  peso total: {total_w:.2f}  POP: {pop}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Standalone validation and summary
    errors = validate_yaml()
    if errors:
        print("ERROS ENCONTRADOS:")
        for e in errors:
            print(f"  ✗ {e}")
    else:
        print("✓ YAML válido\n")

    print(get_scoring_summary())
