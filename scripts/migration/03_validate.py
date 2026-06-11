#!/usr/bin/env python3
"""03_validate.py — Valida a migração Neon → Azure PostgreSQL.

Compara origem e destino e falha (exit 1) em qualquer divergência:
  1. Lista de tabelas do schema public.
  2. Contagem de linhas por tabela.
  3. Conjunto de migrations aplicadas (schema_migrations.name).
  4. Alinhamento das sequences (max(id) das tabelas seriais críticas —
     sequence desalinhada causa erro de PK duplicada no primeiro INSERT).
  5. Extensão pgvector presente no destino.

Uso:
  SOURCE_DATABASE_URL='postgresql://...neon...' \
  TARGET_DATABASE_URL='postgresql://...azure...' \
  python 03_validate.py

Requer: psycopg2 (use o venv do backend: backend/.venv).
"""
from __future__ import annotations

import os
import sys

import psycopg2

# Tabelas com PK serial cujo desalinhamento de sequence quebraria o app.
SERIAL_TABLES = (
    "audits",
    "audit_criteria",
    "colaboradores",
    "fila_revisao_classificacao",
    "huawei_sync_logs",
    "automation_cycle_runs",
    "media_files",
    "ai_feedback",
)


def _connect(env_name: str):
    url = (os.getenv(env_name) or "").strip()
    if not url:
        print(f"ERRO: defina {env_name}.", file=sys.stderr)
        sys.exit(2)
    return psycopg2.connect(url, connect_timeout=15)


def _tables(cur) -> list[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
    )
    return [r[0] for r in cur.fetchall()]


def _count(cur, table: str) -> int:
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')  # nome vem do information_schema
    return int(cur.fetchone()[0])


def _migrations(cur) -> set[str]:
    cur.execute("SELECT name FROM schema_migrations")
    return {r[0] for r in cur.fetchall()}


def _sequence_state(cur, table: str) -> tuple[int, int] | None:
    cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    seq = row[0]
    cur.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')
    max_id = int(cur.fetchone()[0])
    cur.execute(f"SELECT last_value FROM {seq}")
    last_value = int(cur.fetchone()[0])
    return max_id, last_value


def main() -> int:
    src = _connect("SOURCE_DATABASE_URL")
    dst = _connect("TARGET_DATABASE_URL")
    scur, dcur = src.cursor(), dst.cursor()
    problemas: list[str] = []

    # 1. Tabelas
    src_tables, dst_tables = _tables(scur), _tables(dcur)
    faltando = sorted(set(src_tables) - set(dst_tables))
    if faltando:
        problemas.append(f"Tabelas ausentes no destino: {faltando}")
    print(f"[1/5] Tabelas: origem={len(src_tables)} destino={len(dst_tables)}"
          + (" OK" if not faltando else " DIVERGENTE"))

    # 2. Contagens
    divergentes = []
    for table in src_tables:
        if table not in dst_tables:
            continue
        s, d = _count(scur, table), _count(dcur, table)
        if s != d:
            divergentes.append(f"{table}: origem={s} destino={d}")
    if divergentes:
        problemas.append("Contagens divergentes: " + "; ".join(divergentes))
    print(f"[2/5] Contagem de linhas: {'OK' if not divergentes else 'DIVERGENTE -> ' + str(divergentes)}")

    # 3. Migrations
    sm, dm = _migrations(scur), _migrations(dcur)
    if sm != dm:
        problemas.append(f"schema_migrations difere: só na origem={sorted(sm - dm)}, só no destino={sorted(dm - sm)}")
    print(f"[3/5] Migrations aplicadas: origem={len(sm)} destino={len(dm)} {'OK' if sm == dm else 'DIVERGENTE'}")

    # 4. Sequences
    seq_problemas = []
    for table in SERIAL_TABLES:
        state = _sequence_state(dcur, table) if table in dst_tables else None
        if state is None:
            continue
        max_id, last_value = state
        if last_value < max_id:
            seq_problemas.append(f"{table}: max(id)={max_id} > sequence={last_value}")
    if seq_problemas:
        problemas.append(
            "Sequences desalinhadas (rode SELECT setval(pg_get_serial_sequence('<t>','id'), max(id)) ...): "
            + "; ".join(seq_problemas)
        )
    print(f"[4/5] Sequences: {'OK' if not seq_problemas else 'DESALINHADAS -> ' + str(seq_problemas)}")

    # 5. pgvector no destino
    dcur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    has_vector = bool(dcur.fetchone())
    if not has_vector:
        problemas.append("Extensão 'vector' (pgvector) ausente no destino — RAG (procedimento_chunks) inoperante.")
    print(f"[5/5] pgvector no destino: {'OK' if has_vector else 'AUSENTE'}")

    print()
    if problemas:
        print("RESULTADO: FALHOU")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("RESULTADO: MIGRACAO VALIDADA ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
