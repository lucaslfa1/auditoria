"""Seed data for audit sectors, alerts, and criteria.

Loads all scoring configuration from scoring_rules.yaml (POP official document).
The YAML is the single source of truth — do NOT add hardcoded criteria here.
"""

from db.scoring_loader import build_seed_data_from_yaml, build_sectors_from_yaml


def build_alert_seed_data():
    """Retorna lista de (alert_id, sector_id, label, context, [(crit_label, weight, desc, evaluation_type)]).

    All data comes from scoring_rules.yaml, which mirrors the official POP document
    (POP - AUDITORIA DE LIGAÇÕES GERAL, rev. 28/01/2025).
    """
    return build_seed_data_from_yaml()


def build_sector_seed_data():
    """Retorna lista de (sector_id, label, description).

    All data comes from scoring_rules.yaml.
    """
    return build_sectors_from_yaml()
