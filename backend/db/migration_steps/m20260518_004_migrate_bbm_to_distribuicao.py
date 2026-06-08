"""Migracao BBM -> Distribuicao (v1.3.74).

Fase A (usando o cursor recebido): pre-flight + snapshot JSON em
        db/seeds/_archived/2026-05-18-bbm-sector.json.
Fase B (via repositories): cria alias em sector_aliases, deleta criterios ->
        alertas -> setor BBM via repositories.admin_criteria (audit_log
        automatico em audit_*_audit_log).
Fase C (Python pos-DB): invalida lru_cache de classification.

Idempotente: re-rodar e seguro. Cada passo verifica existencia antes.
Audit_log + snapshot_file fornecem 2 caminhos de revert.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("migration.m20260518_004")

MIGRATION_NAME = "m20260518_004_migrate_bbm_to_distribuicao"


def apply(c) -> None:
    # Imports lazy para evitar custo em deploys que nao rodem essa migration
    import db.database as database
    from db.seeds._archived.bbm_snapshot import (
        build_snapshot_payload,
        default_snapshot_path,
        dump_bbm_snapshot,
    )
    from repositories import admin_criteria, sector_aliases

    audit_kwargs = dict(
        alterado_por="system_migration_v1.3.74",
        motivo="Migracao BBM -> Distribuicao (v1.3.74)",
        origem="migration",
    )

    # ---- Fase A: pre-flight checks ---------------------------------------
    c.execute("SELECT COUNT(*) AS n FROM audits WHERE LOWER(sector_id) = 'bbm'")
    audits_bbm = (c.fetchone() or {"n": 0})["n"]
    c.execute("SELECT COUNT(*) AS n FROM colaboradores WHERE LOWER(setor) = 'bbm'")
    colab_bbm = (c.fetchone() or {"n": 0})["n"]
    if audits_bbm or colab_bbm:
        raise RuntimeError(
            f"Migracao BBM abortada: encontrados audits={audits_bbm}, "
            f"colaboradores={colab_bbm} com sector_id/setor='bbm'. "
            "Realocar manualmente antes de rodar a migracao."
        )

    # ---- Fase A: snapshot dump (idempotente) -----------------------------
    snapshot_path = default_snapshot_path()
    if not snapshot_path.exists():
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = 'bbm'")
        sector_row = c.fetchone()
        if sector_row:
            sector_payload = dict(sector_row)
            c.execute(
                "SELECT id, sector_id, label, pop_ref, context "
                "FROM audit_alerts WHERE sector_id = 'bbm' ORDER BY id"
            )
            alerts_payload = [dict(r) for r in c.fetchall()]
            c.execute(
                "SELECT id, alert_id, label, weight, description, chave "
                "FROM audit_criteria WHERE alert_id LIKE 'BBM-%%' "
                "ORDER BY alert_id, id"
            )
            criteria_payload = [dict(r) for r in c.fetchall()]
            payload = build_snapshot_payload(
                sector_payload, alerts_payload, criteria_payload
            )
            dump_bbm_snapshot(payload, snapshot_path)
            logger.info(
                "Snapshot BBM gravado em %s (%d alertas, %d criterios).",
                snapshot_path, len(alerts_payload), len(criteria_payload),
            )
        else:
            logger.info(
                "Setor 'bbm' nao existe no DB; pulando snapshot (re-run idempotente)."
            )

    # ---- Fase B.3: insert alias (se nao existir) -------------------------
    existing_aliases = sector_aliases.list_aliases(database.get_connection)
    has_alias = any(
        a["pattern_type"] == "setor_exact"
        and a["pattern_value"] == "bbm"
        and a["canonical_sector_id"] == "distribuicao"
        for a in existing_aliases
    )
    if not has_alias:
        sector_aliases.create_alias(
            database.get_connection,
            pattern_type="setor_exact",
            pattern_value="bbm",
            canonical_sector_id="distribuicao",
            priority=100,
            descricao="Migracao BBM -> Distribuicao em 2026-05-18",
            ativo=True,
            **audit_kwargs,
        )
        logger.info("Alias bbm -> distribuicao criado em sector_aliases.")

    # ---- Fase B.4a: delete criterios -------------------------------------
    c.execute(
        "SELECT id FROM audit_criteria WHERE alert_id LIKE 'BBM-%%' ORDER BY id"
    )
    criterion_ids = [row["id"] for row in c.fetchall()]
    for cid in criterion_ids:
        admin_criteria.delete_criterion(database.get_connection, cid, **audit_kwargs)
    if criterion_ids:
        logger.info("Removidos %d criterios BBM-*.", len(criterion_ids))

    # ---- Fase B.4b: delete alertas ---------------------------------------
    c.execute("SELECT id FROM audit_alerts WHERE sector_id = 'bbm' ORDER BY id")
    alert_ids = [row["id"] for row in c.fetchall()]
    for aid in alert_ids:
        admin_criteria.delete_alert(database.get_connection, aid, **audit_kwargs)
    if alert_ids:
        logger.info("Removidos %d alertas BBM-*.", len(alert_ids))

    # ---- Fase B.4c: delete setor -----------------------------------------
    c.execute("SELECT 1 FROM audit_sectors WHERE id = 'bbm'")
    if c.fetchone():
        admin_criteria.delete_sector(database.get_connection, "bbm", **audit_kwargs)
        logger.info("Setor 'bbm' removido de audit_sectors.")

    # ---- Fase C: invalidar caches Python ---------------------------------
    try:
        import core.classification as classification
        classification.load_audit_criteria_catalog.cache_clear()
        classification.build_sectors_and_alerts_prompt.cache_clear()
        classification.get_alert_lookup_by_id.cache_clear()
    except Exception:
        logger.exception(
            "Falha ao invalidar lru_cache de classification (nao critico)."
        )
    sector_aliases.clear_cache()
