from typing import Any

from db.schema_tools import ensure_column, get_existing_columns


MIGRATION_NAME = "20260326_018_add_contested_criteria"


def apply(cursor: Any) -> None:
    # Esta migracao adiciona as colunas 'contested_criteria' e 'contestation_reason'
    # que foram adicionadas diretamente no runtime_schema.py mas nao possuiam
    # script de migracao para o banco de dados de producao (PostgreSQL).
    
    # 1. Obter colunas existentes na tabela 'audits'
    audit_columns = get_existing_columns(cursor, "audits")
    
    # 2. Adicionar as colunas
    ensure_column(cursor, "audits", "contestation_reason", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "contested_criteria", "TEXT", audit_columns)
