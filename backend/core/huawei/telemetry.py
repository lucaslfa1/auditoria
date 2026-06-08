from typing import Any, Optional, Dict, List, Callable
import logging

_PROCESS_DELTA_INT_KEYS = (
    "baixadas", "enfileiradas", "duplicadas", "ign_duracao", 
    "ign_operador", "ign_direcao", "ign_sem_recurso", "ign_erro",
    "ign_receptiva_risco", "ign_nativas", "tentativas_download", "operadores_considerados",
    "pretriagem_direcao_indefinida", "pretriagem_direcao_receptiva_descartadas",
    "pretriagem_direcao_ativa_aprovadas", "obs_primary_pulado_sem_record_id",
    "obs_primary_tentativas"
)

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
    if progress_callback is None:
        return
    try:
        progress_callback(stage, current, total)
    except Exception as exc:
        logger.debug("Sync Huawei: callback de progresso falhou: %s", exc)

def _increment_skip_counter(stats: dict, reason: Optional[str]) -> None:
    if not reason:
        return
    counter_key = _SKIP_REASON_COUNTERS.get(reason)
    if not counter_key:
        return
    stats[counter_key] = int(stats.get(counter_key, 0) or 0) + 1
    for extra_counter_key in _SKIP_REASON_EXTRA_COUNTERS.get(reason, ()):
        stats[extra_counter_key] = int(stats.get(extra_counter_key, 0) or 0) + 1

def _empty_process_delta() -> Dict[str, Any]:
    delta: Dict[str, Any] = {key: 0 for key in _PROCESS_DELTA_INT_KEYS}
    delta["erros"] = []
    return delta

def _is_direction_skip(reason: Optional[str]) -> bool:
    return reason in {
        "direction_mismatch",
        "direction_unknown",
        "risk_inbound",
        "receptiva_setor_desconhecido",
    }

