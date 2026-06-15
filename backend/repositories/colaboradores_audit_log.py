"""Trilha de auditoria de colaboradores (`colaboradores_audit_log`).

Registra INSERT/UPDATE/DELETE em `colaboradores` para que, quando um operador
sai da whitelist (status mudou, `auditavel` virou 0, `id_huawei` foi limpo),
seja possivel saber quem, quando e por que.

Extraido de `repositories.operators` (que reexporta `_snapshot_colaborador` e
`_log_colaborador_audit` p/ compat). `repositories.admin_criteria` tambem importa
estes helpers ao cascatear rename de setor.
"""
from typing import Optional

from psycopg2.extras import Json


_AUDITABLE_FIELDS = (
    "nome", "supervisor", "setor", "escala", "status", "auditavel",
    "matricula", "id_weon", "id_huawei", "id_telefonia",
    "softphone_number", "telefonia_account", "organizacao_telefonia",
    "tipo_agente", "status_telefonia", "oficial",
)


def _snapshot_colaborador(cursor, colaborador_id: int) -> Optional[dict]:
    """Le os campos auditaveis de um colaborador para snapshot pre/pos-mudanca."""
    fields = ", ".join(_AUDITABLE_FIELDS)
    cursor.execute(f"SELECT id, {fields} FROM colaboradores WHERE id = %s", (colaborador_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    try:
        return dict(row)
    except (TypeError, ValueError):
        cols = ["id"] + list(_AUDITABLE_FIELDS)
        return dict(zip(cols, row))


def _log_colaborador_audit(
    cursor,
    *,
    acao: str,
    entity_id: int,
    payload_antes: Optional[dict],
    payload_depois: Optional[dict],
    alterado_por: str = "system",
    motivo: Optional[str] = None,
    origem: str = "api",
) -> None:
    """Insere uma entrada em `colaboradores_audit_log`.

    Use o mesmo cursor da transacao principal para que log e mudanca sejam
    atomicos (rollback do log se a mudanca falhar e vice-versa).
    """
    try:
        cursor.execute(
            """
            INSERT INTO colaboradores_audit_log (
                acao, entity_id, payload_antes, payload_depois,
                alterado_por, motivo, origem
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                acao,
                str(entity_id),
                Json(payload_antes) if payload_antes is not None else None,
                Json(payload_depois) if payload_depois is not None else None,
                alterado_por or "system",
                motivo,
                origem,
            ),
        )
    except Exception:
        # Audit log nao pode bloquear a mudanca de negocio. Loga e segue.
        import logging
        logging.getLogger(__name__).exception(
            "Falha ao gravar colaboradores_audit_log (acao=%s entity_id=%s)",
            acao, entity_id,
        )
