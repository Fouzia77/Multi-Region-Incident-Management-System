-- Database initialization script for the incidents table.
-- This runs automatically when the PostgreSQL container starts.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS incidents (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(255)    NOT NULL,
    description     TEXT,
    status          VARCHAR(50)     NOT NULL DEFAULT 'OPEN',
    severity        VARCHAR(50)     NOT NULL,
    assigned_team   VARCHAR(100),
    vector_clock    JSONB           NOT NULL DEFAULT '{}',
    version_conflict BOOLEAN        NOT NULL DEFAULT false,
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for fast lookup by conflict flag (useful for monitoring)
CREATE INDEX IF NOT EXISTS idx_incidents_version_conflict ON incidents(version_conflict);

-- Index for time-ordered queries
CREATE INDEX IF NOT EXISTS idx_incidents_updated_at ON incidents(updated_at DESC);
