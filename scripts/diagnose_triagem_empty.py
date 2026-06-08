"""Diagnostico SOMENTE-LEITURA: por que itens nao estao aparecendo na Triagem.

Verifica 3 hipoteses:
1. Huawei sync nao esta produzindo linhas (fila vazia mesmo nos ultimos sync).
2. Itens existem mas estao com classification_status='pending' (fase 2 nao rodou).
3. Itens existem mas em status que a query da Triagem nao retorna.

Uso:
  $env:DATABASE_URL = "<connection-string-da-.env>"
  python scripts/diagnose_triagem_empty.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402


def _section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    conn = database.get_connection()
    try:
        cur = conn.cursor()
        agora = datetime.now(timezone.utc)
        ontem = (agora - timedelta(hours=24)).isoformat()
        dois_dias = (agora - timedelta(hours=48)).isoformat()

        # ---------- 1. Distribuicao geral da fila ----------
        _section("1) Distribuicao por status (toda a tabela)")
        cur.execute("SELECT status, COUNT(*) AS qtd FROM fila_revisao_classificacao GROUP BY status ORDER BY qtd DESC")
        for r in cur.fetchall():
            print(f"  {r['qtd']:6d}  {r['status']}")

        # ---------- 2. Producao nas ultimas 24h e 48h ----------
        _section("2) Itens novos por janela de tempo")
        for label, since in (("ultimas 24h", ontem), ("ultimas 48h", dois_dias)):
            cur.execute(
                """
                SELECT
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE metadata_json::jsonb ->> 'origem' = 'huawei_sync') AS huawei,
                  COUNT(*) FILTER (WHERE metadata_json::jsonb ->> 'is_manual' = 'true') AS manuais,
                  COUNT(*) FILTER (
                    WHERE metadata_json::jsonb ->> 'classification_status' = 'pending'
                  ) AS class_pending,
                  COUNT(*) FILTER (
                    WHERE metadata_json::jsonb ->> 'classification_status' = 'done'
                  ) AS class_done,
                  COUNT(*) FILTER (
                    WHERE metadata_json::jsonb ->> 'classification_status' = 'error'
                  ) AS class_error
                FROM fila_revisao_classificacao
                WHERE criado_em >= %s
                """,
                (since,),
            )
            r = cur.fetchone()
            print(f"  {label}:")
            print(f"     total inseridos      : {r['total']}")
            print(f"     via huawei_sync      : {r['huawei']}")
            print(f"     manuais              : {r['manuais']}")
            print(f"     classification=pend  : {r['class_pending']}")
            print(f"     classification=done  : {r['class_done']}")
            print(f"     classification=error : {r['class_error']}")

        # ---------- 3. Quantos itens DEVERIAM aparecer na Triagem ----------
        _section("3) Itens visiveis na Triagem (mesma query do /api/revisao/classificacao?status=pending)")
        cur.execute(
            """
            SELECT COUNT(*) AS qtd
            FROM fila_revisao_classificacao
            WHERE (
              (
                status = 'pending'
                AND NOT (
                  COALESCE(metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                  AND COALESCE(metadata_json::jsonb ->> 'classification_status', 'pending') = 'pending'
                  AND COALESCE(metadata_json::jsonb ->> 'is_manual', 'false') = 'false'
                )
              )
              OR status IN ('needs_manual_triage', 'blocked_operator')
            )
            """
        )
        r = cur.fetchone()
        print(f"  Visiveis agora na Triagem: {r['qtd']}")

        cur.execute(
            """
            SELECT COUNT(*) AS qtd
            FROM fila_revisao_classificacao
            WHERE status = 'pending'
              AND COALESCE(metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
              AND COALESCE(metadata_json::jsonb ->> 'classification_status', 'pending') = 'pending'
              AND COALESCE(metadata_json::jsonb ->> 'is_manual', 'false') = 'false'
            """
        )
        r = cur.fetchone()
        print(f"  ESCONDIDOS (huawei_sync + class_pending + nao-manual): {r['qtd']}")

        # ---------- 4. Ultimos 10 itens inseridos ----------
        _section("4) Ultimos 10 itens inseridos (criado_em DESC)")
        cur.execute(
            """
            SELECT
              id,
              nome_arquivo,
              status,
              metadata_json::jsonb ->> 'origem' AS origem,
              metadata_json::jsonb ->> 'is_manual' AS is_manual,
              metadata_json::jsonb ->> 'classification_status' AS class_status,
              metadata_json::jsonb ->> 'huawei_call_id' AS call_id,
              metadata_json::jsonb ->> 'huawei_begin_time' AS begin_time,
              criado_em
            FROM fila_revisao_classificacao
            ORDER BY criado_em DESC
            LIMIT 10
            """
        )
        for r in cur.fetchall():
            print(json.dumps(dict(r), ensure_ascii=False, default=str, indent=2))

        # ---------- 5. Ciclos de automacao recentes ----------
        _section("5) Ultimos 5 ciclos de automacao")
        try:
            cur.execute(
                """
                SELECT id, status, current_stage, current_message, started_at, finished_at,
                       error_message, sync_result_json
                FROM automation_cycles
                ORDER BY started_at DESC
                LIMIT 5
                """
            )
            for r in cur.fetchall():
                print(json.dumps(dict(r), ensure_ascii=False, default=str, indent=2))
        except Exception as e:
            print(f"  automation_cycles indisponivel: {e}")

        # ---------- 6. Pista do "audio nao baixado" + datas erradas ----------
        _section("6) Itens com erros de audio ou erros de classificacao (ultimos 30)")
        cur.execute(
            """
            SELECT
              id, nome_arquivo, status,
              metadata_json::jsonb ->> 'origem' AS origem,
              metadata_json::jsonb ->> 'classification_status' AS class_status,
              metadata_json::jsonb ->> 'erro' AS erro,
              metadata_json::jsonb ->> 'huawei_begin_time' AS begin_time,
              metadata_json::jsonb ->> 'huawei_call_id' AS call_id,
              metadata_json::jsonb ->> 'classified_audio_path' AS audio_path,
              criado_em
            FROM fila_revisao_classificacao
            WHERE metadata_json::jsonb ->> 'erro' IS NOT NULL
               OR metadata_json::jsonb ->> 'classification_status' = 'error'
            ORDER BY criado_em DESC
            LIMIT 30
            """
        )
        for r in cur.fetchall():
            print(json.dumps(dict(r), ensure_ascii=False, default=str, indent=2))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
