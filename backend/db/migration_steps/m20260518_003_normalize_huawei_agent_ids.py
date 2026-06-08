MIGRATION_NAME = "m20260518_003_normalize_huawei_agent_ids"


def apply(c):
    for table_name, column_name in (
        ("colaboradores", "id_huawei"),
        ("colaboradores", "id_telefonia"),
        ("huawei_sync_logs", "agent_id"),
    ):
        c.execute(
            f"""
            UPDATE {table_name}
            SET {column_name} = regexp_replace(TRIM({column_name}), '\\.0+$', '')
            WHERE {column_name} IS NOT NULL
              AND TRIM({column_name}) ~ '^[0-9]+\\.0+$'
            """
        )
