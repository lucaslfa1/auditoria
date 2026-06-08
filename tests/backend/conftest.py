import sys
import os

# Mantido por compatibilidade com testes que rodam o conftest isolado.
# A injecao canonica do backend/ no sys.path mora em tests/backend/__init__.py.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

import pytest

try:
    from core.classification import (
        load_audit_criteria_catalog,
        build_sectors_and_alerts_prompt,
        get_alert_lookup_by_id,
    )
except ImportError:
    load_audit_criteria_catalog = None
    build_sectors_and_alerts_prompt = None
    get_alert_lookup_by_id = None

try:
    from core.config import _load_json_config
except ImportError:
    _load_json_config = None

try:
    from core.export_gestores import _load_pesos_from_path
except ImportError:
    _load_pesos_from_path = None

try:
    from core.gestores_mapping import (
        get_gestores_alert_catalog,
        get_gestores_alert_label_lookup,
    )
except ImportError:
    get_gestores_alert_catalog = None
    get_gestores_alert_label_lookup = None

try:
    from core.procedimentos_rag import load_procedimento_sections
except ImportError:
    load_procedimento_sections = None

@pytest.fixture(autouse=True)
def clear_lru_caches():
    """Limpa todos os lru_caches para evitar poluição entre os testes."""
    if load_audit_criteria_catalog and hasattr(load_audit_criteria_catalog, "cache_clear"):
        load_audit_criteria_catalog.cache_clear()
    if build_sectors_and_alerts_prompt and hasattr(build_sectors_and_alerts_prompt, "cache_clear"):
        build_sectors_and_alerts_prompt.cache_clear()
    if get_alert_lookup_by_id and hasattr(get_alert_lookup_by_id, "cache_clear"):
        get_alert_lookup_by_id.cache_clear()
    if _load_json_config and hasattr(_load_json_config, "cache_clear"):
        _load_json_config.cache_clear()
    if _load_pesos_from_path and hasattr(_load_pesos_from_path, "cache_clear"):
        _load_pesos_from_path.cache_clear()
    if get_gestores_alert_catalog and hasattr(get_gestores_alert_catalog, "cache_clear"):
        get_gestores_alert_catalog.cache_clear()
    if get_gestores_alert_label_lookup and hasattr(get_gestores_alert_label_lookup, "cache_clear"):
        get_gestores_alert_label_lookup.cache_clear()
    if load_procedimento_sections and hasattr(load_procedimento_sections, "cache_clear"):
        load_procedimento_sections.cache_clear()
    yield


def pytest_configure(config):
    """Guard: recusa rodar a suite contra o banco de PRODUCAO.

    Varios testes escrevem no banco (fila de revisao, huawei_sync_logs, etc.). Se a
    DATABASE_URL apontar para o Neon de producao (host ep-aged-river), esses testes poluem
    dados reais — foi assim que um item de teste ('Operador Teste', id reusado de operador
    real) vazou para a fila de producao. Aponte DATABASE_URL para um banco de teste, ou,
    conscientemente, defina ALLOW_TESTS_ON_PROD_DB=1.
    """
    db_url = os.getenv("DATABASE_URL", "") or ""
    if not db_url:
        # pytest_configure roda antes dos testes importarem o app; carrega o .env do projeto.
        try:
            from dotenv import load_dotenv
            here = os.path.dirname(os.path.abspath(__file__))
            for candidate in (
                os.path.join(here, "..", "..", "backend", ".env"),
                os.path.join(here, "..", "..", ".env"),
            ):
                if os.path.exists(candidate):
                    load_dotenv(candidate, override=False)
            db_url = os.getenv("DATABASE_URL", "") or ""
        except Exception:
            pass
    if "ep-aged-river" in db_url and os.getenv("ALLOW_TESTS_ON_PROD_DB") != "1":
        raise pytest.UsageError(
            "Suite BLOQUEADA: DATABASE_URL aponta para o banco de PRODUCAO (ep-aged-river). "
            "Testes escrevem no banco e poluiriam producao. Use um banco de teste (branch "
            "Neon ou local) ou, conscientemente, defina ALLOW_TESTS_ON_PROD_DB=1."
        )
