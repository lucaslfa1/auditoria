from typing import Any


MIGRATION_NAME = "20260419_002_add_fechamento_overrides"


def apply(cursor: Any) -> None:
    columns = [
        "matricula_override", "nome_override", "operacional_override", "telefonica_override",
        "desempenho_override", "status_override", "turno_override", "supervisor_override",
        "setor_override", "processo_override", "final_override", "huawei_override"
    ]
    for col in columns:
        cursor.execute(f"ALTER TABLE fechamento_cadeia_contatos ADD COLUMN IF NOT EXISTS {col} TEXT;")

