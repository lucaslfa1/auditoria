"""Diagnostico SOMENTE-LEITURA do estado da auditoria automatica.

Responde: a auditoria automatica voltou a funcionar apos v1.3.98-1.3.100?

Le (sem escrever nada):
1) Configs de automacao (budget/item_timeout/batch) — confirma se 1500/600/10 valem.
2) Ultimos ciclos (automation_cycle_runs) — completed vs timeout, e qual
   time_budget_seconds estava em efeito (confirma se o deploy/config pegou).
3) Distribuicao de status na fila_revisao_classificacao.
4) Veredito automatico.

Uso: python scripts/diagnose_auto_audit_state.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402


def _section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _as_dict(value):
    """audit_result/sync_result vem como dict (psycopg2 jsonb) ou str."""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}


def main() -> None:
    conn = database.get_connection()
    try:
        cur = conn.cursor()

        _section("0) Identidade do banco conectado (via .env DATABASE_URL)")
        cur.execute("SELECT current_database() AS db, current_user AS usr, inet_server_addr() AS host")
        ident = cur.fetchone()
        print(f"  database={ident['db']}  user={ident['usr']}  host={ident['host']}")
        cur.execute("SELECT COUNT(*) n, MIN(started_at) mn, MAX(started_at) mx FROM automation_cycle_runs")
        c = cur.fetchone()
        print(f"  automation_cycle_runs: {c['n']} ciclos, de {c['mn']} ate {c['mx']}")
        cur.execute("SELECT COUNT(*) n FROM automation_cycle_runs WHERE started_at >= '2026-05-27'")
        print(f"  ciclos desde 2026-05-27 (trabalho de ontem): {cur.fetchone()['n']}")
        cur.execute(
            "SELECT chave FROM configuracoes WHERE chave IN "
            "('automacao_audit_time_budget_seconds','automacao_item_timeout_seconds','automacao_audit_batch_size')"
        )
        keys = [r["chave"] for r in cur.fetchall()]
        print(f"  configs budget/item/batch presentes: {keys or 'NENHUMA (esperadas 3 do 1.3.100)'}")

        _section("1) Configs de automacao (esperado pos-1.3.100: budget=1500, item=600, batch=10)")
        cur.execute(
            """
            SELECT chave, valor, atualizado_em AS atualizado_brt
            FROM configuracoes
            WHERE chave LIKE 'automacao%'
               OR chave IN ('robo_habilitado')
            ORDER BY chave
            """
        )
        configs = {}
        for r in cur.fetchall():
            configs[r["chave"]] = r["valor"]
            print(f"  {r['chave']:45s} = {str(r['valor']):8s}  (atualizado {r['atualizado_brt']})")

        _section("2) Ultimos 15 ciclos de automacao")
        cur.execute(
            """
            SELECT id, source, status, stage,
                   started_at  AT TIME ZONE 'America/Sao_Paulo' AS started_brt,
                   finished_at AT TIME ZONE 'America/Sao_Paulo' AS finished_brt,
                   baixadas, auditadas, audit_result, error_message
            FROM automation_cycle_runs
            ORDER BY started_at DESC
            LIMIT 15
            """
        )
        rows = cur.fetchall()
        print(f"{'id':>5} {'inicio (BRT)':16} {'status':10} {'stage':26} {'baix':>4} {'audit':>5} {'budget':>6} {'compl':>5} {'errs':>4}")
        print("-" * 100)
        recent_completed = 0
        recent_timeouts = 0
        budgets_seen = set()
        for r in rows:
            ar = _as_dict(r["audit_result"])
            budget = ar.get("time_budget_seconds", "-")
            completed = ar.get("completed", "-")
            errors = ar.get("errors") or []
            n_errs = len(errors) if isinstance(errors, list) else "-"
            if isinstance(budget, (int, float)):
                budgets_seen.add(int(budget))
            if isinstance(completed, int):
                recent_completed += completed
            timeout_here = any("timeout" in str(e).lower() for e in errors) if isinstance(errors, list) else False
            if timeout_here:
                recent_timeouts += 1
            started = str(r["started_brt"])[:16]
            print(f"{r['id']:>5} {started:16} {str(r['status']):10} {str(r['stage'])[:26]:26} "
                  f"{r['baixadas']:>4} {r['auditadas']:>5} {str(budget):>6} {str(completed):>5} {str(n_errs):>4}")

        # Mostra os erros do ciclo mais recente que teve erro
        for r in rows:
            ar = _as_dict(r["audit_result"])
            errors = ar.get("errors") or []
            if errors:
                print(f"\n  Erros do ciclo {r['id']} (mais recente com erro):")
                for e in (errors if isinstance(errors, list) else [errors])[:6]:
                    print(f"    - {str(e)[:160]}")
                break

        _section("3) Distribuicao de status na fila")
        cur.execute(
            "SELECT status, COUNT(*) qtd FROM fila_revisao_classificacao GROUP BY status ORDER BY qtd DESC"
        )
        fila = {r["status"]: r["qtd"] for r in cur.fetchall()}
        for status, qtd in fila.items():
            print(f"  {qtd:5d}  {status}")

        _section("VEREDITO")
        budget_cfg = configs.get("automacao_audit_time_budget_seconds")
        item_cfg = configs.get("automacao_item_timeout_seconds")
        batch_cfg = configs.get("automacao_audit_batch_size")
        print(f"  Configs no DB: budget={budget_cfg} (esperado 1500), item={item_cfg} (esperado 600), batch={batch_cfg} (esperado 10)")
        print(f"  time_budget_seconds visto nos ciclos recentes: {sorted(budgets_seen) or '(nenhum ciclo com audit_result)'}")
        print(f"  Total auditadas nos ultimos 15 ciclos: {recent_completed}")
        print(f"  Ciclos recentes com timeout: {recent_timeouts}")
        if 1500 in budgets_seen:
            print("  >> Deploy 1.3.100 CONFIRMADO em producao (budget 1500 ativo nos ciclos).")
        elif budgets_seen:
            print(f"  >> ATENCAO: ciclos ainda rodando com budget {sorted(budgets_seen)} != 1500 -> deploy/config NAO pegou.")
        else:
            print("  >> Nenhum ciclo recente com audit_result — sem dado pos-deploy ainda.")
        if recent_completed > 0 and recent_timeouts == 0:
            print("  >> Auditoria automatica parece SAUDAVEL (completando, sem timeout).")
        elif recent_completed > 0:
            print("  >> PARCIAL: algumas completam mas ainda ha timeouts.")
        else:
            print("  >> AINDA QUEBRADA: 0 auditadas nos ciclos recentes.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
