"""Configuração / tuning de runtime da esteira de automação.

Cluster coeso extraído de `core/automation.py` (v1.3.170) sem mudança de
comportamento: leitura de parâmetros e flags da esteira (meta/lote/timeout/
orçamento de tempo; flags de descarte e auditoria da esteira de dois estados
terminais; cota mensal) da tabela `configuracoes` e de env vars. Funções puras —
não tocam a fila, a IA nem o estado de progresso do ciclo.

Os nomes seguem reexportados de `core.automation` (callers internos
audit_all_pending/_audit_single_item, `routers/audit` e `routers/system` que
importam `_get_monthly_audit_quota`, e os patches de teste em
`core.automation.<nome>`). A config de disposição/retry vive em
`core/automation_disposition.py`.
"""
import logging
import os

import db.database as database

logger = logging.getLogger(__name__)


DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT = 3
DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS = 180


def _get_automation_item_timeout_seconds() -> int:
    """Timeout por item (segundos), clampado em [60, 900].

    Precedência: env `AUTOMATION_ITEM_TIMEOUT_SECONDS` > config no banco
    `automacao_item_timeout_seconds` > 480.
    """
    raw = os.getenv("AUTOMATION_ITEM_TIMEOUT_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value("automacao_item_timeout_seconds", "480")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 480
    return max(60, min(parsed, 900))


def _coerce_positive_int(value: object, default: int) -> int:
    """Converte para int >= 1; valor inválido vira `default`."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _read_config_value_with_fallback(keys: tuple[str, ...], default: str) -> str:
    """Lê a primeira config não vazia do banco entre `keys` (suporta chaves renomeadas/legadas)."""
    for key in keys:
        try:
            raw = database.get_config_value(key, "")
        except Exception as exc:
            logger.debug("Automacao: falha ao ler config %s: %s", key, exc)
            continue
        if raw not in (None, ""):
            return str(raw)
    return default


def _get_automation_audit_target_count() -> int:
    """Meta de auditorias por execução (quantos itens o lote tenta processar).

    Precedência: env `AUTOMATION_AUDIT_TARGET_COUNT` > env legada
    `AUTOMATION_AUDIT_BATCH_SIZE` > configs no banco > default 3.
    """
    raw = os.getenv("AUTOMATION_AUDIT_TARGET_COUNT")
    if raw in (None, ""):
        raw = os.getenv("AUTOMATION_AUDIT_BATCH_SIZE")
    if raw in (None, ""):
        raw = _read_config_value_with_fallback(
            ("automacao_audit_target_count", "automacao_audit_batch_size"),
            str(DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT),
        )
    return _coerce_positive_int(raw, DEFAULT_AUTOMATION_AUDIT_TARGET_COUNT)


def _get_automation_audit_batch_size() -> int:
    """Nome retrocompatível para a meta de auditorias configurada.

    A UI hoje grava uma META de auditorias; o runtime deriva lotes operacionais
    menores a partir do orçamento de tempo (`_derive_automation_audit_batch_size`)
    em vez de tratar este valor como tamanho de página da fila.
    """
    return _get_automation_audit_target_count()


def _get_automation_expected_audit_item_seconds() -> int:
    """Duração ESPERADA de um item (s, clamp [30, 900]) — usada só p/ dimensionar o lote."""
    raw = os.getenv("AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value(
            "automacao_expected_audit_item_seconds",
            str(DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS),
        )
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = DEFAULT_AUTOMATION_EXPECTED_AUDIT_ITEM_SECONDS
    return max(30, min(parsed, 900))


def _derive_automation_audit_batch_size(
    *,
    target_count: int,
    time_budget_seconds: int,
    item_timeout_seconds: int,
) -> int:
    """Tamanho do lote operacional: min(meta, quantos itens cabem no orçamento de tempo).

    Garante que um cron com orçamento curto não pegue mais itens do que
    consegue terminar (evita item iniciado e abortado no meio).
    """
    expected_item_seconds = min(
        _get_automation_expected_audit_item_seconds(),
        max(1, item_timeout_seconds),
    )
    budget_bound = max(1, int(time_budget_seconds) // expected_item_seconds)
    return max(1, min(int(target_count), budget_bound))


def _get_automation_audit_time_budget_seconds() -> int:
    """Orçamento de tempo TOTAL do lote (s, clamp [60, 1800]; default 480).

    Env `AUTOMATION_AUDIT_TIME_BUDGET_SECONDS` > config `automacao_audit_time_budget_seconds`.
    """
    raw = os.getenv("AUTOMATION_AUDIT_TIME_BUDGET_SECONDS")
    if raw in (None, ""):
        raw = database.get_config_value("automacao_audit_time_budget_seconds", "480")
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        parsed = 480
    return max(60, min(parsed, 1800))

def _config_flag(key: str) -> bool:
    """Lê uma flag booleana da tabela de config do banco ('true' literal = ligada)."""
    return str(database.get_config_value(key, "false") or "").strip().lower() == "true"


def _discard_unknown_alerts_enabled() -> bool:
    """Flag: item com alerta 'desconhecido' é descartado (tombstone) em vez de ir p/ triagem manual."""
    raw = os.getenv("AUTOMATION_DISCARD_UNKNOWN_ALERTS")
    if raw is None:
        return True  # default ON; rollback via AUTOMATION_DISCARD_UNKNOWN_ALERTS=false
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _audit_on_transcription_risk_enabled() -> bool:
    """Flag: audita mesmo com transcrição de qualidade arriscada (gate humano valida depois)."""
    raw = os.getenv("AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK")
    if raw is None:
        return True  # default ON; rollback via AUTOMATION_AUDIT_ON_TRANSCRIPTION_RISK=false
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_flag_default_on(name: str) -> bool:
    """Flag de env var com default ON (rollback setando =false). Padrao das flags da
    esteira de dois estados terminais (auditado | descartado)."""
    raw = os.getenv(name)
    if raw is None:
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _discard_blocked_operator_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_BLOCKED_OPERATOR")


def _audit_ignore_monthly_cap_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP")


def _discard_missing_sector_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_MISSING_SECTOR")


def _discard_no_criteria_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_NO_CRITERIA")


def _discard_non_telephony_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_NON_TELEPHONY")


def _discard_impossible_transcription_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_DISCARD_IMPOSSIBLE_TRANSCRIPTION")


def _transcription_failure_retry_enabled() -> bool:
    return _env_flag_default_on("AUTOMATION_TRANSCRIPTION_FAILURE_RETRY")

def _get_monthly_audit_quota() -> int:
    """Cota mensal de auditorias por operador (config `huawei_cota_max_por_operador_mes`, default 2).

    Obs.: com `AUTOMATION_AUDIT_IGNORE_MONTHLY_CAP` ON (default), a cota só é
    aplicada no ENVIO ao supervisor, não na auditoria automática.
    """
    raw = database.get_config_value("huawei_cota_max_por_operador_mes", "2")
    try:
        return max(1, int(str(raw or "2").strip()))
    except (TypeError, ValueError):
        logger.warning("Configuracao huawei_cota_max_por_operador_mes invalida: %r. Usando 2.", raw)
        return 2
