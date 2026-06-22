"""Triagem setorial dos candidatos do sync Huawei.

Agrupa as chamadas candidatas por setor (chaves de AUTOMATION_RULES) e aplica
a triagem hibrida de cada grupo: LLM, regras de motivo ou pass-through.
Codigo movido de core/huawei_sync.py sem alteracao de logica; os nomes
compartilhados/patchaveis resolvem em runtime via core.huawei_sync.

DISPARO: chamado por `core.huawei_sync.executar_sync_huawei` (Fase 1, via
`_aplicar_triagem_setorial`), ANTES do download — que por sua vez roda no cron de
automacao (pipeline D-1) ou nos scripts manuais de sync (huawei_manual_sync.py).
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _resolve_triagem_setor(interacao: dict) -> Optional[str]:
    """Retorna a chave de AUTOMATION_RULES correspondente ao operador
    da interação, ou None se não houver mapeamento confiável."""
    from core import huawei_sync as hs

    raw = (
        interacao.get("operatorSectorIdResolved")
        or interacao.get("operatorSectorResolved")
        or interacao.get("operator_sector_real")
        or ""
    )
    normalized = hs._normalize_setor_regra(str(raw)) if raw else None
    if normalized and normalized in hs.AUTOMATION_RULES:
        return normalized
    return None

def _triagem_fallback(grupo: list[dict]) -> list[dict]:
    """Fallback determinístico quando a LLM falha/está indisponível."""
    from core import huawei_sync as hs

    return sorted(grupo, key=hs.get_call_duration_seconds, reverse=True)[:2]

async def _aplicar_triagem_setorial(
    candidatas: list[dict],
    contadores: dict[str, Any],
    *,
    logger_local=logger,
) -> list[dict]:
    """Agrupa candidatos por setor e aplica triagem híbrida."""
    from core import huawei_sync as hs

    if not candidatas:
        return candidatas

    grupos: dict[Optional[str], list[dict]] = defaultdict(list)
    for cand in candidatas:
        grupos[hs._resolve_triagem_setor(cand)].append(cand)

    contadores.setdefault("triagem_por_setor", {})

    async def _triagem_grupo(setor: Optional[str], grupo: list[dict]) -> list[dict]:
        stats = {"input": len(grupo), "output": 0, "modo": "passthrough"}

        if setor is None:
            stats["modo"] = "setor_desconhecido_passthrough"
            logger_local.warning(
                "Triagem: %d candidatos sem setor resolvido — pass-through.",
                len(grupo),
            )
            stats["output"] = len(grupo)
            contadores["triagem_por_setor"]["_unknown"] = stats
            return grupo

        regra = hs.AUTOMATION_RULES.get(setor) or {}

        if regra.get("use_llm_triage"):
            stats["modo"] = "llm"
            grupo_filtrado = hs.filtrar_chamadas(grupo, regra)
            grupo = grupo_filtrado
            stats["pre_filtro_nativo"] = len(grupo)
            if not grupo:
                stats["output"] = 0
                contadores["triagem_por_setor"][setor] = stats
                return []
            try:
                aprovadas = await hs.filtrar_ligacoes_com_llm(grupo, setor, regra)
            except Exception:
                logger_local.exception(
                    "Triagem LLM falhou para setor=%s — aplicando fallback.",
                    setor,
                )
                aprovadas = []
            if not aprovadas:
                aprovadas = hs._triagem_fallback(grupo)
                stats["modo"] = "llm_fallback"
            stats["output"] = len(aprovadas)
            contadores["triagem_por_setor"][setor] = stats
            return aprovadas

        if regra.get("motivos_alvo"):
            stats["modo"] = "regras"
            aprovadas = hs.filtrar_chamadas(grupo, regra)
            stats["output"] = len(aprovadas)
            contadores["triagem_por_setor"][setor] = stats
            return aprovadas

        # Setor de Risco (sem IA, sem motivos): pass-through
        stats["output"] = len(grupo)
        contadores["triagem_por_setor"][setor] = stats
        return grupo

    # Triagem em paralelo entre setores
    resultados = await asyncio.gather(
        *[_triagem_grupo(s, g) for s, g in grupos.items()]
    )

    aprovadas_total: list[dict] = []
    for r in resultados:
        aprovadas_total.extend(r)

    aprovadas_total.sort(key=hs._download_candidate_sort_key, reverse=True)
    return aprovadas_total
