"""Backfill media_files with classified media pointers.

Phase 1 intentionally covers only classified/pre-audit media. Audit-final media
remains in the legacy audit_storage path until the Telefonia/Triagem ownership
and cleanup rules are defined.

Run without flags for a dry-run. Use --commit to persist rows.
"""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=True)

import db.database as database  # noqa: E402
from core.media_storage import classified_media_hash  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _bucket_name() -> str:
    name = os.getenv("GCS_BUCKET_NAME", "").strip()
    if not name and os.getenv("K_SERVICE"):
        return "auditoria-nstech-audios"
    return name or "auditoria-nstech-audios"


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _load_gcs_objects(bucket_name: str) -> dict[str, dict[str, Any]]:
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    objects: dict[str, dict[str, Any]] = {}
    for blob in bucket.list_blobs():
        objects[blob.name] = {
            "size_bytes": int(blob.size or 0),
            "content_type": blob.content_type,
        }
    return objects


def _classified_local_roots() -> list[Path]:
    roots = [
        Path(
            os.getenv(
                "CLASSIFIED_AUDIO_STORAGE_DIR",
                str(Path(__file__).resolve().parent.parent / "storage" / "classified_audio"),
            )
        ).expanduser(),
        Path(os.getenv("MEDIA_STORAGE_ROOT", str(Path(__file__).resolve().parent.parent / "storage"))).expanduser(),
    ]

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            unique_roots.append(resolved)
            seen.add(resolved)
    return unique_roots


def _safe_local_file(media_path: str) -> Optional[Path]:
    clean_path = str(media_path or "").strip().replace("\\", "/").lstrip("/")
    if not clean_path or ".." in clean_path.split("/") or ":" in clean_path.split("/")[0]:
        return None

    for root in _classified_local_roots():
        candidate = (root / clean_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.exists():
            return candidate
    return None


def _guess_content_type(path: str, filename: Optional[str]) -> str:
    guessed, _ = mimetypes.guess_type(filename or path)
    return guessed or "audio/wav"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill classified media pointers into media_files.")
    parser.add_argument("--commit", action="store_true", help="Persist changes. Default is dry-run.")
    parser.add_argument(
        "--skip-gcs-inventory",
        action="store_true",
        help="Do not list the GCS bucket. Missing paths will be treated as local/drift pointers.",
    )
    return parser.parse_args()


def run_backfill(*, commit: bool = False, skip_gcs_inventory: bool = False) -> int:
    bucket_name = _bucket_name()
    logging.info("Mode: %s", "COMMIT" if commit else "DRY-RUN")

    gcs_objects: dict[str, dict[str, Any]] = {}
    if not skip_gcs_inventory:
        logging.info("Inspecting GCS bucket: %s", bucket_name)
        try:
            gcs_objects = _load_gcs_objects(bucket_name)
        except Exception as exc:  # noqa: BLE001
            logging.error("Failed to inspect GCS bucket %s: %s", bucket_name, exc)
            return 1
        logging.info("Found %d GCS objects.", len(gcs_objects))

    conn = database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.media_files')")
        if cur.fetchone()[0] is None:
            logging.error("Table media_files does not exist. Run pending migrations before this backfill.")
            return 1

        cur.execute("SELECT file_hash FROM media_files")
        existing_hashes = {row[0] for row in cur.fetchall()}

        cur.execute(
            """
            SELECT input_hash, nome_arquivo, metadata_json
              FROM fila_revisao_classificacao
             WHERE metadata_json IS NOT NULL
            """
        )

        pending: dict[str, dict[str, Any]] = {}
        skipped = 0
        for input_hash, original_filename, metadata_json in cur.fetchall():
            file_hash = classified_media_hash(input_hash)
            metadata = _coerce_metadata(metadata_json)
            media_path = str(metadata.get("classified_audio_path") or metadata.get("classified_file_path") or "").strip()
            if not file_hash or not media_path:
                skipped += 1
                continue
            if file_hash in existing_hashes or file_hash in pending:
                continue

            if media_path in gcs_objects:
                object_info = gcs_objects[media_path]
                pending[file_hash] = {
                    "file_hash": file_hash,
                    "storage_backend": "gcs",
                    "storage_key": media_path,
                    "content_type": object_info.get("content_type") or _guess_content_type(media_path, original_filename),
                    "size_bytes": object_info.get("size_bytes") or 0,
                    "original_filename": original_filename or Path(media_path).name,
                }
                continue

            local_file = _safe_local_file(media_path)
            pending[file_hash] = {
                "file_hash": file_hash,
                "storage_backend": "local",
                "storage_key": media_path,
                "content_type": _guess_content_type(media_path, original_filename),
                "size_bytes": local_file.stat().st_size if local_file else 0,
                "original_filename": original_filename or Path(media_path).name,
            }

        gcs_count = sum(1 for item in pending.values() if item["storage_backend"] == "gcs")
        local_count = sum(1 for item in pending.values() if item["storage_backend"] == "local")
        logging.info(
            "Prepared %d classified media rows (gcs=%d, local_or_drift=%d, skipped=%d).",
            len(pending),
            gcs_count,
            local_count,
            skipped,
        )

        if not commit:
            logging.info("Dry-run complete. Re-run with --commit to persist.")
            return 0

        inserted = 0
        for item in pending.values():
            cur.execute(
                """
                INSERT INTO media_files
                    (file_hash, storage_backend, storage_key, content_type, size_bytes, original_filename)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_hash) DO NOTHING
                """,
                (
                    item["file_hash"],
                    item["storage_backend"],
                    item["storage_key"],
                    item["content_type"],
                    item["size_bytes"],
                    item["original_filename"],
                ),
            )
            inserted += cur.rowcount

        conn.commit()
        logging.info("Inserted %d media_files rows.", inserted)
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(run_backfill(commit=args.commit, skip_gcs_inventory=args.skip_gcs_inventory))
