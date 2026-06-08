"""Backfill colaborador_id em auditorias existentes.

Percorre todas as auditorias com operator_name preenchido mas sem colaborador_id,
e tenta casar com a tabela colaboradores usando busca normalizada por nome.

Uso:
    python -m scripts.backfill_colaborador_id [--dry-run]
"""

import sys
import unicodedata
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import db.database as database


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or "").strip().lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def backfill(dry_run: bool = False):
    conn = database.get_connection()
        
    cursor = conn.cursor()

    # 1. Build lookup map: normalized name -> colaborador id
    cursor.execute("SELECT id, nome FROM colaboradores WHERE nome IS NOT NULL AND nome != ''")
    colab_map: dict[str, int] = {}
    for row in cursor.fetchall():
        key = _normalize(row["nome"])
        if key:
            colab_map[key] = row["id"]

    print(f"📋 {len(colab_map)} colaboradores no mapa de lookup")

    # 2. Find audits without colaborador_id
    cursor.execute("""
        SELECT id, operator_name, operator_id
        FROM audits
        WHERE operator_name IS NOT NULL
          AND operator_name != ''
          AND (colaborador_id IS NULL OR colaborador_id = 0)
    """)
    audits = cursor.fetchall()
    print(f"🔍 {len(audits)} auditorias sem colaborador_id")

    matched = 0
    unmatched_names: set[str] = set()

    for audit in audits:
        name_key = _normalize(audit["operator_name"])
        colab_id = colab_map.get(name_key)

        if not colab_id and audit["operator_id"]:
            # Fallback: try by operator_id (Huawei/telefonia)
            cursor.execute(
                "SELECT id FROM colaboradores WHERE id_huawei = %s OR id_telefonia = %s LIMIT 1",
                (audit["operator_id"], audit["operator_id"]),
            )
            row = cursor.fetchone()
            if row:
                colab_id = row["id"]

        if colab_id:
            if not dry_run:
                cursor.execute(
                    "UPDATE audits SET colaborador_id = %s WHERE id = %s",
                    (colab_id, audit["id"]),
                )
            matched += 1
        else:
            unmatched_names.add(audit["operator_name"])

    if not dry_run:
        conn.commit()

    conn.close()

    total = len(audits)
    match_rate = (matched / total * 100) if total > 0 else 0

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Resultado:")
    print(f"  ✅ Vinculadas: {matched}/{total} ({match_rate:.1f}%)")
    print(f"  ❌ Sem match:  {len(unmatched_names)}")

    if unmatched_names:
        print(f"\n📝 Nomes sem correspondência ({len(unmatched_names)}):")
        for name in sorted(unmatched_names):
            print(f"   - {name}")

    return {
        "total": total,
        "matched": matched,
        "match_rate_percent": round(match_rate, 1),
        "unmatched_names": sorted(unmatched_names),
    }


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    backfill(dry_run=dry_run)
