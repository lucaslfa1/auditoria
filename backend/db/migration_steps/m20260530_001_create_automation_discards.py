MIGRATION_NAME = "m20260530_001_create_automation_discards"


def apply(c):
    # Registro historico: esta migration chegou a existir em producao, mas a
    # tabela automation_discards nao faz parte do fluxo operacional atual. O
    # descarte canonico da automacao vive em huawei_sync_logs tombstone.
    _ = c
