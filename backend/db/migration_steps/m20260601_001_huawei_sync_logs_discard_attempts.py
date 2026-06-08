MIGRATION_NAME = "m20260601_001_huawei_sync_logs_discard_attempts"


def apply(c):
    # Contador de descartes do tombstone anti-loop em huawei_sync_logs (esteira de dois
    # estados terminais, v1.3.103). Migration versionada e idempotente — garante a coluna
    # em todos os ambientes via run_pending_migrations (startup), independente do
    # ensure_column do runtime_schema.
    c.execute(
        "ALTER TABLE huawei_sync_logs ADD COLUMN IF NOT EXISTS discard_attempts INTEGER DEFAULT 0"
    )
