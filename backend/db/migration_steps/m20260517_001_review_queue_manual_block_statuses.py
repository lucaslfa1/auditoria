"""Registra os novos estados operacionais da fila de revisao.

O Postgres atual valida os estados da fila na camada de aplicacao, mas manter
esta migracao evita que ambientes ja provisionados fiquem sem rastro explicito
de schema quando `needs_manual_triage` e `blocked_operator` entram em uso.
"""

from db.domain_constants import REVIEW_QUEUE_STATUSES
from db.schema_tools import set_schema_metadata


MIGRATION_NAME = "m20260517_001_review_queue_manual_block_statuses"


def apply(c):
    set_schema_metadata(
        c,
        "schema.review_queue_statuses",
        ",".join(REVIEW_QUEUE_STATUSES),
    )
