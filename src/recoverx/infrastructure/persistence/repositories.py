"""Repository implementations for sessions, jobs, candidates, and partitions."""

import dataclasses
import json
import sqlite3
import time

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import (
    CandidateStatus,
    DeviceTriageStatus,
    JobStatus,
    RecoverySourceMethod,
)
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.session import RecoverySession, ScanJobRecord


class SessionRepository:
    """Persistence repository for user recovery sessions."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, session: RecoverySession) -> None:
        """Insert or update a recovery session without triggering cascade delete."""
        identity_json = json.dumps(dataclasses.asdict(session.source_identity))
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO sessions (
                    session_id, name, created_at, updated_at, status,
                    source_path, source_identity_json, triage_status,
                    triage_notes, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    name = excluded.name,
                    updated_at = excluded.updated_at,
                    status = excluded.status,
                    source_path = excluded.source_path,
                    source_identity_json = excluded.source_identity_json,
                    triage_status = excluded.triage_status,
                    triage_notes = excluded.triage_notes,
                    notes = excluded.notes;
                """,
                (
                    session.session_id,
                    session.name,
                    session.created_at,
                    session.updated_at,
                    session.status,
                    session.source_path,
                    identity_json,
                    session.triage_status.value,
                    session.triage_notes,
                    session.notes,
                ),
            )

    def get(self, session_id: str) -> RecoverySession | None:
        """Retrieve a session by its unique ID."""
        cursor = self.conn.execute(
            """
            SELECT session_id, name, created_at, updated_at, status,
                   source_path, source_identity_json, triage_status,
                   triage_notes, notes
            FROM sessions WHERE session_id = ?;
            """,
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        identity_dict = json.loads(row["source_identity_json"])
        identity = DeviceIdentity(**identity_dict)

        return RecoverySession(
            session_id=row["session_id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            source_path=row["source_path"],
            source_identity=identity,
            triage_status=DeviceTriageStatus(row["triage_status"]),
            triage_notes=row["triage_notes"],
            notes=row["notes"],
        )

    def list_all(self) -> list[RecoverySession]:
        """List all recovery sessions ordered newest to oldest."""
        cursor = self.conn.execute(
            """
            SELECT session_id, name, created_at, updated_at, status,
                   source_path, source_identity_json, triage_status,
                   triage_notes, notes
            FROM sessions ORDER BY created_at DESC;
            """
        )
        sessions: list[RecoverySession] = []
        for row in cursor.fetchall():
            identity_dict = json.loads(row["source_identity_json"])
            sessions.append(
                RecoverySession(
                    session_id=row["session_id"],
                    name=row["name"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    status=row["status"],
                    source_path=row["source_path"],
                    source_identity=DeviceIdentity(**identity_dict),
                    triage_status=DeviceTriageStatus(row["triage_status"]),
                    triage_notes=row["triage_notes"],
                    notes=row["notes"],
                )
            )
        return sessions

    def delete(self, session_id: str) -> bool:
        """Delete a recovery session and associated records."""
        with self.conn:
            cursor = self.conn.execute("DELETE FROM sessions WHERE session_id = ?;", (session_id,))
            return cursor.rowcount > 0


class JobRepository:
    """Persistence repository for scan, imaging, and extraction jobs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save(self, job: ScanJobRecord) -> None:
        """Insert or update a job record."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO jobs (
                    job_id, session_id, job_type, status, source_identifier,
                    destination_path, created_at, started_at, completed_at,
                    progress_fraction, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status,
                    started_at = excluded.started_at,
                    completed_at = excluded.completed_at,
                    progress_fraction = excluded.progress_fraction,
                    error_message = excluded.error_message;
                """,
                (
                    job.job_id,
                    job.session_id,
                    job.job_type,
                    job.status.value,
                    job.source_identifier,
                    job.destination_path,
                    job.created_at,
                    job.started_at,
                    job.completed_at,
                    job.progress_fraction,
                    job.error_message,
                ),
            )

    def get(self, job_id: str) -> ScanJobRecord | None:
        """Retrieve a job record by its ID."""
        cursor = self.conn.execute(
            """
            SELECT job_id, session_id, job_type, status, source_identifier,
                   destination_path, created_at, started_at, completed_at,
                   progress_fraction, error_message
            FROM jobs WHERE job_id = ?;
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return ScanJobRecord(
            job_id=row["job_id"],
            session_id=row["session_id"],
            job_type=row["job_type"],
            status=JobStatus(row["status"]),
            source_identifier=row["source_identifier"],
            destination_path=row["destination_path"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            progress_fraction=row["progress_fraction"],
            error_message=row["error_message"],
        )

    def list_by_session(self, session_id: str) -> list[ScanJobRecord]:
        """List all jobs associated with a session."""
        cursor = self.conn.execute(
            """
            SELECT job_id, session_id, job_type, status, source_identifier,
                   destination_path, created_at, started_at, completed_at,
                   progress_fraction, error_message
            FROM jobs WHERE session_id = ? ORDER BY created_at ASC;
            """,
            (session_id,),
        )
        return [
            ScanJobRecord(
                job_id=r["job_id"],
                session_id=r["session_id"],
                job_type=r["job_type"],
                status=JobStatus(r["status"]),
                source_identifier=r["source_identifier"],
                destination_path=r["destination_path"],
                created_at=r["created_at"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                progress_fraction=r["progress_fraction"],
                error_message=r["error_message"],
            )
            for r in cursor.fetchall()
        ]

    def get_active_jobs(self) -> list[ScanJobRecord]:
        """List all currently active or pending jobs."""
        cursor = self.conn.execute(
            """
            SELECT job_id, session_id, job_type, status, source_identifier,
                   destination_path, created_at, started_at, completed_at,
                   progress_fraction, error_message
            FROM jobs WHERE status IN ('pending', 'running') ORDER BY created_at ASC;
            """
        )
        return [
            ScanJobRecord(
                job_id=r["job_id"],
                session_id=r["session_id"],
                job_type=r["job_type"],
                status=JobStatus(r["status"]),
                source_identifier=r["source_identifier"],
                destination_path=r["destination_path"],
                created_at=r["created_at"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                progress_fraction=r["progress_fraction"],
                error_message=r["error_message"],
            )
            for r in cursor.fetchall()
        ]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: str | None = None,
    ) -> None:
        """Update job status and optional error."""
        now = time.time()
        completed = (
            now if status in (JobStatus.COMPLETED, JobStatus.CANCELLED, JobStatus.FAILED) else None
        )
        with self.conn:
            self.conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    completed_at = COALESCE(?, completed_at),
                    error_message = COALESCE(?, error_message)
                WHERE job_id = ?;
                """,
                (status.value, completed, error_message, job_id),
            )


class CandidateRepository:
    """Persistence repository for recovered file candidates."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_batch(self, session_id: str, candidates: list[RecoveryCandidate]) -> None:
        """Persist a list of candidate files.

        NOTE: Only metadata is stored. Never store recovered file content bytes in SQLite!
        """
        rows = [
            (
                c.candidate_id,
                session_id,
                c.filename,
                c.relative_path,
                c.source_offset,
                c.size_bytes,
                c.extension,
                c.status.value,
                c.source_method.value,
                c.sha256_hash,
                c.created_at,
                c.modified_at,
                c.notes,
            )
            for c in candidates
        ]
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO candidates (
                    candidate_id, session_id, filename, relative_path,
                    source_offset, size_bytes, extension, status,
                    source_method, sha256_hash, created_at, modified_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    status = excluded.status,
                    sha256_hash = COALESCE(excluded.sha256_hash, candidates.sha256_hash),
                    notes = excluded.notes;
                """,
                rows,
            )

    def get_by_session(self, session_id: str) -> list[RecoveryCandidate]:
        """Retrieve all candidates associated with a session."""
        cursor = self.conn.execute(
            """
            SELECT candidate_id, filename, relative_path, source_offset,
                   size_bytes, extension, status, source_method, sha256_hash,
                   created_at, modified_at, notes
            FROM candidates WHERE session_id = ? ORDER BY source_offset ASC;
            """,
            (session_id,),
        )
        return [
            RecoveryCandidate(
                candidate_id=r["candidate_id"],
                filename=r["filename"],
                relative_path=r["relative_path"],
                source_offset=r["source_offset"],
                size_bytes=r["size_bytes"],
                extension=r["extension"],
                status=CandidateStatus(r["status"]),
                source_method=RecoverySourceMethod(r["source_method"]),
                sha256_hash=r["sha256_hash"],
                created_at=r["created_at"],
                modified_at=r["modified_at"],
                notes=r["notes"],
            )
            for r in cursor.fetchall()
        ]

    def update_candidate_recovered(
        self, candidate_id: str, recovered_path: str, sha256_hash: str | None = None
    ) -> None:
        """Record extracted path and actual hash for a recovered candidate."""
        with self.conn:
            self.conn.execute(
                """
                UPDATE candidates
                SET recovered_path = ?,
                    sha256_hash = COALESCE(?, sha256_hash)
                WHERE candidate_id = ?;
                """,
                (recovered_path, sha256_hash, candidate_id),
            )

    def count_by_session(self, session_id: str) -> int:
        """Count total candidates discovered in a session."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM candidates WHERE session_id = ?;", (session_id,)
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0


class PartitionRepository:
    """Persistence repository for analyzed partitions and lost volumes."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def save_batch(
        self,
        session_id: str,
        partitions: list[PartitionInfo],
        is_lost_volume: bool = False,
    ) -> None:
        """Persist a list of discovered partitions."""
        rows = [
            (
                f"{session_id}_{p.partition_number}_{p.start_sector}",
                session_id,
                p.partition_number,
                p.start_sector,
                p.sector_count,
                p.partition_type_or_guid or "Unknown",
                1 if p.is_bootable else 0,
                1 if is_lost_volume else 0,
                p.name or "",
            )
            for p in partitions
        ]
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO partitions (
                    partition_id, session_id, partition_index, start_sector,
                    sector_count, filesystem_type, is_active, is_lost_volume,
                    description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(partition_id) DO UPDATE SET
                    filesystem_type = excluded.filesystem_type,
                    is_active = excluded.is_active,
                    description = excluded.description;
                """,
                rows,
            )

    def get_by_session(self, session_id: str) -> list[PartitionInfo]:
        """Retrieve all partitions for a session."""
        cursor = self.conn.execute(
            """
            SELECT partition_index, start_sector, sector_count, filesystem_type,
                   is_active, description
            FROM partitions WHERE session_id = ? ORDER BY start_sector ASC;
            """,
            (session_id,),
        )
        return [
            PartitionInfo(
                partition_number=r["partition_index"],
                start_sector=r["start_sector"],
                sector_count=r["sector_count"],
                partition_type_or_guid=r["filesystem_type"],
                name=r["description"],
                is_bootable=bool(r["is_active"]),
            )
            for r in cursor.fetchall()
        ]
