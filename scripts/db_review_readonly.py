"""Read-only database review for the official Auditoria PostgreSQL database.

This script intentionally does not import ``backend.database`` or call
``init_db()``. It only runs SELECT-style catalog and consistency checks.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import DictCursor


ROOT_DIR = Path(__file__).resolve().parents[1]


CRITICAL_TABLES = [
    "schema_migrations",
    "schema_metadata",
    "users",
    "configuracoes",
    "configuracoes_audit_log",
    "audit_sectors",
    "audit_alerts",
    "audit_criteria",
    "audit_criteria_audit_log",
    "audit_drafts",
    "sector_aliases",
    "sector_aliases_audit_log",
    "ai_prompts",
    "ai_prompts_audit_log",
    "ai_feedback",
    "procedimento_chunks",
    "colaboradores",
    "audits",
    "arquivos_salvos",
    "gestor_feedbacks",
    "report_exports",
    "ligacoes_auditadas",
    "resultados_classificacao",
    "fila_revisao_classificacao",
    "resultados_auditoria",
    "huawei_sync_logs",
    "telefonia_sync_history",
    "huawei_d_minus_1_runs",
    "automation_cycle_runs",
    "fechamento_cadeia_contatos",
    "fechamento_layout_operadores",
    "fechamento_layout_overrides",
    "transcript_candidates",
    "media_files",
]

CRITICAL_VIEWS = [
    "audits_com_colaborador",
    "ligacoes_boas",
    "ligacoes_ruins",
    "ligacoes_zeradas",
]


def load_env_file(path: Path, *, override: bool) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def mask_url(url: str) -> dict[str, Any]:
    parsed = urlparse(url)
    query = dict(part.split("=", 1) for part in parsed.query.split("&") if "=" in part)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname,
        "database": parsed.path.lstrip("/"),
        "uses_pooler": "-pooler" in (parsed.hostname or ""),
        "sslmode": query.get("sslmode", ""),
        "official_host_match": "ep-falling-hall-ac2t9rln" in (parsed.hostname or ""),
    }


def fetch_all(cursor, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cursor.execute(sql, params)
    return [dict(row) for row in cursor.fetchall()]


def fetch_one(cursor, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return dict(row) if row else None


def scalar(cursor, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    return row[0]


def table_exists(cursor, table_name: str) -> bool:
    return bool(
        scalar(
            cursor,
            "SELECT to_regclass(%s) IS NOT NULL",
            (f"public.{table_name}",),
        )
    )


def exact_counts(cursor, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in table_names:
        if not table_exists(cursor, table_name):
            continue
        cursor.execute(f'SELECT COUNT(*) AS count FROM public."{table_name}"')
        counts[table_name] = int(cursor.fetchone()["count"])
    return counts


def load_expected_migrations() -> list[str]:
    migrations_dir = ROOT_DIR / "backend" / "db" / "migration_steps"
    names: list[str] = []
    for path in sorted(migrations_dir.glob("m*.py")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r'MIGRATION_NAME\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            names.append(match.group(1))
    return sorted(names)


def collect_schema(cursor) -> dict[str, Any]:
    tables = fetch_all(
        cursor,
        """
        SELECT
            c.relname AS table_name,
            pg_total_relation_size(c.oid) AS total_bytes,
            pg_relation_size(c.oid) AS table_bytes,
            COALESCE(s.n_live_tup, c.reltuples)::bigint AS estimated_rows,
            COALESCE(s.n_dead_tup, 0)::bigint AS estimated_dead_rows,
            s.last_vacuum::text AS last_vacuum,
            s.last_autovacuum::text AS last_autovacuum,
            s.last_analyze::text AS last_analyze,
            s.last_autoanalyze::text AS last_autoanalyze
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
        ORDER BY pg_total_relation_size(c.oid) DESC, c.relname
        """,
    )
    views = fetch_all(
        cursor,
        """
        SELECT table_name
        FROM information_schema.views
        WHERE table_schema = 'public'
        ORDER BY table_name
        """,
    )
    columns = fetch_all(
        cursor,
        """
        SELECT
            table_name,
            column_name,
            ordinal_position,
            data_type,
            udt_name,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """,
    )
    constraints = fetch_all(
        cursor,
        """
        SELECT
            tc.table_name,
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = 'public'
        ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position
        """,
    )
    indexes = fetch_all(
        cursor,
        """
        SELECT
            schemaname,
            tablename,
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY tablename, indexname
        """,
    )
    extensions = fetch_all(
        cursor,
        """
        SELECT extname, extversion
        FROM pg_extension
        ORDER BY extname
        """,
    )
    sequences = fetch_all(
        cursor,
        """
        SELECT sequence_schema, sequence_name, data_type, start_value, minimum_value, maximum_value
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
        ORDER BY sequence_name
        """,
    )
    return {
        "tables": tables,
        "views": views,
        "columns": columns,
        "constraints": constraints,
        "indexes": indexes,
        "extensions": extensions,
        "sequences": sequences,
    }


def collect_migrations(cursor) -> dict[str, Any]:
    expected = load_expected_migrations()
    applied: list[str] = []
    if table_exists(cursor, "schema_migrations"):
        applied = [
            str(row["name"])
            for row in fetch_all(cursor, "SELECT name FROM schema_migrations ORDER BY name")
        ]
    return {
        "expected_count": len(expected),
        "applied_count": len(applied),
        "missing_in_db": sorted(set(expected) - set(applied)),
        "extra_in_db": sorted(set(applied) - set(expected)),
        "latest_expected": expected[-1] if expected else "",
        "latest_applied": applied[-1] if applied else "",
        "expected": expected,
        "applied": applied,
    }


def collect_schema_metadata(cursor) -> dict[str, str]:
    if not table_exists(cursor, "schema_metadata"):
        return {}
    return {
        str(row["key"]): str(row["value"] or "")
        for row in fetch_all(cursor, "SELECT key, value FROM schema_metadata ORDER BY key")
    }


def collect_integrity(cursor) -> dict[str, Any]:
    result: dict[str, Any] = {}

    if table_exists(cursor, "audits"):
        result["audits_status_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(status, '<null>') AS status, COUNT(*)::bigint AS count
            FROM audits
            GROUP BY COALESCE(status, '<null>')
            ORDER BY count DESC, status
            """,
        )
        result["audits_source_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(source_type, '<null>') AS source_type, COUNT(*)::bigint AS count
            FROM audits
            GROUP BY COALESCE(source_type, '<null>')
            ORDER BY count DESC, source_type
            """,
        )
        result["audits_duplicate_input_hash_groups"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*) FROM (
                    SELECT input_hash
                    FROM audits
                    WHERE COALESCE(TRIM(input_hash), '') <> ''
                    GROUP BY input_hash
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )
        result["audits_duplicate_input_hash_rows"] = int(
            scalar(
                cursor,
                """
                SELECT COALESCE(SUM(row_count), 0)::bigint FROM (
                    SELECT COUNT(*) AS row_count
                    FROM audits
                    WHERE COALESCE(TRIM(input_hash), '') <> ''
                    GROUP BY input_hash
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )
        result["audits_duplicate_input_hash_samples"] = fetch_all(
            cursor,
            """
            SELECT LEFT(input_hash, 12) AS input_hash_prefix, COUNT(*)::bigint AS count
            FROM audits
            WHERE COALESCE(TRIM(input_hash), '') <> ''
            GROUP BY input_hash
            HAVING COUNT(*) > 1
            ORDER BY count DESC, input_hash_prefix
            LIMIT 10
            """,
        )
        result["audits_with_operator_without_colaborador"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audits
                WHERE colaborador_id IS NULL
                  AND (
                    COALESCE(TRIM(operator_name), '') <> ''
                    OR COALESCE(TRIM(operator_id), '') <> ''
                  )
                """,
            )
            or 0
        )
        result["audits_invalid_colaborador_fk"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audits a
                LEFT JOIN colaboradores c ON c.id = a.colaborador_id
                WHERE a.colaborador_id IS NOT NULL
                  AND c.id IS NULL
                """,
            )
            or 0
        )
        result["audits_likely_non_json_details"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audits
                WHERE COALESCE(TRIM(details_json), '') <> ''
                  AND LEFT(TRIM(details_json), 1) NOT IN ('[', '{')
                """,
            )
            or 0
        )
        result["audits_likely_non_json_transcription"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audits
                WHERE COALESCE(TRIM(transcription_json), '') <> ''
                  AND LEFT(TRIM(transcription_json), 1) NOT IN ('[', '{')
                """,
            )
            or 0
        )
        result["audits_non_iso_timestamp_like"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audits
                WHERE COALESCE(TRIM(timestamp), '') <> ''
                  AND TRIM(timestamp) !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                """,
            )
            or 0
        )

    if table_exists(cursor, "colaboradores"):
        result["colaboradores_status_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(status, '<null>') AS status, COUNT(*)::bigint AS count
            FROM colaboradores
            GROUP BY COALESCE(status, '<null>')
            ORDER BY count DESC, status
            """,
        )
        result["colaboradores_auditavel_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(auditavel::text, '<null>') AS auditavel, COUNT(*)::bigint AS count
            FROM colaboradores
            GROUP BY COALESCE(auditavel::text, '<null>')
            ORDER BY count DESC, auditavel
            """,
        )
        result["colaboradores_duplicate_id_huawei_groups"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*) FROM (
                    SELECT id_huawei
                    FROM colaboradores
                    WHERE COALESCE(TRIM(id_huawei), '') <> ''
                    GROUP BY id_huawei
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )
        result["colaboradores_duplicate_id_huawei_samples"] = fetch_all(
            cursor,
            """
            SELECT id_huawei, COUNT(*)::bigint AS count
            FROM colaboradores
            WHERE COALESCE(TRIM(id_huawei), '') <> ''
            GROUP BY id_huawei
            HAVING COUNT(*) > 1
            ORDER BY count DESC, id_huawei
            LIMIT 20
            """,
        )
        result["colaboradores_duplicate_matricula_groups"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*) FROM (
                    SELECT matricula
                    FROM colaboradores
                    WHERE COALESCE(TRIM(matricula), '') <> ''
                    GROUP BY matricula
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )
        result["colaboradores_missing_huawei_active_auditable"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM colaboradores
                WHERE UPPER(COALESCE(status, '')) = 'ATIVO'
                  AND COALESCE(auditavel, 1) = 1
                  AND COALESCE(TRIM(id_huawei), '') = ''
                """,
            )
            or 0
        )

    if table_exists(cursor, "arquivos_salvos"):
        result["arquivos_salvos_orphans"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM arquivos_salvos s
                LEFT JOIN audits a ON a.id = s.audit_id
                WHERE s.audit_id IS NOT NULL
                  AND a.id IS NULL
                """,
            )
            or 0
        )
        result["arquivos_salvos_without_audit_id"] = int(
            scalar(cursor, "SELECT COUNT(*)::bigint FROM arquivos_salvos WHERE audit_id IS NULL")
            or 0
        )

    if table_exists(cursor, "gestor_feedbacks"):
        result["gestor_feedbacks_orphans"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM gestor_feedbacks g
                LEFT JOIN audits a ON a.id = g.audit_id
                WHERE a.id IS NULL
                """,
            )
            or 0
        )

    if table_exists(cursor, "transcript_candidates"):
        result["transcript_candidates_orphans"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM transcript_candidates t
                LEFT JOIN audits a ON a.id = t.audit_id
                WHERE t.audit_id IS NOT NULL
                  AND a.id IS NULL
                """,
            )
            or 0
        )
        result["transcript_candidates_provider_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(provider, '<null>') AS provider, COUNT(*)::bigint AS count
            FROM transcript_candidates
            GROUP BY COALESCE(provider, '<null>')
            ORDER BY count DESC, provider
            """,
        )

    if table_exists(cursor, "media_files"):
        result["media_files_backend_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(storage_backend, '<null>') AS storage_backend, COUNT(*)::bigint AS count
            FROM media_files
            GROUP BY COALESCE(storage_backend, '<null>')
            ORDER BY count DESC, storage_backend
            """,
        )
        result["media_files_missing_storage_key"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM media_files
                WHERE COALESCE(TRIM(storage_key), '') = ''
                """,
            )
            or 0
        )
        result["media_files_duplicate_file_hash_groups"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*) FROM (
                    SELECT file_hash
                    FROM media_files
                    WHERE COALESCE(TRIM(file_hash), '') <> ''
                    GROUP BY file_hash
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )

    if table_exists(cursor, "huawei_sync_logs"):
        result["huawei_sync_logs_status_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(status, '<null>') AS status, COUNT(*)::bigint AS count
            FROM huawei_sync_logs
            GROUP BY COALESCE(status, '<null>')
            ORDER BY count DESC, status
            """,
        )
        result["huawei_sync_logs_duplicate_call_id_groups"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*) FROM (
                    SELECT call_id
                    FROM huawei_sync_logs
                    WHERE COALESCE(TRIM(call_id), '') <> ''
                    GROUP BY call_id
                    HAVING COUNT(*) > 1
                ) dup
                """,
            )
            or 0
        )

    if table_exists(cursor, "huawei_d_minus_1_runs"):
        result["huawei_d_minus_1_runs_status_distribution"] = fetch_all(
            cursor,
            """
            SELECT COALESCE(status, '<null>') AS status, COUNT(*)::bigint AS count
            FROM huawei_d_minus_1_runs
            GROUP BY COALESCE(status, '<null>')
            ORDER BY count DESC, status
            """,
        )
        result["huawei_d_minus_1_runs_latest"] = fetch_all(
            cursor,
            """
            SELECT
                date_str,
                status,
                attempts,
                first_attempt_at::text AS first_attempt_at,
                last_attempt_at::text AS last_attempt_at,
                completed_at::text AS completed_at,
                manifest_csv_count,
                manifest_rows_count,
                candidates_count,
                downloaded_count,
                skipped_quota_count,
                last_error
            FROM huawei_d_minus_1_runs
            ORDER BY date_str DESC
            LIMIT 10
            """,
        )

    if table_exists(cursor, "configuracoes"):
        result["huawei_obs_config_keys"] = fetch_all(
            cursor,
            """
            SELECT
                chave,
                tipo,
                is_secret,
                CASE
                    WHEN COALESCE(TRIM(valor), '') = '' THEN false
                    ELSE true
                END AS has_value
            FROM configuracoes
            WHERE chave LIKE 'huawei_obs_%%'
               OR chave IN (
                    'huawei_d1_enabled',
                    'huawei_d1_horario_execucao',
                    'huawei_d1_lookback_dias',
                    'huawei_d1_limite_ligacoes',
                    'huawei_d1_max_retries',
                    'huawei_d1_retry_intervalo_minutos'
               )
            ORDER BY chave
            """,
        )

    if table_exists(cursor, "audit_criteria"):
        result["audit_criteria_without_alert"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audit_criteria c
                LEFT JOIN audit_alerts a ON a.id = c.alert_id
                WHERE a.id IS NULL
                """,
            )
            or 0
        )
        result["audit_alerts_without_sector"] = int(
            scalar(
                cursor,
                """
                SELECT COUNT(*)::bigint
                FROM audit_alerts a
                LEFT JOIN audit_sectors s ON s.id = a.sector_id
                WHERE s.id IS NULL
                """,
            )
            or 0
        )

    return result


def collect_performance(cursor) -> dict[str, Any]:
    return {
        "largest_tables": fetch_all(
            cursor,
            """
            SELECT
                c.relname AS table_name,
                pg_total_relation_size(c.oid) AS total_bytes,
                pg_relation_size(c.oid) AS table_bytes,
                pg_indexes_size(c.oid) AS index_bytes,
                COALESCE(s.n_live_tup, c.reltuples)::bigint AS estimated_rows,
                COALESCE(s.n_dead_tup, 0)::bigint AS estimated_dead_rows
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 15
            """,
        ),
        "low_scan_indexes": fetch_all(
            cursor,
            """
            SELECT
                relname AS table_name,
                indexrelname AS index_name,
                idx_scan,
                pg_relation_size(indexrelid) AS index_bytes
            FROM pg_stat_user_indexes
            WHERE pg_relation_size(indexrelid) > 0
              AND idx_scan = 0
            ORDER BY pg_relation_size(indexrelid) DESC, indexrelname
            LIMIT 30
            """,
        ),
        "high_dead_tuple_tables": fetch_all(
            cursor,
            """
            SELECT
                relname AS table_name,
                n_live_tup,
                n_dead_tup,
                CASE
                    WHEN n_live_tup + n_dead_tup = 0 THEN 0
                    ELSE ROUND((n_dead_tup::numeric / (n_live_tup + n_dead_tup)) * 100, 2)
                END AS dead_pct,
                last_autovacuum::text AS last_autovacuum,
                last_autoanalyze::text AS last_autoanalyze
            FROM pg_stat_user_tables
            WHERE n_dead_tup > 0
            ORDER BY n_dead_tup DESC
            LIMIT 20
            """,
        ),
    }


def collect_object_presence(cursor) -> dict[str, Any]:
    table_names = {
        row["table_name"]
        for row in fetch_all(
            cursor,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """,
        )
    }
    view_names = {
        row["table_name"]
        for row in fetch_all(
            cursor,
            """
            SELECT table_name
            FROM information_schema.views
            WHERE table_schema = 'public'
            """,
        )
    }
    return {
        "missing_critical_tables": sorted(set(CRITICAL_TABLES) - table_names),
        "present_critical_tables": sorted(set(CRITICAL_TABLES) & table_names),
        "extra_tables": sorted(table_names - set(CRITICAL_TABLES)),
        "missing_critical_views": sorted(set(CRITICAL_VIEWS) - view_names),
        "present_critical_views": sorted(set(CRITICAL_VIEWS) & view_names),
        "extra_views": sorted(view_names - set(CRITICAL_VIEWS)),
    }


def collect_review() -> dict[str, Any]:
    load_env_file(ROOT_DIR / ".env", override=False)
    load_env_file(ROOT_DIR / "backend" / ".env", override=True)
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL nao configurado.")

    connection_info = mask_url(database_url)
    conn = psycopg2.connect(database_url, cursor_factory=DictCursor)
    conn.autocommit = False
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            metadata = fetch_one(
                cursor,
                """
                SELECT
                    current_database() AS database,
                    current_schema() AS schema,
                    version() AS version,
                    now()::text AS collected_db_time
                """,
            )
            schema = collect_schema(cursor)
            object_presence = collect_object_presence(cursor)
            table_names = [row["table_name"] for row in schema["tables"]]
            counts = exact_counts(cursor, table_names)
            review = {
                "collected_at_utc": datetime.now(timezone.utc).isoformat(),
                "connection": connection_info,
                "metadata": metadata,
                "schema_metadata": collect_schema_metadata(cursor),
                "object_presence": object_presence,
                "migrations": collect_migrations(cursor),
                "schema": schema,
                "counts": counts,
                "integrity": collect_integrity(cursor),
                "performance": collect_performance(cursor),
            }
            conn.rollback()
            return review
    finally:
        conn.close()


def compact_for_terminal(review: dict[str, Any]) -> dict[str, Any]:
    schema = review["schema"]
    integrity = review["integrity"]
    return {
        "connection": review["connection"],
        "metadata": review["metadata"],
        "table_count": len(schema["tables"]),
        "view_count": len(schema["views"]),
        "extension_names": [row["extname"] for row in schema["extensions"]],
        "object_presence": review["object_presence"],
        "migrations": review["migrations"],
        "counts": review["counts"],
        "integrity": integrity,
        "largest_tables": review["performance"]["largest_tables"][:10],
        "low_scan_indexes": review["performance"]["low_scan_indexes"][:10],
        "high_dead_tuple_tables": review["performance"]["high_dead_tuple_tables"][:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only DB review.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print full JSON, including all columns/indexes/constraints.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the selected JSON payload.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print JSON to stdout. Useful when --output is used.",
    )
    args = parser.parse_args()

    review = collect_review()
    payload = review if args.full else compact_for_terminal(review)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not args.quiet:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
