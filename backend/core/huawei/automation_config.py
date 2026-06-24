"""Configuração / credenciais / tuning de runtime do sync Huawei.

Cluster coeso extraído de `core/huawei_sync.py` (v1.3.169) sem mudança de
comportamento: leitura de credenciais (`_load_config`/`_missing_credentials`),
flags de env e limites/concorrência da esteira (downloads, duração, confiança de
auto-auditoria) lidos da tabela `configuracoes` ou de env vars. Funções puras que
NÃO tocam cliente Huawei/OBS, fila nem o estado do orquestrador.

Os nomes seguem reexportados de `core.huawei_sync` (callers internos,
`core/huawei/sync_classification.py` via `hs.<nome>`, `huawei_d_minus_1` e ~10
scripts importam `from core.huawei_sync import _load_config`). ATENÇÃO: `_env_flag`
aqui tem semântica Huawei (Optional[bool], default None) — não confundir com
`core.config._env_flag` (bool, default False).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import db.database as database
from core.huawei_client import OAUTH_DIRECT_MODES

logger = logging.getLogger(__name__)


DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT = 20
# Teto FIXO de downloads por ciclo de sync, independente da meta de auditorias.
# O numero efetivo de downloads segue a meta (automacao_audit_target_count), mas
# nunca ultrapassa este teto — trava de seguranca contra coleta descontrolada.
HUAWEI_SYNC_DOWNLOAD_HARD_CEILING = 500
DEFAULT_HUAWEI_SYNC_MIN_DURATION_SECONDS = 120
DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS = 0
DEFAULT_HUAWEI_SYNC_DOWNLOAD_CONCURRENCY = 5
DEFAULT_HUAWEI_SYNC_CLASSIFY_CONCURRENCY = 5
DEFAULT_HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD = 0.90
# Teto de downloads do MESMO operador por ciclo de sync. DESACOPLADO da cota de
# compliance `huawei_cota_max_por_operador_mes` (2/operador/mes, que governa SO o
# envio ao supervisor). Objetivo: o volume baixado se aproximar da meta sem ficar
# preso em 2/operador. 0 = ilimitado (segue so a meta + rodizio por setor).
DEFAULT_HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO = 10

# Linhas fixas da CENTRAL (47 3481-6122 / 47 2101-6122 e ramais do mesmo bloco),
# usadas para inferir a direção de ligações que vêm sem `isCallIn` (manifesto OBS).
DEFAULT_HUAWEI_CENTRAL_NUMBERS = (
    "4734816122,4721016122,4734816171,4734816142,4721016142"
)


def get_huawei_central_numbers() -> set:
    """Números (só dígitos) das linhas da CENTRAL para inferir direção.

    Override por env `HUAWEI_CENTRAL_NUMBERS` ou config `huawei_central_numbers`
    (lista separada por vírgula); senão usa `DEFAULT_HUAWEI_CENTRAL_NUMBERS`.
    Efeito colateral: leitura de banco/env.
    """
    raw = os.getenv("HUAWEI_CENTRAL_NUMBERS")
    if raw in (None, ""):
        try:
            raw = database.get_config_value("huawei_central_numbers", "")
        except Exception as exc:
            logger.debug("Sync Huawei: falha ao ler huawei_central_numbers: %s", exc)
            raw = ""
    if raw in (None, ""):
        raw = DEFAULT_HUAWEI_CENTRAL_NUMBERS
    numeros: set = set()
    for parte in str(raw).split(","):
        digitos = re.sub(r"\D+", "", parte)
        if digitos:
            numeros.add(digitos)
    return numeros


def _ensure_enabled() -> bool:
    return (os.getenv("ENABLE_HUAWEI_SYNC", "false") or "").strip().lower() == "true"

def _load_config() -> Dict[str, Any]:
    """Le AK/SK/CCID/VDN/App Key da tabela configuracoes.

    Env vars funcionam como override local (`HUAWEI_AK`, etc.).
    """

    def read(key: str) -> str:
        env_key = f"HUAWEI_{key.upper()}"
        if os.getenv(env_key):
            return str(os.getenv(env_key)).strip()
        return str(database.get_config_value(f"huawei_{key}", "") or "").strip()

    cfg = {
        "cms_url": read("cms_url") or read("portal_url"),
        "fs_url": read("fs_url"),
        "cc_id": read("ccid") or read("cc_id"),
        "vdn": read("vdn"),
        "ak": read("ak"),
        "sk": read("sk"),
        "app_key": read("app_key"),
        "app_secret": read("app_secret"),
        "proxy_url": read("proxy_url"),
        "auth_mode": read("auth_mode"),
        # OAuth direct (modo `oauth_direct`): credenciais isoladas do proxy
        # Teledata para o tokenByAkSk + cabecalho X-TenantSpaceID.
        "auth_base_url": read("auth_base_url"),
        "tenant_space_id": read("tenant_space_id"),
        "direct_app_key": read("direct_app_key"),
        "direct_app_secret": read("direct_app_secret"),
        # Credenciais OBS (fallback direto no bucket quando CC-FS retorna 0300012).
        # Lidas do mesmo padrao: env HUAWEI_OBS_* ou tabela configuracoes huawei_obs_*.
        "obs_ak": read("obs_ak"),
        "obs_sk": read("obs_sk"),
        "obs_bucket": read("obs_bucket"),
        "obs_endpoint": read("obs_endpoint"),
    }
        
    return cfg

def _missing_credentials(cfg: Dict[str, Any]) -> List[str]:
    """Lista quais credenciais obrigatorias estao faltando, conforme o auth_mode.

    Em modos OAuth direto (`OAUTH_DIRECT_MODES`) exige cc_id, vdn, direct_app_key
    e direct_app_secret; nos demais (proxy) exige ak, sk, cc_id e vdn. Retorna a
    lista vazia quando esta tudo presente. Funcao pura sobre o dict de `_load_config`.
    """
    auth_mode = str(cfg.get("auth_mode") or "proxy").strip().lower()
    if auth_mode in OAUTH_DIRECT_MODES:
        obrigatorios = ["cc_id", "vdn", "direct_app_key", "direct_app_secret"]
    else:
        obrigatorios = ["ak", "sk", "cc_id", "vdn"]
    return [k for k in obrigatorios if not cfg.get(k)]


def _get_duration_limits_for_sector(
    raw_setor: str,
    default_min: int,
    default_max: int = DEFAULT_HUAWEI_SYNC_MAX_DURATION_SECONDS,
) -> tuple[int, int]:
    # A coleta de ligacoes deve ser ampla; setor nao deve bloquear download.
    _ = raw_setor
    return max(0, default_min), max(0, default_max)

def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default

def _runtime_int_config(env_key: str, db_keys: tuple[str, ...], default: int) -> int:
    """Le um inteiro de runtime: env var primeiro, depois tabela configuracoes.

    Tenta `env_key`; se vazio, percorre `db_keys` na ordem chamando
    `database.get_config_value` e usa o primeiro valor presente. Falhas de leitura
    do banco sao logadas em debug e ignoradas (passa para a proxima chave).
    Retorna `default` se nada for encontrado. Efeito colateral: leitura de banco.
    """
    raw = os.getenv(env_key)
    if raw not in (None, ""):
        return _coerce_int(raw, default)

    for key in db_keys:
        try:
            raw = database.get_config_value(key, "")
        except Exception as exc:
            logger.debug("Sync Huawei: falha ao ler config %s: %s", key, exc)
            continue
        if raw not in (None, ""):
            return _coerce_int(raw, default)

    return default


def _effective_download_attempt_limit() -> int:
    """Quantos downloads tentar por ciclo de sync (clamp [1, HUAWEI_SYNC_DOWNLOAD_HARD_CEILING]).

    O numero EFETIVO segue a META de auditorias do ciclo (downloads = meta, 1:1),
    lida de env (`AUTOMATION_AUDIT_TARGET_COUNT` / `AUTOMATION_AUDIT_BATCH_SIZE`) ou
    da tabela configuracoes (`automacao_audit_target_count` /
    `automacao_audit_batch_size`), com override explicito por
    `HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS`. Em TODOS os casos o resultado e limitado ao
    teto fixo `HUAWEI_SYNC_DOWNLOAD_HARD_CEILING` (500): a meta governa o volume, o
    teto e so a trava de seguranca. Efeito colateral: leitura de banco/env. Default
    `DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT` quando nada esta configurado.
    """
    explicit_download_limit = os.getenv("HUAWEI_SYNC_MAX_DOWNLOAD_ATTEMPTS")
    if explicit_download_limit not in (None, ""):
        return max(
            1,
            min(
                HUAWEI_SYNC_DOWNLOAD_HARD_CEILING,
                _coerce_int(explicit_download_limit, DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT),
            ),
        )

    # Opção 1 (downloads = meta): o número de downloads por ciclo passa a ser a
    # própria meta de auditorias. O antigo `huawei_d1_limite_ligacoes` deixou de
    # ser um controle separado — era redundante, pois o efetivo já era
    # max(limite_downloads, meta). Agora vale só a meta (1:1).
    raw_audit_target = os.getenv("AUTOMATION_AUDIT_TARGET_COUNT") or os.getenv("AUTOMATION_AUDIT_BATCH_SIZE")
    if raw_audit_target in (None, ""):
        raw_audit_target = ""
        for key in ("automacao_audit_target_count", "automacao_audit_batch_size"):
            try:
                raw_audit_target = database.get_config_value(key, "")
            except Exception as exc:
                logger.debug("Sync Huawei: falha ao ler config %s: %s", key, exc)
                continue
            if raw_audit_target not in (None, ""):
                break
    return max(
        1,
        min(
            HUAWEI_SYNC_DOWNLOAD_HARD_CEILING,
            _coerce_int(raw_audit_target, DEFAULT_HUAWEI_SYNC_DOWNLOAD_LIMIT),
        ),
    )


def _download_max_por_operador_ciclo() -> int:
    """Teto de downloads do MESMO operador por ciclo (>= 0; 0 = ilimitado).

    Lido de env `HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO` ou config
    `huawei_download_max_por_operador_ciclo` (default
    `DEFAULT_HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO` = 10). DESACOPLADO de
    `huawei_cota_max_por_operador_mes` (cota de compliance do supervisor, 2/mes):
    mexer neste teto NAO altera a regra de envio ao supervisor. Efeito colateral:
    leitura de banco/env.
    """
    valor = _runtime_int_config(
        "HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO",
        ("huawei_download_max_por_operador_ciclo",),
        DEFAULT_HUAWEI_DOWNLOAD_MAX_POR_OPERADOR_CICLO,
    )
    return max(0, valor)


def _runtime_float_config(env_key: str, db_keys: tuple[str, ...], default: float) -> float:
    """Versao float de `_runtime_int_config`: env var primeiro, depois banco.

    Mesma logica de precedencia e tolerancia a falhas; retorna `default` se nada
    for encontrado. Efeito colateral: leitura de banco.
    """
    raw = os.getenv(env_key)
    if raw not in (None, ""):
        return _coerce_float(raw, default)

    for key in db_keys:
        try:
            raw = database.get_config_value(key, "")
        except Exception as exc:
            logger.debug("Sync Huawei: falha ao ler config %s: %s", key, exc)
            continue
        if raw not in (None, ""):
            return _coerce_float(raw, default)

    return default


def _get_huawei_auto_audit_confidence_threshold() -> float:
    """Limiar de confianca [0.0, 1.0] para auto-auditar sem revisao humana.

    Le de env/banco via `_runtime_float_config` (default
    `DEFAULT_HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD` = 0.90) e faz clamp no
    intervalo [0.0, 1.0]. Efeito colateral: leitura de banco.
    """
    threshold = _runtime_float_config(
        "HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD",
        ("huawei_auto_audit_confidence_threshold",),
        DEFAULT_HUAWEI_AUTO_AUDIT_CONFIDENCE_THRESHOLD,
    )
    return min(1.0, max(0.0, threshold))

def _env_flag(name: str, default: Optional[bool] = None) -> Optional[bool]:
    """Le uma flag booleana de env com semantica Huawei (tri-state).

    Retorna `default` (por padrao None = "nao definido") quando a env var nao
    existe; caso contrario, True se o valor for "1/true/yes/on", senao False.

    ATENCAO: difere de `core.config._env_flag`, que e bool com default False. Aqui
    o Optional/None e proposital para distinguir "nao configurado" de "False".
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}

def _should_run_auto_classification_after_sync() -> bool:
    """Controls the expensive Telefonia-side alert classifier.

    Default is disabled: Huawei sync should download/enqueue and let the
    triage module classify alerts. Legacy HUAWEI_SYNC_SKIP_CLASSIFY is still
    honored when explicitly set so existing deployments can roll back quickly.
    """
    explicit_enable = _env_flag("HUAWEI_SYNC_ENABLE_CLASSIFY", None)
    if explicit_enable is not None:
        return explicit_enable

    legacy_skip = _env_flag("HUAWEI_SYNC_SKIP_CLASSIFY", None)
    if legacy_skip is not None:
        return not legacy_skip

    return False
