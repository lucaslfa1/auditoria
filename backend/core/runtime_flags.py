"""Flags de runtime lidas de variáveis de ambiente.

Papel no sistema: centraliza pequenas decisões de comportamento controladas por
env. Hoje expõe apenas o gate que libera, exclusivamente em testes, fallbacks
legados de critérios oficiais.

Sem custo de API: só lê `os.environ` (CPU). Não chama Azure, banco nem rede.
"""

import os


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_truthy(name: str) -> bool:
    """Retorna True se a env `name` tiver valor verdadeiro ("1/true/yes/on")."""
    return str(os.getenv(name, "")).strip().lower() in _TRUE_VALUES


def allow_official_criteria_test_fallback() -> bool:
    """Allow legacy criteria fallbacks only when a test opts in explicitly."""

    return _env_truthy("AUDIT_ALLOW_OFFICIAL_CRITERIA_TEST_FALLBACK") and bool(
        os.getenv("PYTEST_CURRENT_TEST")
    )
