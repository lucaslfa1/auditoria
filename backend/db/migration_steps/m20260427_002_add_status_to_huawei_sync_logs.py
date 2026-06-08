MIGRATION_NAME = "m20260427_002_add_status_to_huawei_sync_logs"


def apply(c):
    c.execute("ALTER TABLE huawei_sync_logs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'success'")
    c.execute("ALTER TABLE huawei_sync_logs ADD COLUMN IF NOT EXISTS failure_reason TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_huawei_sync_status ON huawei_sync_logs(status)")
