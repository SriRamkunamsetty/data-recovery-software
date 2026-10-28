"""SQLite database schema and migrations for RecoverX session persistence."""

# Current schema version
LATEST_SCHEMA_VERSION = 1

MIGRATION_V1 = """
-- Schema migration version 1: Base session persistence
-- IMPORTANT FORENSIC CONSTRAINT: Never store recovered file content (raw bytes) in SQLite!
-- Stored content is restricted to metadata, hashes, offsets, and paths.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_identity_json TEXT NOT NULL,
    triage_status TEXT NOT NULL,
    triage_notes TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    destination_path TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    progress_fraction REAL NOT NULL DEFAULT 0.0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS partitions (
    partition_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    partition_index INTEGER NOT NULL,
    start_sector INTEGER NOT NULL,
    sector_count INTEGER NOT NULL,
    filesystem_type TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    is_lost_volume INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS candidates (
    candidate_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    source_offset INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    extension TEXT NOT NULL,
    status TEXT NOT NULL,
    source_method TEXT NOT NULL,
    sha256_hash TEXT,
    created_at REAL,
    modified_at REAL,
    notes TEXT NOT NULL DEFAULT '',
    recovered_path TEXT
);

CREATE INDEX IF NOT EXISTS idx_candidates_session ON candidates(session_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id);
CREATE INDEX IF NOT EXISTS idx_partitions_session ON partitions(session_id);
"""
