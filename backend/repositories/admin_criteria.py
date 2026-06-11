import logging
from typing import Optional, Any

from psycopg2 import sql

from repositories.common import extract_returning_id

logger = logging.getLogger(__name__)


_VALID_ORIGINS = {"ui", "api", "seed", "script", "system", "migration"}
_AUDIT_LOG_TABLES = {
    "sector": "audit_sectors_audit_log",
    "alert": "audit_alerts_audit_log",
    "criterion": "audit_criteria_audit_log",
}


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


def _validate_audit_args(alterado_por: str, origem: str, op_label: str) -> bool:
    """Common validation for the three audit-log args. Returns True iff valid."""
    if not alterado_por or not str(alterado_por).strip():
        logger.error("%s rejeitado: alterado_por obrigatorio", op_label)
        return False
    if origem not in _VALID_ORIGINS:
        logger.error("%s rejeitado: origem invalida '%s'", op_label, origem)
        return False
    return True


def _log_change(
    cursor: Any,
    *,
    entity_type: str,
    acao: str,
    entity_id: str,
    payload_antes: Optional[dict],
    payload_depois: Optional[dict],
    alterado_por: str,
    motivo: str,
    origem: str,
) -> None:
    """INSERT into the appropriate *_audit_log table. Same transaction as caller.

    Idempotent at the call-site sense: caller decides when to log (e.g., skip on
    no-op updates). entity_id is normalized to TEXT so all 3 tables share schema.
    """
    from psycopg2.extras import Json

    table = _AUDIT_LOG_TABLES[entity_type]
    cursor.execute(
        f"""
        INSERT INTO {table}
            (acao, entity_id, payload_antes, payload_depois, alterado_por, motivo, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            acao,
            str(entity_id),
            Json(payload_antes) if payload_antes is not None else None,
            Json(payload_depois) if payload_depois is not None else None,
            str(alterado_por).strip(),
            (motivo or "").strip() or None,
            origem,
        ),
    )


def get_sectors(db_connection_factory):
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors ORDER BY label")
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_alerts(db_connection_factory, sector_id: Optional[str] = None):
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        if sector_id:
            c.execute(
                "SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE sector_id = %s ORDER BY label",
                (sector_id,),
            )
        else:
            c.execute(
                "SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts ORDER BY sector_id, label"
            )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_criteria(db_connection_factory, alert_id: Optional[str] = None):
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        if alert_id:
            c.execute(
                """
                SELECT id, alert_id, chave, label, weight, description, type,
                       deflator, referencia, exemplo, evaluation_type
                FROM audit_criteria
                WHERE alert_id = %s
                ORDER BY id
                """,
                (alert_id,),
            )
        else:
            c.execute(
                """
                SELECT id, alert_id, chave, label, weight, description, type,
                       deflator, referencia, exemplo, evaluation_type
                FROM audit_criteria
                ORDER BY alert_id, id
                """
            )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

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

# CRUD Operations (todas com audit_log na mesma transacao)

def create_sector(
    db_connection_factory,
    id: str,
    label: str,
    description: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> bool:
    if not _validate_audit_args(alterado_por, origem, "create_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_sectors (id, label, description) VALUES (%s, %s, %s)",
            (id, label, description),
        )
        _log_change(
            c,
            entity_type="sector",
            acao="create",
            entity_id=id,
            payload_antes=None,
            payload_depois={"id": id, "label": label, "description": description},
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return True
    except Exception:
        logger.exception("create_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_sector(
    db_connection_factory,
    id: str,
    label: str,
    description: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "update_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        depois = {"id": id, "label": label, "description": description}
        if antes == depois:
            return True  # no-op silencioso, nao polui audit_log
        c.execute(
            "UPDATE audit_sectors SET label = %s, description = %s WHERE id = %s",
            (label, description, id),
        )
        _log_change(
            c,
            entity_type="sector",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("update_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def get_sector_members(db_connection_factory, sector_id: str) -> list[dict]:
    """Colaboradores cujo setor resolve (via sector_aliases) para `sector_id`.

    Read-only. Fonte unica da "associacao funcionario->setor": usada tanto pelo
    preview `/members` quanto pela cascata de rename. A vinculacao e implicita
    (string `colaboradores.setor` -> mapa de apelidos -> `audit_sectors.id`), nunca
    pelo rotulo de exibicao.
    """
    from repositories import sector_aliases as _sa

    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        rules = _sa.list_active_rules(db_connection_factory)
        c.execute(
            """
            SELECT id, nome, setor, escala, supervisor, organizacao_telefonia
              FROM colaboradores
             ORDER BY nome
            """
        )
        members: list[dict] = []
        for raw in c.fetchall():
            colab = dict(raw)
            canon = _sa.match_canonical_sector(
                rules,
                setor=colab.get("setor") or "",
                escala=colab.get("escala") or "",
                supervisor=colab.get("supervisor") or "",
                organizacao=colab.get("organizacao_telefonia") or "",
            )
            if canon == sector_id:
                members.append(
                    {"id": colab["id"], "nome": colab.get("nome"), "setor": colab.get("setor")}
                )
        return members
    finally:
        conn.close()


def rename_sector_with_cascade(
    db_connection_factory,
    sector_id: str,
    new_label: str,
    description: Optional[str] = None,
    *,
    cascade: bool = True,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> Optional[dict]:
    """Renomeia o rotulo de um setor e, se `cascade`, propaga o novo nome para todos
    os colaboradores vinculados — mantendo as regras de auditoria intactas.

    O `id` do setor (chave a que `audit_alerts.sector_id` aponta) NUNCA muda; por
    isso a auditoria nao e afetada. Passos, numa unica transacao de escrita:
      1. `UPDATE audit_sectors.label/description`;
      2. detecta membros (`get_sector_members`) e faz bulk `UPDATE colaboradores.setor`
         para o novo nome, com snapshot pre/pos em `colaboradores_audit_log`;
      3. garante um alias `setor_exact` (_norm(new_label) -> sector_id) com prioridade
         alta, para o novo nome continuar resolvendo ao mesmo `sector_id`;
      4. registra a mudanca em `audit_sectors_audit_log` (com resumo da cascata).

    Retorna {"affected": int, "label": str} ou None se o setor nao existe.
    """
    if not _validate_audit_args(alterado_por, origem, "rename_sector_with_cascade"):
        return None

    new_label = (new_label or "").strip()
    if not new_label:
        logger.error("rename_sector_with_cascade rejeitado: new_label vazio")
        return None

    from repositories import sector_aliases as _sa
    from repositories.operators import _snapshot_colaborador, _log_colaborador_audit

    # Deteccao (read-only) antes da transacao de escrita — exclui quem ja esta no nome novo.
    affected_ids: list[int] = []
    if cascade:
        affected_ids = [
            int(m["id"])
            for m in get_sector_members(db_connection_factory, sector_id)
            if (m.get("setor") or "") != new_label
        ]

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (sector_id,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return None
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        c.execute(
            "UPDATE audit_sectors SET label = %s, description = %s WHERE id = %s",
            (new_label, description, sector_id),
        )

        if cascade and affected_ids:
            snapshots_before = {cid: _snapshot_colaborador(c, cid) for cid in affected_ids}
            c.execute(
                "UPDATE colaboradores SET setor = %s, atualizado_em = CURRENT_TIMESTAMP "
                "WHERE id = ANY(%s)",
                (new_label, affected_ids),
            )
            cascade_motivo = motivo or f"rename setor '{antes['label']}' -> '{new_label}'"
            for cid in affected_ids:
                _log_colaborador_audit(
                    c,
                    acao="update",
                    entity_id=cid,
                    payload_antes=snapshots_before.get(cid),
                    payload_depois=_snapshot_colaborador(c, cid),
                    alterado_por=alterado_por,
                    motivo=cascade_motivo,
                    origem=origem,
                )

        if cascade:
            # Garante que o novo nome resolva para este sector_id (regras intactas).
            norm_label = _sa._norm(new_label)
            if norm_label:
                c.execute(
                    "SELECT 1 FROM sector_aliases "
                    "WHERE pattern_type = 'setor_exact' AND pattern_value = %s "
                    "AND canonical_sector_id = %s AND ativo",
                    (norm_label, sector_id),
                )
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO sector_aliases "
                        "(pattern_type, pattern_value, canonical_sector_id, priority, descricao, ativo) "
                        "VALUES ('setor_exact', %s, %s, %s, %s, TRUE)",
                        (norm_label, sector_id, 200, f"auto: rename setor -> {new_label}"),
                    )

        _log_change(
            c,
            entity_type="sector",
            acao="update",
            entity_id=sector_id,
            payload_antes=antes,
            payload_depois={
                "id": sector_id,
                "label": new_label,
                "description": description,
                "cascade": cascade,
                "affected_colaboradores": len(affected_ids),
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return {"affected": len(affected_ids), "label": new_label}
    except Exception:
        logger.exception("rename_sector_with_cascade falhou (id=%s)", sector_id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
        try:
            _sa.clear_cache()  # novo alias publicado -> invalida cache de regras
        except Exception:
            pass


def delete_sector(
    db_connection_factory,
    id: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "delete_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        c.execute("DELETE FROM audit_sectors WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="sector",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def create_alert(
    db_connection_factory,
    sector_id: str,
    label: str,
    context: Optional[str] = None,
    original_id: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
    pop_ref: Optional[str] = None,
    expected_direction: Optional[str] = None,
):
    if not _validate_audit_args(alterado_por, origem, "create_alert"):
        return None

    import uuid
    if original_id:
        a_id = f"{sector_id}::{original_id}"
    else:
        a_id = f"{sector_id}::{uuid.uuid4().hex[:8]}"

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_alerts (id, sector_id, label, context, pop_ref, expected_direction) VALUES (%s, %s, %s, %s, %s, %s)",
            (a_id, sector_id, label, context, pop_ref, expected_direction),
        )
        _log_change(
            c,
            entity_type="alert",
            acao="create",
            entity_id=a_id,
            payload_antes=None,
            payload_depois={
                "id": a_id, "sector_id": sector_id, "label": label,
                "context": context, "pop_ref": pop_ref, "expected_direction": expected_direction,
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return a_id
    except Exception:
        logger.exception("create_alert falhou (sector_id=%s, label=%s)", sector_id, label)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_alert(
    db_connection_factory,
    id: str,
    label: str,
    context: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
    pop_ref: Optional[str] = None,
    expected_direction: Optional[str] = None,
):
    if not _validate_audit_args(alterado_por, origem, "update_alert"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "sector_id": row[1], "label": row[2],
            "context": row[3], "pop_ref": row[4], "expected_direction": row[5]
        }
        # pop_ref e expected_direction nao mexido a nao ser que o caller passe explicitamente
        new_pop_ref = pop_ref if pop_ref is not None else row[4]
        new_expected_direction = expected_direction if expected_direction is not None else row[5]
        depois = {
            "id": id, "sector_id": row[1], "label": label,
            "context": context, "pop_ref": new_pop_ref, "expected_direction": new_expected_direction
        }
        if antes == depois:
            return True
        c.execute(
            "UPDATE audit_alerts SET label = %s, context = %s, pop_ref = %s, expected_direction = %s WHERE id = %s",
            (label, context, new_pop_ref, new_expected_direction, id),
        )
        _log_change(
            c,
            entity_type="alert",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("update_alert falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def delete_alert(
    db_connection_factory,
    id: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "delete_alert"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "sector_id": row[1], "label": row[2],
            "context": row[3], "pop_ref": row[4], "expected_direction": row[5]
        }
        c.execute("DELETE FROM audit_alerts WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="alert",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_alert falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def create_criterion(
    db_connection_factory,
    alert_id: str,
    chave: str,
    label: str,
    weight: float,
    description: Optional[str] = None,
    type: str = "boolean",
    deflator: float = 0,
    referencia: Optional[str] = None,
    exemplo: Optional[str] = None,
    evaluation_type: str = "auto",
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "create_criterion"):
        return None
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_criteria (alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type),
        )
        new_id = extract_returning_id(c.fetchone())
        _log_change(
            c,
            entity_type="criterion",
            acao="create",
            entity_id=new_id,
            payload_antes=None,
            payload_depois={
                "id": new_id, "alert_id": alert_id, "chave": chave, "label": label,
                "weight": weight, "description": description, "type": type,
                "deflator": deflator, "referencia": referencia, "exemplo": exemplo,
                "evaluation_type": evaluation_type,
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return new_id
    except Exception:
        logger.exception("create_criterion falhou (alert_id=%s, chave=%s)", alert_id, chave)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_criterion(
    db_connection_factory,
    id: int,
    chave: str,
    label: str,
    weight: float,
    description: Optional[str] = None,
    type: str = "boolean",
    deflator: float = 0,
    referencia: Optional[str] = None,
    exemplo: Optional[str] = None,
    evaluation_type: str = "auto",
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "update_criterion"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type FROM audit_criteria WHERE id = %s",
            (id,),
        )
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "alert_id": row[1], "chave": row[2], "label": row[3],
            "weight": row[4], "description": row[5], "type": row[6],
            "deflator": row[7], "referencia": row[8], "exemplo": row[9],
            "evaluation_type": row[10],
        }
        depois = {
            "id": id, "alert_id": row[1], "chave": chave, "label": label,
            "weight": weight, "description": description, "type": type,
            "deflator": deflator, "referencia": referencia, "exemplo": exemplo,
            "evaluation_type": evaluation_type,
        }
        if antes == depois:
            return True
        c.execute(
            "UPDATE audit_criteria SET chave = %s, label = %s, weight = %s, description = %s, type = %s, deflator = %s, referencia = %s, exemplo = %s, evaluation_type = %s WHERE id = %s",
            (chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type, id),
        )
        _log_change(
            c,
            entity_type="criterion",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("update_criterion falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def delete_criterion(
    db_connection_factory,
    id: int,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    if not _validate_audit_args(alterado_por, origem, "delete_criterion"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type FROM audit_criteria WHERE id = %s",
            (id,),
        )
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "alert_id": row[1], "chave": row[2], "label": row[3],
            "weight": row[4], "description": row[5], "type": row[6],
            "deflator": row[7], "referencia": row[8], "exemplo": row[9],
            "evaluation_type": row[10],
        }
        c.execute("DELETE FROM audit_criteria WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="criterion",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_criterion falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def list_audit_log(
    db_connection_factory,
    *,
    entity_type: str,
    entity_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Lista as ultimas mudancas em sector/alert/criterion, mais recentes primeiro.

    `entity_type` deve ser 'sector', 'alert' ou 'criterion'. Filtra por `entity_id`
    se informado. `limit` clampado em [1, 500].
    """
    import psycopg2.extras
    if entity_type not in _AUDIT_LOG_TABLES:
        return []
    table = _AUDIT_LOG_TABLES[entity_type]
    safe_limit = max(1, min(int(limit or 50), 500))
    conn = db_connection_factory()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if entity_id:
            cursor.execute(
                f"""
                SELECT id, acao, entity_id, payload_antes, payload_depois,
                       alterado_por, alterado_em, motivo, origem
                  FROM {table}
                 WHERE entity_id = %s
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (str(entity_id), safe_limit),
            )
        else:
            cursor.execute(
                f"""
                SELECT id, acao, entity_id, payload_antes, payload_depois,
                       alterado_por, alterado_em, motivo, origem
                  FROM {table}
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (safe_limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        logger.exception("list_audit_log falhou (entity_type=%s)", entity_type)
        return []
    finally:
        conn.close()
