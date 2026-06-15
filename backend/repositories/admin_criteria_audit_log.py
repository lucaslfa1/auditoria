"""Trilha de auditoria das telas de Critérios (setores/alertas/critérios).

Primitivas compartilhadas pelas operações de escrita de `admin_criteria`:
validação dos argumentos de auditoria e o INSERT na tabela `*_audit_log`
correspondente (na mesma transação do caller). Extraído de
`repositories.admin_criteria` (que reexporta estes nomes p/ compat).

Obs.: `sector_aliases.py` e `configuration.py` mantêm cópias próprias deste
padrão; unificá-las aqui é um passo futuro (exige confirmar equivalência).
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


_VALID_ORIGINS = {"ui", "api", "seed", "script", "system", "migration"}
_AUDIT_LOG_TABLES = {
    "sector": "audit_sectors_audit_log",
    "alert": "audit_alerts_audit_log",
    "criterion": "audit_criteria_audit_log",
}


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
