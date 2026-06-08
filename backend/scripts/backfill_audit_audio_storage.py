import argparse
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db.database as database


def _fetch_candidates(limit: int | None = None) -> list[dict]:
    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        sql = """
            SELECT id, input_hash, audio_original_filename, audio_mime_type
            FROM audits
            WHERE COALESCE(source_type, 'audio') = 'audio'
              AND COALESCE(audio_storage_path, '') = ''
            ORDER BY id ASC
        """
        params: tuple = ()
        if limit:
            sql += " LIMIT %s"
            params = (limit,)
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def backfill(*, dry_run: bool, limit: int | None = None) -> dict:
    candidates = _fetch_candidates(limit)
    recovered: list[dict] = []
    missing: list[dict] = []

    for audit in candidates:
        audit_id = int(audit["id"])
        if dry_run:
            queue_item = database.obter_fila_revisao_classificacao_por_auditoria(
                audit_id,
                audit.get("input_hash"),
            )
            metadata = queue_item.get("metadata") if isinstance(queue_item, dict) else None
            classified_path = metadata.get("classified_audio_path") if isinstance(metadata, dict) else None
            if classified_path:
                recovered.append({"audit_id": audit_id, "classified_audio_path": classified_path})
            else:
                missing.append({"audit_id": audit_id, "reason": "classified_audio_path ausente"})
            continue

        media = database.recover_audit_audio_from_classified_queue(audit_id, audit, audit)
        if media and media.get("audio_storage_path"):
            recovered.append({"audit_id": audit_id, "audio_storage_path": media["audio_storage_path"]})
        else:
            missing.append({"audit_id": audit_id, "reason": "audio classificado indisponivel"})

    return {
        "dry_run": dry_run,
        "candidates": len(candidates),
        "recovered": recovered,
        "missing": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reanexa arquivos de audio de auditorias usando o audio classificado da fila de triagem.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa o backfill. Sem esta flag, roda em dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de auditorias verificadas.",
    )
    args = parser.parse_args()

    result = backfill(dry_run=not args.apply, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
