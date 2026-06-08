MIGRATION_NAME = "m20260518_002_add_expected_direction"

def apply(c):
    c.execute(
        "ALTER TABLE audit_alerts ADD COLUMN IF NOT EXISTS expected_direction TEXT"
    )
