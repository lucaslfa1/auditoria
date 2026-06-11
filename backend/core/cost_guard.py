"""Guardrail de orcamento para APIs pagas (Azure OpenAI / Azure Speech).

Motivacao: em jun/2026 o orcamento Azure estourou porque o pipeline de
automacao rodava a cada 30 min com o motor de transcricao mais caro e ate 15
retries por item (ver docs/07-custos-e-guardrails.md). Este modulo garante
estruturalmente que o consumo diario tem teto, independente de configuracao
de cadencia ou engine.

Tres mecanismos, todos opt-out por env:

1. TETO DIARIO DE CHAMADAS LLM (`COST_MAX_LLM_CALLS_PER_DAY`, default 1500):
   conta toda chamada ao Azure OpenAI (classificacao, triagem, avaliacao,
   judge, transcricao premium...). Ao atingir o teto, `budget_exceeded()`
   passa a retornar o motivo e os pontos de entrada do pipeline param de
   processar itens NOVOS (itens ficam pendentes para o dia seguinte; nada
   e descartado).

2. TETO DIARIO DE AUDITORIAS (`COST_MAX_AUDITS_PER_DAY`, default 200):
   cada auditoria completa custa varias chamadas pagas (transcricao +
   avaliacao); este teto limita o pior caso mesmo se os contadores por
   chamada falharem.

3. KILL-SWITCH (`COST_KILL_SWITCH` env OU chave `cost_kill_switch` na tabela
   `configuracoes`): corta o consumo pago imediatamente, sem redeploy —
   basta um UPDATE no banco.

Persistencia: tabela `api_usage_daily` (data, provider, categoria, chamadas),
incrementada via UPSERT por `record_call()`. Leitura dos totais usa cache em
memoria com TTL para nao adicionar carga ao Postgres em loops quentes.

Filosofia de falha: FAIL-OPEN. Se o banco estiver indisponivel, o guard nao
bloqueia o pipeline (loga e segue) — indisponibilidade de telemetria nao pode
derrubar a operacao. O teto e uma protecao de custo, nao um controle critico
de seguranca.

Fuso: o "dia" segue o fuso do processo (TZ=America/Sao_Paulo no container).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Identificadores de provider usados em record_call(). Mantidos curtos e
# estaveis: viram chave primaria em api_usage_daily e rotulo na UI de status.
PROVIDER_AZURE_OPENAI = "azure_openai"
PROVIDER_AZURE_SPEECH = "azure_speech"
PROVIDER_PIPELINE = "pipeline"  # eventos internos (ex.: auditoria concluida)

# Categoria reservada para contar auditorias completas (1 por item auditado).
CATEGORIA_AUDITORIA = "auditoria"

DEFAULT_MAX_LLM_CALLS_PER_DAY = 1500
DEFAULT_MAX_AUDITS_PER_DAY = 200

# Cache do snapshot de uso do dia. TTL curto: o guard tolera ate
# _CACHE_TTL_SECONDS de atraso na detecao do teto (aceitavel — o teto e uma
# ordem de grandeza acima do uso normal), em troca de nao consultar o banco
# a cada item processado.
_CACHE_TTL_SECONDS = 20.0
_cache_lock = threading.Lock()
_usage_cache: dict = {"date": None, "loaded_at": 0.0, "rows": []}


class BudgetExceededError(RuntimeError):
    """Teto diario de consumo pago atingido (ver cost_guard.budget_exceeded)."""


# ---------------------------------------------------------------------------
# Leitura de limites (env primeiro, tabela configuracoes como fallback)
# ---------------------------------------------------------------------------

def _read_limit(env_name: str, config_key: str, default: int) -> int:
    """Le um teto numerico. Valor <= 0 desativa o teto correspondente."""
    raw = os.getenv(env_name)
    if raw in (None, ""):
        try:
            from db import database
            raw = database.get_config_value(config_key, "")
        except Exception as exc:  # noqa: BLE001 — fail-open
            logger.debug("cost_guard: falha ao ler config %s: %s", config_key, exc)
            raw = ""
    try:
        return int(str(raw).strip()) if str(raw).strip() else default
    except (TypeError, ValueError):
        return default


def get_max_llm_calls_per_day() -> int:
    return _read_limit(
        "COST_MAX_LLM_CALLS_PER_DAY", "cost_max_llm_calls_per_day",
        DEFAULT_MAX_LLM_CALLS_PER_DAY,
    )


def get_max_audits_per_day() -> int:
    return _read_limit(
        "COST_MAX_AUDITS_PER_DAY", "cost_max_audits_per_day",
        DEFAULT_MAX_AUDITS_PER_DAY,
    )


def kill_switch_active() -> bool:
    """Kill-switch de custo: env COST_KILL_SWITCH ou config cost_kill_switch.

    A via por banco permite cortar o consumo pago em producao com um simples
    UPDATE em `configuracoes`, sem redeploy nem acesso ao Cloud Run/Azure.
    """
    if (os.getenv("COST_KILL_SWITCH") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    try:
        from db import database
        raw = database.get_config_value("cost_kill_switch", "")
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("cost_guard: falha ao ler kill-switch do banco: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Contadores
# ---------------------------------------------------------------------------

def record_call(provider: str, categoria: str, n: int = 1) -> None:
    """Registra `n` chamadas pagas de uma categoria do pipeline.

    Chamado IMEDIATAMENTE ANTES de cada request a API paga (se o request
    falhar, a tentativa ja consumiu cota/risco de custo — contar a tentativa
    e o comportamento conservador correto).

    Nunca propaga excecao: telemetria não pode quebrar o pipeline.
    """
    if n <= 0:
        return
    try:
        from db.database import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO api_usage_daily (data, provider, categoria, chamadas, atualizado_em)
                VALUES (CURRENT_DATE, %s, %s, %s, NOW())
                ON CONFLICT (data, provider, categoria)
                DO UPDATE SET chamadas = api_usage_daily.chamadas + EXCLUDED.chamadas,
                              atualizado_em = NOW()
                """,
                (provider, categoria, n),
            )
            conn.commit()
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.warning("cost_guard: falha ao registrar uso %s/%s: %s", provider, categoria, exc)
        return
    # Mantem o cache coerente sem esperar o TTL expirar.
    with _cache_lock:
        if _usage_cache["date"] == date.today():
            for row in _usage_cache["rows"]:
                if row["provider"] == provider and row["categoria"] == categoria:
                    row["chamadas"] += n
                    break
            else:
                _usage_cache["rows"].append(
                    {"provider": provider, "categoria": categoria, "chamadas": n}
                )


def record_audit_completed() -> None:
    """Conta 1 auditoria concluida pela automacao (para o teto diario)."""
    record_call(PROVIDER_PIPELINE, CATEGORIA_AUDITORIA, 1)


def _load_today_rows() -> list[dict]:
    """Snapshot dos contadores do dia, com cache TTL (fail-open: [] em erro)."""
    today = date.today()
    now = time.monotonic()
    with _cache_lock:
        if (
            _usage_cache["date"] == today
            and (now - _usage_cache["loaded_at"]) < _CACHE_TTL_SECONDS
        ):
            return [dict(r) for r in _usage_cache["rows"]]
    try:
        from db.database import get_connection
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT provider, categoria, chamadas FROM api_usage_daily WHERE data = CURRENT_DATE"
            )
            rows = [
                {"provider": str(r[0]), "categoria": str(r[1]), "chamadas": int(r[2])}
                for r in cur.fetchall()
            ]
    except Exception as exc:  # noqa: BLE001 — fail-open
        logger.debug("cost_guard: falha ao ler api_usage_daily: %s", exc)
        return []
    with _cache_lock:
        _usage_cache["date"] = today
        _usage_cache["loaded_at"] = now
        _usage_cache["rows"] = [dict(r) for r in rows]
    return rows


def invalidate_cache() -> None:
    """Forca releitura do banco no proximo acesso (usado em testes)."""
    with _cache_lock:
        _usage_cache["date"] = None
        _usage_cache["loaded_at"] = 0.0
        _usage_cache["rows"] = []


def get_today_usage() -> dict:
    """Resumo do consumo do dia para o endpoint de status / health.

    Retorna totais, tetos vigentes e o motivo de bloqueio (se houver) — tudo
    que a UI precisa para mostrar "quanto do orcamento de hoje ja foi usado".
    """
    rows = _load_today_rows()
    total_llm = sum(r["chamadas"] for r in rows if r["provider"] == PROVIDER_AZURE_OPENAI)
    total_speech = sum(r["chamadas"] for r in rows if r["provider"] == PROVIDER_AZURE_SPEECH)
    total_audits = sum(
        r["chamadas"]
        for r in rows
        if r["provider"] == PROVIDER_PIPELINE and r["categoria"] == CATEGORIA_AUDITORIA
    )
    return {
        "data": date.today().isoformat(),
        "chamadas_llm": total_llm,
        "chamadas_speech": total_speech,
        "auditorias": total_audits,
        "por_categoria": {
            f"{r['provider']}/{r['categoria']}": r["chamadas"] for r in sorted(
                rows, key=lambda x: (x["provider"], x["categoria"])
            )
        },
        "limites": {
            "max_chamadas_llm_dia": get_max_llm_calls_per_day(),
            "max_auditorias_dia": get_max_audits_per_day(),
        },
        "kill_switch": kill_switch_active(),
        "bloqueado_motivo": budget_exceeded(),
    }


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def budget_exceeded() -> Optional[str]:
    """Retorna o motivo do bloqueio de consumo pago, ou None se liberado.

    Consultar no INICIO de cada unidade de trabalho paga (antes de classificar
    um item, antes de auditar um item) — nunca no meio de uma auditoria em
    andamento, para nao gerar artefato pela metade.
    """
    if kill_switch_active():
        return "kill_switch_ativo"

    rows = _load_today_rows()

    max_audits = get_max_audits_per_day()
    if max_audits > 0:
        total_audits = sum(
            r["chamadas"]
            for r in rows
            if r["provider"] == PROVIDER_PIPELINE and r["categoria"] == CATEGORIA_AUDITORIA
        )
        if total_audits >= max_audits:
            return f"teto_auditorias_dia_atingido ({total_audits}/{max_audits})"

    max_llm = get_max_llm_calls_per_day()
    if max_llm > 0:
        total_llm = sum(r["chamadas"] for r in rows if r["provider"] == PROVIDER_AZURE_OPENAI)
        if total_llm >= max_llm:
            return f"teto_chamadas_llm_dia_atingido ({total_llm}/{max_llm})"

    return None
