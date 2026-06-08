"""Recuperacao da tabela colaboradores apos estrago do re-import (2026-05-26).

Operacoes (em UMA transacao, com audit log):
1. Aplica migration m20260526_001_colaboradores_audit_log (se ausente).
2. Reassigna audits.colaborador_id das duplicatas para os canonicals.
3. UPDATE auditavel=0 nos perdedores dos conflitos Tipo B + restauracao BUG-025.
4. DELETE das 10 duplicatas vazias (sem audits restantes).
5. Adiciona UNIQUE PARTIAL INDEX em id_huawei para impedir recorrencia.

Idempotente: pode rodar de novo. Verifica pre-condicoes antes de cada passo.

Uso:
  python scripts/fix_colaboradores_duplicates.py --dry-run   (default)
  python scripts/fix_colaboradores_duplicates.py --execute
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from db import database  # noqa: E402


# ============================================================================
# PLANO DE EXECUCAO
# ============================================================================

# Reassignments: audits.colaborador_id (origem -> destino)
REASSIGN_AUDITS = [
    (1271, 985, "Andressa Rambo Franco — colapsar dup 1271 (sem matricula) no canonical 985 (com matricula+escala)"),
    (1391, 1393, "Poliana Emanuelly Pereira Possenti — colapsar dup 1391 no canonical 1393"),
]

# UPDATE auditavel=0 nos perdedores dos conflitos id_huawei + restauracao BUG-025
UPDATE_AUDITAVEL_ZERO = [
    (1061, "Fernanda Sant Anna Santiago de Souza", "Restaurar decisao BUG-025: libera id_huawei 2967 para Poliana (commit 426e66c)"),
    (1095, "Cintia Cristina Domingos Ribeiro", "Conflito id_huawei 2428: Raffaella Barrozo (755) e a titular conforme re-imports recorrentes da Excel; Cintia perde auditavel"),
    (817, "Guilherme Aparecido Parente Boettger", "Conflito id_huawei 2505: Patrick Miranda (721) e o titular conforme re-imports recorrentes da Excel; Guilherme perde auditavel"),
]

# DELETEs (apenas IDs SEM audits restantes apos reassignment)
DELETE_DUPLICATES = [
    (1075, "Pamela Nadona", "Duplicata legacy (encoding antigo, setor BAS) — canonical e 1309 (TRANSFERENCIA)"),
    (1307, "Pamela Nadona", "Duplicata identica do canonical 1309"),
    (1310, "Gabriela Sesering Fortunato", "Duplicata identica do canonical 1087"),
    (1311, "Patrick Miranda Nunes", "Duplicata identica do canonical 721"),
    (1312, "Raffaella Barrozo da Silva", "Duplicata do canonical 755 (re-import da Excel)"),
    (1313, "Raffaella Barrozo da Silva", "Duplicata do canonical 755 (re-import da Excel)"),
    (1314, "Raffaella Barrozo da Silva", "Duplicata do canonical 755 (re-import da Excel)"),
    (1271, "Andressa Regina Rambo Franco", "Duplicata sem matricula/escala — audits ja reassignados ao canonical 985"),
    (1391, "Poliana Emanuelly Pereira Possenti", "Duplicata — audits ja reassignados ao canonical 1393"),
    (1392, "Poliana Emanuelly Pereira Possenti", "Duplicata identica do canonical 1393"),
]


# ============================================================================
# IMPLEMENTACAO
# ============================================================================

AUDITABLE_FIELDS = (
    "nome", "supervisor", "setor", "escala", "status", "matricula",
    "id_weon", "id_huawei", "id_telefonia", "softphone_number",
    "telefonia_account", "organizacao_telefonia", "tipo_agente",
    "status_telefonia", "auditavel",
)


def section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def ensure_audit_log_table_exists(cur) -> bool:
    cur.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema='public' AND table_name='colaboradores_audit_log'
        )
    """)
    return cur.fetchone()[0] if isinstance(cur.fetchone(), tuple) else cur.fetchone()["exists"]


def apply_audit_log_migration(cur) -> bool:
    """Cria a tabela colaboradores_audit_log se nao existir.

    Replica a definicao da migration m20260526_001 (idempotente via IF NOT EXISTS).
    """
    cur.execute("""
        CREATE TABLE IF NOT EXISTS colaboradores_audit_log (
            id             BIGSERIAL PRIMARY KEY,
            acao           TEXT NOT NULL
                           CHECK (acao IN ('create','update','delete')),
            entity_id      TEXT NOT NULL,
            payload_antes  JSONB,
            payload_depois JSONB,
            alterado_por   TEXT NOT NULL,
            alterado_em    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            motivo         TEXT,
            origem         TEXT NOT NULL DEFAULT 'ui'
                           CHECK (origem IN ('ui','api','seed','script','system','migration'))
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_audit_log_entity_id ON colaboradores_audit_log(entity_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_audit_log_alterado_em ON colaboradores_audit_log(alterado_em DESC)")
    # Registra na schema_migrations
    cur.execute("""
        INSERT INTO schema_migrations(name) VALUES ('m20260526_001_colaboradores_audit_log')
        ON CONFLICT (name) DO NOTHING
    """)
    return True


def snapshot_colaborador(cur, colaborador_id: int) -> dict | None:
    fields = ", ".join(AUDITABLE_FIELDS)
    cur.execute(f"SELECT id, {fields} FROM colaboradores WHERE id = %s", (colaborador_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def log_audit(cur, *, acao: str, entity_id: int, payload_antes, payload_depois,
              motivo: str, alterado_por: str = "script:fix_colaboradores_duplicates",
              origem: str = "script") -> None:
    cur.execute("""
        INSERT INTO colaboradores_audit_log (acao, entity_id, payload_antes, payload_depois, alterado_por, motivo, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (acao, str(entity_id),
          json.dumps(payload_antes, default=str) if payload_antes is not None else None,
          json.dumps(payload_depois, default=str) if payload_depois is not None else None,
          alterado_por, motivo, origem))


def run_reassign_audits(cur, dry_run: bool) -> int:
    """Sempre executa o SQL; rollback final em dry-run preserva o banco."""
    total = 0
    prefix = "DRY" if dry_run else "GO "
    for src_id, dst_id, motivo in REASSIGN_AUDITS:
        cur.execute("SELECT COUNT(*) AS n FROM audits WHERE colaborador_id = %s", (src_id,))
        n = cur.fetchone()["n"]
        if n == 0:
            print(f"  [skip] reassign audits {src_id} -> {dst_id}: 0 audits")
            continue
        print(f"  [{prefix}] reassign {n} audits: colaborador_id {src_id} -> {dst_id}  ({motivo[:60]}...)")
        cur.execute("UPDATE audits SET colaborador_id = %s WHERE colaborador_id = %s", (dst_id, src_id))
        log_audit(cur, acao="update", entity_id=src_id,
                  payload_antes={"audits_reassign_from_colaborador_id": src_id, "audits_count": n},
                  payload_depois={"audits_reassign_to_colaborador_id": dst_id},
                  motivo=motivo)
        total += n
    return total


def run_updates_auditavel(cur, dry_run: bool) -> int:
    n = 0
    prefix = "DRY" if dry_run else "GO "
    for col_id, nome_esperado, motivo in UPDATE_AUDITAVEL_ZERO:
        snap = snapshot_colaborador(cur, col_id)
        if not snap:
            print(f"  [skip] {col_id} {nome_esperado}: nao encontrado")
            continue
        if snap.get("auditavel") in (0, False):
            print(f"  [skip] {col_id} {snap['nome']}: ja esta auditavel=0")
            continue
        print(f"  [{prefix}] auditavel=0  id={col_id}  {snap['nome']}  motivo={motivo[:50]}...")
        cur.execute("UPDATE colaboradores SET auditavel = 0, atualizado_em = CURRENT_TIMESTAMP WHERE id = %s", (col_id,))
        after = snapshot_colaborador(cur, col_id)
        log_audit(cur, acao="update", entity_id=col_id,
                  payload_antes=snap, payload_depois=after, motivo=motivo)
        n += 1
    return n


def run_deletes(cur, dry_run: bool) -> int:
    n = 0
    prefix = "DRY" if dry_run else "GO "
    for col_id, nome_esperado, motivo in DELETE_DUPLICATES:
        snap = snapshot_colaborador(cur, col_id)
        if not snap:
            print(f"  [skip] {col_id} {nome_esperado}: ja nao existe")
            continue
        # Safety: nunca deletar se ainda tem audits ligados
        cur.execute("SELECT COUNT(*) AS n FROM audits WHERE colaborador_id = %s", (col_id,))
        audits_count = cur.fetchone()["n"]
        if audits_count > 0:
            raise RuntimeError(
                f"REFUSE delete id={col_id} ({snap['nome']}): ainda tem {audits_count} audits. "
                "Reassign primeiro."
            )
        print(f"  [{prefix}] DELETE id={col_id}  {snap['nome']}  motivo={motivo[:50]}...")
        log_audit(cur, acao="delete", entity_id=col_id,
                  payload_antes=snap, payload_depois=None, motivo=motivo)
        cur.execute("DELETE FROM colaboradores WHERE id = %s", (col_id,))
        n += 1
    return n


def run_unique_index(cur, dry_run: bool) -> None:
    prefix = "DRY" if dry_run else "GO "
    # Verifica se ainda ha duplicatas que impediriam a constraint
    cur.execute("""
        SELECT id_huawei, COUNT(*) AS qtd
        FROM colaboradores
        WHERE status='ATIVO'
          AND COALESCE(auditavel, 1) = 1
          AND COALESCE(NULLIF(TRIM(id_huawei),''),'') <> ''
        GROUP BY id_huawei
        HAVING COUNT(*) > 1
    """)
    remaining = cur.fetchall()
    if remaining:
        print(f"  [WARN] {len(remaining)} id_huawei ainda duplicados — nao cria UNIQUE INDEX:")
        for r in remaining:
            print(f"     {r['id_huawei']}: {r['qtd']}x")
        return
    print(f"  [{prefix}] CREATE UNIQUE INDEX IF NOT EXISTS uq_colaboradores_id_huawei_ativo_auditavel")
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_colaboradores_id_huawei_ativo_auditavel
        ON colaboradores(id_huawei)
        WHERE status='ATIVO'
          AND COALESCE(auditavel, 1) = 1
          AND COALESCE(NULLIF(TRIM(id_huawei),''),'') <> ''
    """)


def main() -> None:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--execute", action="store_true")
    args = ap.parse_args()
    dry_run = not args.execute

    print(f"Modo: {'DRY-RUN (nenhuma mudanca)' if dry_run else 'EXECUTE (mudancas reais)'}")

    conn = database.get_connection()
    try:
        cur = conn.cursor()

        section("1) Migration colaboradores_audit_log")
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='colaboradores_audit_log')")
        exists = cur.fetchone()["exists"]
        if exists:
            print("  [skip] tabela ja existe")
        else:
            prefix = "DRY" if dry_run else "GO "
            print(f"  [{prefix}] criar tabela colaboradores_audit_log + indices + registrar na schema_migrations")
            apply_audit_log_migration(cur)

        section("2) Reassign audits.colaborador_id")
        n_reassign = run_reassign_audits(cur, dry_run)
        print(f"  Total audits reassignados: {n_reassign}")

        section("3) UPDATE auditavel=0 (perdedores dos conflitos)")
        n_upd = run_updates_auditavel(cur, dry_run)
        print(f"  Total UPDATEs: {n_upd}")

        section("4) DELETE duplicatas (apenas sem audits)")
        n_del = run_deletes(cur, dry_run)
        print(f"  Total DELETEs: {n_del}")

        section("5) UNIQUE PARTIAL INDEX em id_huawei")
        run_unique_index(cur, dry_run)

        if dry_run:
            print("\n>>> DRY-RUN: rollback (nenhuma mudanca persistida)")
            conn.rollback()
        else:
            conn.commit()
            print("\n>>> COMMITED")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
