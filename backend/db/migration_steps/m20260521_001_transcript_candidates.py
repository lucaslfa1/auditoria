"""Add trace table for immutable transcription provider candidates."""
from __future__ import annotations


MIGRATION_NAME = "m20260521_001_transcript_candidates"


def apply(c) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS transcript_candidates (
            id BIGSERIAL PRIMARY KEY,
            audit_id BIGINT REFERENCES audits(id) ON DELETE CASCADE,
            input_hash TEXT,
            candidate_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT 'audit',
            segments JSONB NOT NULL DEFAULT '[]'::jsonb,
            raw_response JSONB,
            provider_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
            deterministic_score NUMERIC,
            judge_score NUMERIC,
            judge_reason TEXT,
            cross_signals JSONB NOT NULL DEFAULT '{}'::jsonb,
            status TEXT NOT NULL DEFAULT 'candidate',
            error TEXT,
            elapsed_seconds NUMERIC,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    c.execute("CREATE INDEX IF NOT EXISTS ix_transcript_candidates_audit ON transcript_candidates(audit_id)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_transcript_candidates_hash ON transcript_candidates(input_hash)")
    c.execute("CREATE INDEX IF NOT EXISTS ix_transcript_candidates_provider ON transcript_candidates(provider)")
    c.execute(
        """
        ALTER TABLE audits
        ADD COLUMN IF NOT EXISTS selected_candidate_id BIGINT REFERENCES transcript_candidates(id)
        """
    )
    c.execute("ALTER TABLE audits ADD COLUMN IF NOT EXISTS selection_reason TEXT")
    c.execute("ALTER TABLE audits ADD COLUMN IF NOT EXISTS selection_gates JSONB")
