"""Adiciona scripts de Logistica ausentes no catalogo DB-first.

O seed YAML atende bancos novos, mas ambientes existentes preservam o catalogo
editavel em audit_* e nao reexecutam o seed. Esta migration insere apenas os
quatro alertas solicitados pelos auditores, sem apagar edicoes manuais.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("migration.m20260519_001")

MIGRATION_NAME = "m20260519_001_add_logistica_missing_scripts"

LOGISTICA_ALERT_IDS = (
    "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI",
    "LOGISTICA-PERDA-POSICAO-CLI",
    "LOGISTICA-PARADA-EXCESSIVA-MOT",
    "LOGISTICA-PARADA-EXCESSIVA-CLI",
)


def _exists(c, query: str, params: tuple) -> bool:
    c.execute(query, params)
    return c.fetchone() is not None


def apply(c) -> None:
    from db.scoring_loader import load_scoring_rules

    rules = load_scoring_rules()
    sectors = {str(sector["id"]): sector for sector in rules.get("sectors", [])}
    alerts = {str(alert["id"]): alert for alert in rules.get("alerts", [])}

    sector = sectors.get("logistica")
    if sector and not _exists(c, "SELECT 1 FROM audit_sectors WHERE id = %s", ("logistica",)):
        c.execute(
            """
            INSERT INTO audit_sectors (id, label, description)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            ("logistica", sector.get("label", "Logistica"), sector.get("description", "")),
        )

    inserted_alerts = 0
    inserted_criteria = 0

    for alert_id in LOGISTICA_ALERT_IDS:
        alert = alerts.get(alert_id)
        if not alert:
            raise RuntimeError(f"Alerta {alert_id} nao encontrado em scoring_rules.bootstrap.yaml")

        existed = _exists(c, "SELECT 1 FROM audit_alerts WHERE id = %s", (alert_id,))
        c.execute(
            """
            INSERT INTO audit_alerts (id, sector_id, label, context, pop_ref, expected_direction)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                sector_id = EXCLUDED.sector_id,
                label = EXCLUDED.label,
                context = EXCLUDED.context,
                pop_ref = EXCLUDED.pop_ref,
                expected_direction = EXCLUDED.expected_direction
            """,
            (
                alert_id,
                alert.get("sector", "logistica"),
                alert.get("label", alert_id),
                alert.get("context", ""),
                alert.get("pop_ref"),
                alert.get("expected_direction"),
            ),
        )
        if not existed:
            inserted_alerts += 1

        for criterion in alert.get("criteria", []):
            label = str(criterion.get("label") or "").strip()
            if not label:
                continue
            if _exists(
                c,
                "SELECT 1 FROM audit_criteria WHERE alert_id = %s AND label = %s",
                (alert_id, label),
            ):
                continue
            c.execute(
                """
                INSERT INTO audit_criteria (
                    alert_id, label, description, weight, evaluation_type, deflator
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    alert_id,
                    label,
                    criterion.get("description", ""),
                    float(criterion.get("weight", 0)),
                    criterion.get("evaluation_type", "auto"),
                    float(criterion.get("deflator", 0.0)),
                ),
            )
            inserted_criteria += 1

    logger.info(
        "Scripts de Logistica adicionados: %d alertas novos, %d criterios novos.",
        inserted_alerts,
        inserted_criteria,
    )

    try:
        import core.classification as classification

        classification.load_audit_criteria_catalog.cache_clear()
        classification.build_sectors_and_alerts_prompt.cache_clear()
        classification.get_alert_lookup_by_id.cache_clear()
    except Exception:
        logger.exception("Falha ao invalidar caches de classificacao (nao critico).")
