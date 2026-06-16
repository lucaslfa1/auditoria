"""Acesso às regras de auditoria externalizadas em ``config/audit_rules.yaml``.

Lê o YAML uma vez (cache via ``lru_cache``) e expõe getters tipados para as
seções de configuração que ditam regras de negócio da avaliação: setores com
regra de senha, setores de rastreamento, chaves de critério de senha, regras de
prompt por setor, setores afetados por cada fatal flag (zeragem) e palavras-chave
fatais por setor. Sem custo de API (só leitura de arquivo/CPU).

Falha ao ler/parsear o YAML é tolerada (log de erro + dict vazio), de modo que
ausência de configuração equivale a "regra não definida".
"""

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
    """Carrega e retorna o dict de regras do ``audit_rules.yaml`` (resultado em cache).

    ``path`` opcional sobrescreve o caminho padrão (``config/audit_rules.yaml``).
    Em qualquer falha de leitura/parse retorna ``{}`` (log de erro). Resultado
    memoizado por ``lru_cache(maxsize=1)`` — o cache é por argumento, então uma
    chamada sem ``path`` e outra com ``path`` são entradas distintas.
    """
    rules_path = Path(path).resolve() if path else _RULES_PATH
    try:
        with open(rules_path, "r", encoding="utf-8") as file:
            payload = yaml.safe_load(file) or {}
    except Exception as exc:
        logger.error("Falha ao carregar regras de auditoria em %s: %s", rules_path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def get_password_rule_sectors() -> set[str]:
    """Conjunto (lowercase) de setores sujeitos à regra de senha (de ``password_rule_sectors``)."""
    return _as_text_set(load_audit_rules().get("password_rule_sectors"))


def get_rastreamento_sectors() -> set[str]:
    """Conjunto (lowercase) de setores de rastreamento (de ``rastreamento_sectors``)."""
    return _as_text_set(load_audit_rules().get("rastreamento_sectors"))


def get_password_criterion_keys() -> set[str]:
    """Conjunto (lowercase) de chaves de critério que representam a senha (de ``password_criterion_keys``)."""
    return _as_text_set(load_audit_rules().get("password_criterion_keys"))


def get_sector_prompt_rules(sector_id: Optional[str]) -> Optional[dict[str, str]]:
    """Regras de prompt específicas de um setor (de ``sector_prompt_rules``).

    Retorna ``None`` se ``sector_id`` for vazio ou não houver regra para ele.
    Quando há, retorna sempre um dict com as chaves ``label``, ``tipo_ligacao``
    e ``regras_zeragem`` (campos ausentes viram string vazia / o próprio
    ``sector_id`` no ``label``).
    """
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
    """Indica se a regra de senha se aplica ao setor.

    ATENÇÃO: setor vazio/ausente retorna ``True`` (regra aplica por padrão).
    Caso contrário, retorna ``True`` somente se o setor estiver em
    ``get_password_rule_sectors()``.
    """
    sector_key = str(sector_id or "").strip().lower()
    if not sector_key:
        return True
    return sector_key in get_password_rule_sectors()


def get_fatal_flag_sectors(flag: str) -> set[str]:
    """Setores (lowercase) afetados por uma fatal flag de zeragem.

    Lê ``fatal_flags[<flag>].sectors`` do YAML. Retorna ``set()`` se a flag não
    existir ou não tiver seção válida.
    """
    flags = load_audit_rules().get("fatal_flags")
    if not isinstance(flags, dict):
        return set()
    payload = flags.get(str(flag or "").strip())
    if not isinstance(payload, dict):
        return set()
    return _as_text_set(payload.get("sectors"))


def get_fatal_flag_reason_text(flag: str) -> str:
    """Texto-motivo da zeragem associado a uma fatal flag.

    Lê ``fatal_flags[<flag>].reason_text`` do YAML. Retorna string vazia se não
    houver flag/seção/texto.
    """
    flags = load_audit_rules().get("fatal_flags")
    if not isinstance(flags, dict):
        return ""
    payload = flags.get(str(flag or "").strip())
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("reason_text") or "").strip()


def get_fatal_keywords_for_sector(sector_id: Optional[str]) -> list[str]:
    """Lista (lowercase) de palavras-chave fatais configuradas para o setor.

    Lê ``fatal_keywords_by_sector[<sector_id>]`` do YAML. Retorna ``[]`` se não
    houver seção válida ou palavras para o setor.
    """
    sector_key = str(sector_id or "").strip().lower()
    rules = load_audit_rules().get("fatal_keywords_by_sector")
    if not isinstance(rules, dict):
        return []
    return _as_text_list(rules.get(sector_key))
