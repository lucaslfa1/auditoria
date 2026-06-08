"""Script de reverter: re-insere BBM no DB a partir do snapshot.

Uso: python backend/db/seeds/_archived/restore_bbm.py

Idempotente nas verificacoes de existencia previa (create_* dos repositories).
Remove o alias bbm -> distribuicao se existir. Grava no audit_log com motivo
`Restore BBM via snapshot 2026-05-18`.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Permite rodar como script direto: python backend/db/seeds/_archived/restore_bbm.py
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from db.seeds._archived.bbm_snapshot import default_snapshot_path, load_bbm_snapshot

logger = logging.getLogger("restore_bbm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    load_dotenv()
    from db.database import get_connection
    from repositories import sector_aliases
    from repositories import admin_criteria

    snapshot_path = default_snapshot_path()
    if not snapshot_path.exists():
        logger.error("Snapshot nao encontrado em %s", snapshot_path)
        return 1

    snapshot = load_bbm_snapshot(snapshot_path)
    sector = snapshot["sector"]
    alerts = snapshot["alerts"]
    criteria = snapshot["criteria"]

    audit_kwargs = dict(
        alterado_por="system_restore_v1.3.74",
        motivo="Restore BBM via snapshot 2026-05-18",
        origem="script",
    )

    admin_criteria.create_sector(
        get_connection,
        id=sector["id"],
        label=sector["label"],
        description=sector.get("description", ""),
        **audit_kwargs,
    )
    for alert in alerts:
        admin_criteria.create_alert(
            get_connection,
            sector_id=alert["sector_id"],
            id=alert["id"],
            label=alert["label"],
            pop_ref=alert.get("pop_ref", ""),
            context=alert.get("context", ""),
            **audit_kwargs,
        )
    for criterion in criteria:
        admin_criteria.create_criterion(
            get_connection,
            alert_id=criterion["alert_id"],
            label=criterion["label"],
            weight=float(criterion.get("weight", 0)),
            description=criterion.get("description", ""),
            chave=criterion.get("chave"),
            **audit_kwargs,
        )

    aliases = sector_aliases.list_aliases(get_connection)
    for alias in aliases:
        if (
            alias["pattern_type"] == "setor_exact"
            and alias["pattern_value"] == "bbm"
            and alias["canonical_sector_id"] == "distribuicao"
        ):
            sector_aliases.delete_alias(get_connection, alias["id"], **audit_kwargs)
            break

    sector_aliases.clear_cache()
    logger.info(
        "Restore concluido: 1 setor + %d alertas + %d criterios + alias removido.",
        len(alerts),
        len(criteria),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
