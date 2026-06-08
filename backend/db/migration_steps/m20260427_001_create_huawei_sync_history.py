MIGRATION_NAME = "m20260427_001_create_huawei_sync_history"

def apply(c):
    c.execute('''
        CREATE TABLE IF NOT EXISTS telefonia_sync_history (
            id SERIAL PRIMARY KEY,
            started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(50) NOT NULL,
            horas_retroativas INTEGER DEFAULT 1,
            baixadas INTEGER DEFAULT 0,
            enfileiradas INTEGER DEFAULT 0,
            erros_totais INTEGER DEFAULT 0,
            mensagem_erro TEXT,
            trigger_type VARCHAR(50) DEFAULT 'cron'
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_telefonia_sync_history_started_at ON telefonia_sync_history(started_at DESC)')

