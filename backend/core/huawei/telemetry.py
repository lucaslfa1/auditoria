"""Telemetria/contadores do sync Huawei (estatísticas de processamento).

Reúne os helpers que alimentam o dicionário de `stats` retornado pelo sync:
notificação de progresso, mapeamento de motivos de descarte para contadores e
o "delta" zerado de cada lote de processamento. Extraído de `core.huawei_sync`,
que reexporta `_notify_progress`, `_increment_skip_counter`,
`_empty_process_delta` e `_is_direction_skip` para compat.

Sem custo de API (só CPU/estruturas em memória; nenhuma chamada a banco ou
rede). As chaves dos contadores (`baixadas`, `ignoradas_*`, etc.) são contrato
de telemetria consumido por UI/relatórios — NÃO renomear.
"""

from typing import Any, Optional, Dict, List, Callable
import logging

# Chaves inteiras do "delta" de cada lote (todas começam zeradas). São o
# contrato de telemetria por execução; não renomear sem alinhar com quem lê.
_PROCESS_DELTA_INT_KEYS = (
    "baixadas", "enfileiradas", "duplicadas", "ign_duracao", 
    "ign_operador", "ign_direcao", "ign_sem_recurso", "ign_erro",
    "ign_receptiva_risco", "ign_nativas", "tentativas_download", "operadores_considerados",
    "pretriagem_direcao_indefinida", "pretriagem_direcao_receptiva_descartadas",
    "pretriagem_direcao_ativa_aprovadas", "obs_primary_pulado_sem_record_id",
    "obs_primary_tentativas"
)

# Mapeia o `reason` (motivo de descarte vindo do pipeline) para a chave do
# contador que deve ser incrementada em `stats`. Vários motivos podem apontar
# para o mesmo contador (ex.: 'operator_not_registered' e
# 'operator_huawei_not_registered').
_SKIP_REASON_COUNTERS = {
    "mondelez": "ignoradas_mondelez",
    "operator_not_registered": "ignoradas_operador_huawei_nao_cadastrado",
    "direction_mismatch": "ignoradas_direcao_incompativel",
    "direction_unknown": "ignoradas_direcao_desconhecida",
    "risk_inbound": "ignoradas_receptiva_setor_risco",
    "non_telefonia_sector": "ignoradas_setor_nao_telefonia",
    "receptiva_setor_desconhecido": "ignoradas_receptiva_setor_desconhecido",
    "operator_huawei_not_registered": "ignoradas_operador_huawei_nao_cadastrado",
}
# Contadores ADICIONAIS incrementados junto com o principal: alguns motivos
# contam em duas estatísticas ao mesmo tempo (ex.: uma receptiva em setor de
# risco também entra como "direção incompatível").
_SKIP_REASON_EXTRA_COUNTERS = {
    "risk_inbound": ("ignoradas_direcao_incompativel",),
    "receptiva_setor_desconhecido": ("ignoradas_direcao_incompativel",),
}

logger = logging.getLogger(__name__)

def _notify_progress(
    progress_callback: Optional[Callable[[str, int, int], None]],
    stage: str,
    current: int,
    total: int,
) -> None:
    """Invoca o callback de progresso, se houver, sem deixar erro vazar.

    `progress_callback` recebe (stage, current, total). Se for None, não faz
    nada. Qualquer exceção do callback é apenas logada em debug — o progresso
    nunca deve derrubar o sync.
    """
    if progress_callback is None:
        return
    try:
        progress_callback(stage, current, total)
    except Exception as exc:
        logger.debug("Sync Huawei: callback de progresso falhou: %s", exc)

def _increment_skip_counter(stats: dict, reason: Optional[str]) -> None:
    """Incrementa em `stats` o(s) contador(es) associados a um motivo de descarte.

    Resolve `reason` via `_SKIP_REASON_COUNTERS` (principal) e
    `_SKIP_REASON_EXTRA_COUNTERS` (adicionais). Motivo None/vazio ou
    desconhecido é ignorado (no-op). Muta `stats` no lugar (+1 por contador).
    """
    if not reason:
        return
    counter_key = _SKIP_REASON_COUNTERS.get(reason)
    if not counter_key:
        return
    stats[counter_key] = int(stats.get(counter_key, 0) or 0) + 1
    for extra_counter_key in _SKIP_REASON_EXTRA_COUNTERS.get(reason, ()):
        stats[extra_counter_key] = int(stats.get(extra_counter_key, 0) or 0) + 1

def _empty_process_delta() -> Dict[str, Any]:
    """Cria o dicionário de delta de um lote com todos os inteiros zerados.

    Todas as chaves de `_PROCESS_DELTA_INT_KEYS` começam em 0 e adiciona uma
    lista vazia `erros`. Usado pelo sync como acumulador por lote.
    """
    delta: Dict[str, Any] = {key: 0 for key in _PROCESS_DELTA_INT_KEYS}
    delta["erros"] = []
    return delta

def _is_direction_skip(reason: Optional[str]) -> bool:
    """True se o motivo de descarte é relacionado à direção da chamada.

    Agrupa os motivos ligados a direção (mismatch, desconhecida, receptiva em
    setor de risco/desconhecido) para o sync tratá-los em conjunto.
    """
    return reason in {
        "direction_mismatch",
        "direction_unknown",
        "risk_inbound",
        "receptiva_setor_desconhecido",
    }

