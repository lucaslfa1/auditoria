"""Identifica QUAL caminho do codigo produz huawei_begin_time com +3h offset.

A query #3 do diagnostico anterior mostrou que 50% dos itens tem diff=+3h.
Esta segunda etapa cruza essa informacao com:
- metadata.origem (huawei_sync vs manual)
- metadata.is_manual
- metadata.fix_timezone_applied (foi tocado pelos scripts de rescue?)
- horario do dia em que foi criado (pode ser cron especifico)
- agent_id (algum agente tem padrao especifico)
"""
from __future__ import annotations

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

import psycopg2  # noqa: E402
from psycopg2.extras import RealDictCursor  # noqa: E402


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERRO: DATABASE_URL nao encontrada")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute(
        """
        SELECT
          metadata_json::jsonb->>'huawei_call_id' AS call_id,
          (metadata_json::jsonb->>'huawei_begin_time')::bigint AS begin_time_ms,
          split_part(metadata_json::jsonb->>'huawei_call_id', '-', 1)::bigint * 1000 AS call_id_epoch_ms,
          ROUND(
            ((metadata_json::jsonb->>'huawei_begin_time')::bigint
             - split_part(metadata_json::jsonb->>'huawei_call_id', '-', 1)::bigint * 1000)
            / 3600000.0,
            2
          ) AS diff_horas,
          metadata_json::jsonb->>'origem' AS origem,
          metadata_json::jsonb->>'is_manual' AS is_manual,
          metadata_json::jsonb->>'fix_timezone_applied' AS ja_corrigido,
          metadata_json::jsonb->>'huawei_agent_id' AS agent_id,
          metadata_json::jsonb->>'operator_name' AS operator,
          metadata_json::jsonb->>'classification_status' AS class_status,
          metadata_json::jsonb->>'source_type' AS source_type,
          status,
          criado_em::timestamptz AS criado_em
        FROM fila_revisao_classificacao
        WHERE metadata_json::jsonb->>'huawei_call_id' ~ '^[0-9]+-'
          AND metadata_json::jsonb->>'huawei_begin_time' ~ '^[0-9]+$'
          AND criado_em::timestamptz >= NOW() - INTERVAL '14 days'
        ORDER BY criado_em::timestamptz DESC
        LIMIT 500
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("Nenhum item encontrado.")
        return

    # Classifica cada item
    bugados = []
    corretos = []
    outros = []
    for r in rows:
        d = float(r["diff_horas"]) if r["diff_horas"] is not None else None
        if d is None:
            continue
        if abs(d) < 0.5:
            corretos.append(r)
        elif 2.5 < abs(d) < 3.5:
            bugados.append(r)
        else:
            outros.append(r)

    _section(f"Comparativo: {len(corretos)} CORRETOS vs {len(bugados)} BUGADOS vs {len(outros)} OUTROS")

    # Helper: distribuicao de um campo
    def dist(rows_set, field: str, label: str) -> None:
        c: Counter = Counter()
        for r in rows_set:
            c[r.get(field) or "(null)"] += 1
        print(f"  {label}:")
        for k, v in c.most_common(8):
            print(f"    {v:4d}  {k}")

    _section("ORIGEM dos itens")
    print("CORRETOS:")
    dist(corretos, "origem", "origem")
    print()
    print("BUGADOS (+/-3h):")
    dist(bugados, "origem", "origem")

    _section("IS_MANUAL")
    print("CORRETOS:")
    dist(corretos, "is_manual", "is_manual")
    print()
    print("BUGADOS (+/-3h):")
    dist(bugados, "is_manual", "is_manual")

    _section("STATUS atual da fila")
    print("CORRETOS:")
    dist(corretos, "status", "status")
    print()
    print("BUGADOS (+/-3h):")
    dist(bugados, "status", "status")

    _section("FIX_TIMEZONE_APPLIED (ja foi tocado por rescue script?)")
    print("CORRETOS:")
    dist(corretos, "ja_corrigido", "ja_corrigido")
    print()
    print("BUGADOS (+/-3h):")
    dist(bugados, "ja_corrigido", "ja_corrigido")

    _section("HORARIO de criacao (UTC) - bugados podem ter padrao de cron")
    def hour_dist(rows_set, label):
        c: Counter = Counter()
        for r in rows_set:
            c[r["criado_em"].hour] += 1
        print(f"  {label}:")
        for h in sorted(c.keys()):
            print(f"    {h:02d}h UTC : {c[h]:4d}")

    hour_dist(corretos, "CORRETOS")
    print()
    hour_dist(bugados, "BUGADOS (+/-3h)")

    _section("AMOSTRA: 10 BUGADOS mais recentes (todos os campos)")
    for r in bugados[:10]:
        print(f"  {r['criado_em']}  diff={r['diff_horas']:+.2f}h")
        print(f"    call_id={r['call_id']}")
        print(f"    origem={r['origem']!r}  is_manual={r['is_manual']!r}  status={r['status']!r}")
        print(f"    ja_corrigido={r['ja_corrigido']!r}  class_status={r['class_status']!r}")
        print(f"    operator={r['operator']!r}  agent={r['agent_id']!r}")
        print()

    _section("AMOSTRA: 5 CORRETOS mais recentes (comparativo)")
    for r in corretos[:5]:
        print(f"  {r['criado_em']}  diff={r['diff_horas']:+.2f}h")
        print(f"    call_id={r['call_id']}")
        print(f"    origem={r['origem']!r}  is_manual={r['is_manual']!r}  status={r['status']!r}")
        print(f"    operator={r['operator']!r}")
        print()

    conn.close()


if __name__ == "__main__":
    main()
