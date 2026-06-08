from __future__ import annotations

from functools import lru_cache
import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "audit_rules.yaml"


def _as_text_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip().lower() for item in value if str(item).strip()}


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


@lru_cache(maxsize=1)
def load_audit_rules(path: Optional[str] = None) -> dict[str, Any]:
    rules_path = Path(path).resolve() if path else _RULES_PATH
    try:
        with open(rules_path, "r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}
    except Exception as exc:
        logger.error("Falha ao carregar regras de auditoria em %s: %s", rules_path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def get_password_rule_sectors() -> set[str]:
    return _as_text_set(load_audit_rules().get("password_rule_sectors"))


def get_rastreamento_sectors() -> set[str]:
    return _as_text_set(load_audit_rules().get("rastreamento_sectors"))


def get_password_criterion_keys() -> set[str]:
    return _as_text_set(load_audit_rules().get("password_criterion_keys"))


def get_sector_prompt_rules(sector_id: Optional[str]) -> Optional[dict[str, str]]:
    sector_key = str(sector_id or "").strip().lower()
    if not sector_key:
        return None
    rules = load_audit_rules().get("sector_prompt_rules")
    if not isinstance(rules, dict):
        return None
    value = rules.get(sector_key)
    if not isinstance(value, dict):
        return None
    return {
        "label": str(value.get("label") or sector_key),
        "tipo_ligacao": str(value.get("tipo_ligacao") or ""),
        "regras_zeragem": str(value.get("regras_zeragem") or ""),
    }


def password_rule_applies_to_sector(sector_id: Optional[str]) -> bool:
    sector_key = str(sector_id or "").strip().lower()
    if not sector_key:
        return True
    return sector_key in get_password_rule_sectors()


def get_fatal_flag_sectors(flag: str) -> set[str]:
    flags = load_audit_rules().get("fatal_flags")
    if not isinstance(flags, dict):
        return set()
    payload = flags.get(str(flag or "").strip())
    if not isinstance(payload, dict):
        return set()
    return _as_text_set(payload.get("sectors"))


def get_fatal_flag_reason_text(flag: str) -> str:
    flags = load_audit_rules().get("fatal_flags")
    if not isinstance(flags, dict):
        return ""
    payload = flags.get(str(flag or "").strip())
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("reason_text") or "").strip()


def get_fatal_keywords_for_sector(sector_id: Optional[str]) -> list[str]:
    sector_key = str(sector_id or "").strip().lower()
    rules = load_audit_rules().get("fatal_keywords_by_sector")
    if not isinstance(rules, dict):
        return []
    return _as_text_list(rules.get(sector_key))
