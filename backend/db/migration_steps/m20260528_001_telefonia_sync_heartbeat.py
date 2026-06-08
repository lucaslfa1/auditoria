"""Adiciona colunas de heartbeat e flags de controle em `telefonia_sync_history`.

Permite que pause/resume e cancel sobrevivam reinicio do Cloud Run, ja que o
estado deixa de viver apenas em memoria (globals em `backend/routers/telefonia.py`).

- `pause_requested BOOLEAN`     — auditor pediu pause; lido pelo loop do sync.
- `cancel_requested BOOLEAN`    — auditor pediu cancel; lido pelo loop do sync.
- `last_heartbeat_at TIMESTAMPTZ` — atualizado periodicamente; serve para
  reconciliar runs orfaos (pod morreu antes do finished_at) como 'interrupted'.
"""

MIGRATION_NAME = "m20260528_001_telefonia_sync_heartbeat"


def apply(c):
    # information_schema check garante idempotencia (sem IF NOT EXISTS antigo).
    c.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'telefonia_sync_history'
          AND column_name IN ('pause_requested', 'cancel_requested', 'last_heartbeat_at')
        """
    )
    existing = {row[0] if not isinstance(row, dict) else row['column_name'] for row in c.fetchall()}

    if 'pause_requested' not in existing:
        c.execute(
            "ALTER TABLE telefonia_sync_history "
            "ADD COLUMN pause_requested BOOLEAN NOT NULL DEFAULT false"
        )
    if 'cancel_requested' not in existing:
        c.execute(
            "ALTER TABLE telefonia_sync_history "
            "ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT false"
        )
    if 'last_heartbeat_at' not in existing:
        c.execute(
            "ALTER TABLE telefonia_sync_history "
            "ADD COLUMN last_heartbeat_at TIMESTAMPTZ"
        )

    # Index parcial para acelerar lookup de "run ativo" (finished_at IS NULL).
    # Tipicamente ha 0 ou 1 linha matching — o index e essencialmente um filtro.
    c.execute(
        """
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public'
          AND indexname = 'idx_telefonia_sync_history_active'
        """
    )
    if not c.fetchone():
        c.execute(
            "CREATE INDEX idx_telefonia_sync_history_active "
            "ON telefonia_sync_history (started_at) WHERE finished_at IS NULL"
        )
