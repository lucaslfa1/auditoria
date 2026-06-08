"""Adiciona operator_name e huawei_skill_id em huawei_sync_logs.

Motivacao: hoje a tabela armazena apenas call_id + agent_id (workNo). Quando
o operador da ligacao nao casa com nenhum colaborador cadastrado, perdemos
o nome que a Huawei reportou para diagnostico e rastreabilidade.

skill_id eh capturado pra uso futuro (mapeamento setor por skill) — sem
custo adicional aqui ja que o valor vem junto na interacao.
"""

MIGRATION_NAME = "m20260516_001_huawei_sync_logs_operator_skill"


def apply(c):
    c.execute(
        "ALTER TABLE huawei_sync_logs ADD COLUMN IF NOT EXISTS operator_name TEXT"
    )
    c.execute(
        "ALTER TABLE huawei_sync_logs ADD COLUMN IF NOT EXISTS huawei_skill_id TEXT"
    )
    # Indice para consultas operacionais por agent_id.
    c.execute(
        "CREATE INDEX IF NOT EXISTS idx_huawei_sync_agent_id ON huawei_sync_logs(agent_id)"
    )
