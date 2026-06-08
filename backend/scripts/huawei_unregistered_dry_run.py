"""Dry-run report for Huawei queue items without an official Huawei operator ID.

This script is intentionally read-only. It helps identify legacy Huawei queue
rows that were downloaded before the sync required a registered id_huawei match.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
load_dotenv(ROOT_DIR / ".env", override=False)
load_dotenv(BACKEND_DIR / ".env", override=True)

import db.database as database  # noqa: E402
from core.huawei.download_candidates import _clean_huawei_operator_id, _normalize_identity_text  # noqa: E402
from core.huawei_discovery import HuaweiDiscoveryService  # noqa: E402
from repositories import operators  # noqa: E402
from repositories.common import json_loads  # noqa: E402


SP_TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_HIGHLIGHT_LOCAL = "29/04/2026 23:30"
TERMINAL_QUEUE_STATUSES = ("audited", "monthly_capped")
HUAWEI_ID_METADATA_KEYS = (
    "operator_id_huawei_real",
    "id_huawei",
    "operator_id",
    "huawei_agent_id",
    "huawei_work_no",
    "agent_id",
    "agentId",
    "agentid",
    "workNo",
    "work_no",
    "operatorId",
    "operator_id_huawei",
    "idHuawei",
)


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, "keys"):
        return row[key] if key in row.keys() else default
    return default


def _coerce_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    parsed = json_loads(value, {})
    return parsed if isinstance(parsed, dict) else {}


def extract_candidate_huawei_ids(metadata: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for key in HUAWEI_ID_METADATA_KEYS:
        raw_value = metadata.get(key)
        values = raw_value if isinstance(raw_value, (list, tuple, set)) else (raw_value,)
        for value in values:
            candidate = _clean_huawei_operator_id(value)
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            result.append(candidate)
    return result


def build_official_indexes(official_operators: Iterable[dict[str, Any]]) -> tuple[set[str], set[str]]:
    official_ids: set[str] = set()
    official_names: set[str] = set()
    for operador in official_operators:
        id_huawei = _clean_huawei_operator_id(operador.get("id_huawei") or operador.get("idHuawei"))
        if id_huawei:
            official_ids.add(id_huawei)
        name_key = _normalize_identity_text(operador.get("nome") or operador.get("name"))
        if name_key:
            official_names.add(name_key)
    return official_ids, official_names


def _coerce_local_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SP_TZ)
        return parsed.astimezone(SP_TZ)

    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=SP_TZ)
            except ValueError:
                continue

    millis = HuaweiDiscoveryService._coerce_huawei_time_ms(value)
    if millis is None:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).astimezone(SP_TZ)


def _format_local_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d/%m/%Y %H:%M:%S") if value else ""


def _highlight_prefix(value: str) -> str:
    return str(value or "").replace(",", "").strip()


def build_unregistered_items(
    rows: Iterable[Any],
    official_operators: Iterable[dict[str, Any]],
    *,
    highlight_local: str = DEFAULT_HIGHLIGHT_LOCAL,
) -> list[dict[str, Any]]:
    official_ids, official_names = build_official_indexes(official_operators)
    highlight = _highlight_prefix(highlight_local)
    items: list[dict[str, Any]] = []

    for row in rows:
        metadata = _coerce_metadata(_row_value(row, "metadata_json") or _row_value(row, "metadata"))
        candidate_ids = extract_candidate_huawei_ids(metadata)
        if any(candidate in official_ids for candidate in candidate_ids):
            continue

        operator_name = (
            _row_value(row, "operador_previsto")
            or metadata.get("operator_name")
            or metadata.get("operator_name_real")
            or metadata.get("huawei_operator_name")
            or ""
        )
        local_dt = _coerce_local_datetime(
            metadata.get("huawei_begin_time")
            or metadata.get("beginTime")
            or metadata.get("callBegin")
        )
        local_text = _format_local_datetime(local_dt)
        operator_name_key = _normalize_identity_text(operator_name)
        items.append(
            {
                "id": _row_value(row, "id"),
                "input_hash": _row_value(row, "input_hash"),
                "nome_arquivo": _row_value(row, "nome_arquivo"),
                "status": _row_value(row, "status"),
                "operador": str(operator_name or "").strip(),
                "candidate_huawei_ids": candidate_ids,
                "huawei_call_id": metadata.get("huawei_call_id") or metadata.get("callId"),
                "huawei_begin_time": metadata.get("huawei_begin_time"),
                "call_started_at_sp": local_text,
                "duration": metadata.get("huawei_duration") or metadata.get("duration"),
                "audio_path": metadata.get("classified_audio_path") or metadata.get("classified_file_path"),
                "name_matches_official": bool(operator_name_key and operator_name_key in official_names),
                "reported_match": bool(highlight and local_text.startswith(highlight)),
            }
        )

    return items


def fetch_huawei_queue_rows(*, limit: int, include_final: bool) -> list[dict[str, Any]]:
    filters = ["metadata_json::jsonb ->> 'origem' = 'huawei_sync'"]
    params: list[Any] = []
    if not include_final:
        filters.append("COALESCE(status, '') <> ALL(%s)")
        params.append(list(TERMINAL_QUEUE_STATUSES))

    where_clause = " AND ".join(filters)
    limit_clause = "LIMIT %s" if limit > 0 else ""
    if limit > 0:
        params.append(limit)

    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, input_hash, nome_arquivo, setor_previsto, alerta_previsto,
                   confianca, operador_previsto, status, criado_em, atualizado_em,
                   metadata_json
            FROM fila_revisao_classificacao
            WHERE {where_clause}
            ORDER BY atualizado_em DESC, id DESC
            {limit_clause}
            """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def _print_text_report(payload: dict[str, Any]) -> None:
    print("Dry-run Huawei sem operador oficial - nenhum dado foi alterado.")
    print(f"Linhas Huawei lidas: {payload['rows_read']}")
    print(f"Operadores oficiais com id_huawei: {payload['official_operator_ids']}")
    print(f"Itens sem id_huawei oficial na fila: {payload['unregistered_count']}")
    print(f"Ocorrencias no horario reportado: {payload['highlight_count']}")
    if not payload["items"]:
        return
    print("")
    for item in payload["items"]:
        marker = " [HORARIO REPORTADO]" if item["reported_match"] else ""
        ids = ", ".join(item["candidate_huawei_ids"]) or "sem ID"
        print(
            f"-{marker} id={item['id']} status={item['status']} "
            f"data={item['call_started_at_sp'] or 'sem data'} operador=\"{item['operador'] or 'sem nome'}\" "
            f"ids={ids} call_id={item['huawei_call_id'] or 'sem call_id'} "
            f"hash={item['input_hash']} arquivo={item['nome_arquivo']}"
        )
        if item["name_matches_official"]:
            print("  nome bate com colaborador oficial, mas o ID Huawei da chamada nao bate.")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=1000, help="Numero maximo de linhas Huawei a ler; 0 remove limite.")
    parser.add_argument("--include-final", action="store_true", help="Inclui itens finalizados/auditados no relatorio.")
    parser.add_argument("--highlight-local", default=DEFAULT_HIGHLIGHT_LOCAL, help="Horario local a destacar, formato DD/MM/AAAA HH:MM.")
    parser.add_argument("--json", action="store_true", help="Imprime o relatorio em JSON.")
    args = parser.parse_args(argv)

    official_operators = operators.listar_auditaveis_com_id_huawei(database.get_connection)
    rows = fetch_huawei_queue_rows(limit=args.limit, include_final=args.include_final)
    official_ids, _ = build_official_indexes(official_operators)
    items = build_unregistered_items(rows, official_operators, highlight_local=args.highlight_local)
    payload = {
        "dry_run": True,
        "rows_read": len(rows),
        "official_operator_ids": len(official_ids),
        "unregistered_count": len(items),
        "highlight_local": args.highlight_local,
        "highlight_count": sum(1 for item in items if item["reported_match"]),
        "items": items,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text_report(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
