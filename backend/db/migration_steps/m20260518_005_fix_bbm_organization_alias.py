"""Corrige alias Huawei BBM para Distribuicao.

A migracao v1.3.74 removeu BBM como setor operacional e criou alias
`setor_exact: bbm -> distribuicao`, mas a regra legada de organizacao Huawei
`organizacao_contains: bbm -> transferencia` continuou ativa. Esta migration
alinha a origem Huawei com a decisao operacional: qualquer BBM deve cair em
Distribuicao.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("migration.m20260518_005")

MIGRATION_NAME = "m20260518_005_fix_bbm_organization_alias"


def apply(c) -> None:
    import db.database as database
    from repositories import sector_aliases

    aliases = sector_aliases.list_aliases(database.get_connection)
    target_aliases = [
        alias
        for alias in aliases
        if alias["pattern_type"] == "organizacao_contains"
        and alias["pattern_value"] == "bbm"
        and alias.get("ativo", True)
    ]

    for alias in target_aliases:
        if alias["canonical_sector_id"] == "distribuicao":
            continue
        sector_aliases.update_alias(
            database.get_connection,
            alias["id"],
            canonical_sector_id="distribuicao",
            descricao="Organizacao Huawei 'BBM' absorvida por Distribuicao",
            alterado_por="system_migration_v1.3.75",
            motivo="Correcao residual da migracao BBM -> Distribuicao: organizacao Huawei BBM nao deve cair em transferencia.",
            origem="migration",
        )
        logger.info(
            "Alias organizacao_contains/bbm atualizado: %s -> distribuicao.",
            alias["canonical_sector_id"],
        )

    sector_aliases.clear_cache()
