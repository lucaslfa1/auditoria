import os


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in _TRUE_VALUES


def allow_official_criteria_test_fallback() -> bool:
    """Allow legacy criteria fallbacks only when a test opts in explicitly."""

    return _env_truthy("AUDIT_ALLOW_OFFICIAL_CRITERIA_TEST_FALLBACK") and bool(
        os.getenv("PYTEST_CURRENT_TEST")
    )
