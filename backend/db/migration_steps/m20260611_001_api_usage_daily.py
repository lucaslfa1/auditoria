"""Contadores diarios de chamadas a APIs pagas (guardrail de orcamento).

Tabela alimentada por core/cost_guard.py: cada chamada a Azure OpenAI /
Azure Speech incrementa (data, provider, categoria). Serve a dois fins:
1. Teto de orcamento: cost_guard.budget_exceeded() compara os totais do dia
   com COST_MAX_LLM_CALLS_PER_DAY / COST_MAX_AUDITS_PER_DAY.
2. Telemetria: visibilidade de quantas chamadas pagas cada etapa do pipeline
   (classificacao, triagem, transcricao, avaliacao...) gerou por dia.
"""
from __future__ import annotations

MIGRATION_NAME = "m20260611_001_api_usage_daily"


def apply(c) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS api_usage_daily (
            data DATE NOT NULL,
            provider TEXT NOT NULL,
            categoria TEXT NOT NULL,
            chamadas INTEGER NOT NULL DEFAULT 0,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (data, provider, categoria)
        )
        """
    )
