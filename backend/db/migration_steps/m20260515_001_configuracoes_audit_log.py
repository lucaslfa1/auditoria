"""Fase 0 do plano de migracao DB-first (docs/database/dynamic-config-migration.md).

Cria a infraestrutura de auditoria para a tabela `configuracoes`:
- `configuracoes_audit_log`: trilha de quem mudou o que, quando e por que.
- `configuracoes.tipo`: classificacao do valor (string/int/float/bool/json/secret).
- `configuracoes.is_secret`: flag para mascarar no GET /api/configuracoes.

Tudo idempotente. Seed dos `tipo`/`is_secret` pras chaves ja existentes na producao
(Huawei, automacao, RPA, etc.) — qualquer chave nova entra como 'string' por default
e pode ser reclassificada via UPDATE direto ou nova migracao.
"""

MIGRATION_NAME = "m20260515_001_configuracoes_audit_log"


def apply(c):
    # 1. Tabela de audit log
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes_audit_log (
            id            BIGSERIAL PRIMARY KEY,
            chave         TEXT NOT NULL,
            valor_antes   TEXT,
            valor_depois  TEXT,
            alterado_por  TEXT NOT NULL,
            alterado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            motivo        TEXT,
            origem        TEXT NOT NULL DEFAULT 'ui'
                          CHECK (origem IN ('ui','api','seed','script','system','migration'))
        )
        """
    )
    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_configuracoes_audit_chave_em
            ON configuracoes_audit_log (chave, alterado_em DESC)
        """
    )
    c.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_configuracoes_audit_em
            ON configuracoes_audit_log (alterado_em DESC)
        """
    )

    # 2. Colunas novas em configuracoes (DEFAULTs garantem que rows existentes nao quebrem)
    c.execute(
        "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'string'"
    )
    c.execute(
        "ALTER TABLE configuracoes ADD COLUMN IF NOT EXISTS is_secret BOOLEAN NOT NULL DEFAULT false"
    )
    # CHECK constraint separado pra ser idempotente (DROP IF EXISTS antes do ADD)
    c.execute("ALTER TABLE configuracoes DROP CONSTRAINT IF EXISTS configuracoes_tipo_check")
    c.execute(
        """
        ALTER TABLE configuracoes
            ADD CONSTRAINT configuracoes_tipo_check
            CHECK (tipo IN ('string','int','float','bool','json','secret'))
        """
    )

    # 3. Seed dos tipos/flags pras chaves existentes na producao.
    # Importante: idempotente — UPDATEs simples, sem assumir valor previo.
    c.execute(
        """
        UPDATE configuracoes SET tipo = 'bool'
         WHERE chave IN (
            'automacao_hibrida_ativa',
            'automacao_is_cancelled',
            'automacao_is_paused',
            'huawei_d1_enabled',
            'robo_habilitado',
            'sync_lock',
            'telefonia_cron_sync_ativa'
         )
        """
    )
    c.execute(
        """
        UPDATE configuracoes SET tipo = 'int'
         WHERE chave IN (
            'automacao_intervalo_segundos',
            'huawei_ccid',
            'huawei_vdn',
            'huawei_d1_limite_ligacoes',
            'huawei_d1_lookback_dias',
            'huawei_d1_max_retries',
            'huawei_d1_retry_intervalo_minutos',
            'huawei_cota_max_por_operador_mes'
         )
        """
    )
    c.execute(
        """
        UPDATE configuracoes SET tipo = 'float'
         WHERE chave IN ('huawei_horas_retroativas')
        """
    )
    c.execute(
        """
        UPDATE configuracoes SET tipo = 'secret', is_secret = true
         WHERE chave IN (
            'huawei_ak',
            'huawei_sk',
            'huawei_app_secret',
            'huawei_obs_ak',
            'huawei_obs_sk',
            'rpa_senha'
         )
        """
    )
