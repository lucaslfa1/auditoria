"""Diagnostico SOMENTE-LEITURA: investiga a hipotese H1 (timezone bug ativo).

Hipotese: huawei_begin_time esta sendo gravado com offset de timezone, fazendo
o lookup de Voice/{YYYYMMDD}/ apontar pra pasta errada e marcar audio_not_found.

Killshot: huawei_call_id da Huawei tem formato 'EPOCH_SECONDS-suffix'. Se o
diff entre huawei_begin_time (ms) e o epoch embutido for consistentemente
+/- 3h, confirma o bug.

Roda 3 queries read-only contra Postgres.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

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
        print("ERRO: DATABASE_URL nao encontrada no backend/.env")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ---------- 1. Volume e padrao dos audio_not_found ----------
    _section("1) Volume de audio_not_found nos ultimos 14 dias")
    cur.execute(
        """
        SELECT
          DATE(sincronizado_em) AS dia,
          COUNT(*) AS total_failed,
          COUNT(DISTINCT agent_id) AS agentes_afetados
        FROM huawei_sync_logs
        WHERE status = 'failed'
          AND failure_reason = 'audio_not_found'
          AND sincronizado_em >= NOW() - INTERVAL '14 days'
        GROUP BY DATE(sincronizado_em)
        ORDER BY dia DESC
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("  Nenhum audio_not_found nos ultimos 14 dias.")
    else:
        for r in rows:
            print(f"  {r['dia']}  failed={r['total_failed']:4d}  agentes={r['agentes_afetados']:3d}")

    # ---------- 2. Distribuicao por failure_reason ----------
    _section("2) Distribuicao por failure_reason / status (ultimos 7 dias)")
    cur.execute(
        """
        SELECT
          failure_reason,
          status,
          COUNT(*) AS qtd
        FROM huawei_sync_logs
        WHERE sincronizado_em >= NOW() - INTERVAL '7 days'
        GROUP BY failure_reason, status
        ORDER BY qtd DESC
        """
    )
    for r in cur.fetchall():
        print(f"  {r['qtd']:6d}  status={r['status']!r:25s}  reason={r['failure_reason']!r}")

    # ---------- 3. KILLSHOT: diff begin_time vs call_id epoch ----------
    _section("3) KILLSHOT - diff entre huawei_begin_time e epoch embutido no call_id")
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
          metadata_json::jsonb->>'fix_timezone_applied' AS ja_corrigido,
          criado_em
        FROM fila_revisao_classificacao
        WHERE metadata_json::jsonb->>'huawei_call_id' ~ '^[0-9]+-'
          AND metadata_json::jsonb->>'huawei_begin_time' ~ '^[0-9]+$'
          AND criado_em::timestamptz >= NOW() - INTERVAL '7 days'
        ORDER BY criado_em::timestamptz DESC
        LIMIT 200
        """
    )
    rows = cur.fetchall()
    if not rows:
        print("  Nenhum item com huawei_call_id/begin_time nos ultimos 7 dias.")
    else:
        # Distribuicao do diff
        diffs = [float(r["diff_horas"]) for r in rows if r["diff_horas"] is not None]
        bucket: Counter = Counter()
        for d in diffs:
            # bucket por hora inteira
            bucket[round(d)] += 1

        print(f"  Total de itens analisados: {len(diffs)}")
        print(f"  Distribuicao do diff (horas inteiras):")
        for h in sorted(bucket.keys()):
            marker = "  <- SUSPEITO" if abs(h) == 3 else ("  ok" if h == 0 else "")
            print(f"    diff={h:+3d}h : {bucket[h]:5d} itens{marker}")

        # Amostra dos primeiros 15
        print()
        print("  Amostra dos 15 mais recentes:")
        for r in rows[:15]:
            corrigido = " [JA_CORRIGIDO]" if r["ja_corrigido"] == "true" else ""
            print(
                f"    {r['criado_em']}  call_id={(r['call_id'] or '')[:40]:40s}  "
                f"diff={r['diff_horas']:+6.2f}h{corrigido}"
            )

        # Veredito automatico
        print()
        if len(diffs) >= 5:
            zero_count = sum(1 for d in diffs if abs(d) < 0.5)
            three_count = sum(1 for d in diffs if 2.5 < abs(d) < 3.5)
            print("  VEREDITO AUTOMATICO:")
            print(f"    ~0h    : {zero_count}/{len(diffs)} ({100*zero_count/len(diffs):.1f}%)")
            print(f"    ~+/-3h : {three_count}/{len(diffs)} ({100*three_count/len(diffs):.1f}%)")
            if three_count / len(diffs) > 0.5:
                print("    >>> H1 CONFIRMADA: maioria com diff ~3h = bug timezone ATIVO")
            elif zero_count / len(diffs) > 0.9:
                print("    >>> H1 REFUTADA: timestamps consistentes, investigar outra causa")
            else:
                print("    >>> RESULTADO MISTO: investigar quais commits/datas tem o bug")

    conn.close()
    print()
    print("Diagnostico concluido.")


if __name__ == "__main__":
    main()
