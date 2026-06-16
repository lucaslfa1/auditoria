"""Export/serialização do catálogo de critérios (formato auditCriteria.json).

Subdomínio coeso extraído de `repositories/admin_criteria.py` (v1.3.166) sem
mudança de comportamento: leitura defensiva das tabelas audit_sectors/
audit_alerts/audit_criteria (tolerante a colunas ausentes em DBs antigos) e
montagem da hierarquia setor->alerta->critério, incluindo a regra de negócio dos
setores de risco operacional que compartilham alertas com 'bas' (POP 4.1).

Os nomes seguem reexportados de `repositories.admin_criteria` (o router usa
get_export_format; os getters/CRUD usam _with_row_factory). `_with_row_factory`
mora aqui e é reexportado de volta — quebra o ciclo de import.
"""

from typing import Any

from psycopg2 import sql


def _with_row_factory(conn):
    """Ensure dict(row) works on fetched rows."""

    return conn


def _get_existing_columns(cursor: Any, table_name: str) -> set[str]:
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table_name,))
    return {str(row[0]) for row in cursor.fetchall()}


def _safe_select_rows(
    cursor: Any,
    table_name: str,
    required_columns: list[str],
    optional_columns: list[str],
) -> list[dict]:
    existing_columns = _get_existing_columns(cursor, table_name)
    selected_columns = [column for column in required_columns + optional_columns if column in existing_columns]
    # Identificadores via psycopg2.sql (defesa em profundidade): os nomes ja
    # vem de whitelist interna + information_schema, mas o quoting formal
    # elimina a classe de injecao caso um caller futuro passe input externo.
    query = sql.SQL("SELECT {columns} FROM {table}").format(
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in selected_columns),
        table=sql.Identifier(table_name),
    )
    cursor.execute(query)
    rows = [dict(row) for row in cursor.fetchall()]

    missing_columns = [column for column in optional_columns if column not in existing_columns]
    for row in rows:
        for column in missing_columns:
            row[column] = None

    return rows


def get_export_format(db_connection_factory):
    """Returns the JSON structure compatible with auditCriteria.json"""
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        sectors_rows = _safe_select_rows(
            c,
            "audit_sectors",
            required_columns=["id", "label"],
            optional_columns=["description"],
        )

        alerts_rows = _safe_select_rows(
            c,
            "audit_alerts",
            required_columns=["id", "sector_id", "label"],
            optional_columns=["context", "pop_ref"],
        )

        criteria_rows = _safe_select_rows(
            c,
            "audit_criteria",
            required_columns=["id", "alert_id", "label", "weight"],
            optional_columns=["chave", "description", "type", "deflator", "evaluation_type", "referencia", "exemplo"],
        )

        # Build hierarchy
        alerts_by_sector = {}
        for a in alerts_rows:
            s_id = a["sector_id"]
            if s_id not in alerts_by_sector:
                alerts_by_sector[s_id] = []
            alerts_by_sector[s_id].append({
                "id": a["id"],
                "label": a["label"],
                "context": a["context"],
                "criteria": []
            })

        # Optimize lookup: we need the original full a.id string to match criteria
        alerts_map = {a["id"]: a for a in alerts_rows}

        # Create dictionaries by target ID for O(1) appending
        export_data = {"sectors": []}
        built_alerts = {}
        for a in alerts_rows:
            built_alerts[a["id"]] = {
                "id": a["id"],
                "label": a["label"],
                "context": a.get("context"),
                "pop_ref": a.get("pop_ref"),
                "criteria": []
            }

        for c_row in criteria_rows:
            a_id = c_row["alert_id"]
            if a_id in built_alerts:
                chave_val = c_row.get("chave")
                crit_id = chave_val if chave_val else f"crit_{c_row.get('id', 'unknown')}"

                # Resolvendo type e deflator de forma segura (pois as versões antigas do DB podem não ter a coluna ou retornar null/None)
                crit_type = c_row.get("type") if c_row.get("type") else "boolean"
                crit_deflator = c_row.get("deflator") if c_row.get("deflator") is not None else 0.0

                built_alerts[a_id]["criteria"].append({
                    "id": crit_id,
                    "label": c_row["label"],
                    "description": c_row.get("description"),
                    "weight": c_row["weight"],
                    "type": crit_type,
                    "deflator": crit_deflator,
                    "referencia": c_row.get("referencia"),
                    "exemplo": c_row.get("exemplo"),
                    "evaluation_type": c_row.get("evaluation_type") or "auto",
                })

        # Group alerts by sector
        alerts_by_sector_map = {}
        for a in alerts_rows:
            s_id = a["sector_id"]
            if s_id not in alerts_by_sector_map:
                alerts_by_sector_map[s_id] = []
            alerts_by_sector_map[s_id].append(built_alerts[a["id"]])

        # ── Operational risk sectors share alerts with BAS ────────────────
        # Per POP 4.1: Transferência, UTI, BAS, Distribuição and Fênix
        # all share the same risk alerts (4.1.x). In the DB, these alerts
        # are stored under sector_id='bas'. Replicate them to sibling sectors.
        OPERATIONAL_RISK_SECTORS = {"transferencia", "uti", "distribuicao", "fenix"}
        bas_alerts = alerts_by_sector_map.get("bas", [])
        if bas_alerts:
            for risk_sector_id in OPERATIONAL_RISK_SECTORS:
                if risk_sector_id not in alerts_by_sector_map:
                    alerts_by_sector_map[risk_sector_id] = list(bas_alerts)
                else:
                    # Append BAS alerts that are not already present
                    existing_ids = {a["id"] for a in alerts_by_sector_map[risk_sector_id]}
                    for ba in bas_alerts:
                        if ba["id"] not in existing_ids:
                            alerts_by_sector_map[risk_sector_id].append(ba)

        for s in sectors_rows:
            s_id = s["id"]
            export_data["sectors"].append({
                "id": s_id,
                "label": s["label"],
                "description": s.get("description"),
                "alerts": alerts_by_sector_map.get(s_id, [])
            })

        return export_data
    finally:
        conn.close()
