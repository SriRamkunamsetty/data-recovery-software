"""Concurrency and resource locking manager for scan, imaging, and recovery jobs."""

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from recoverx.domain.enums import JobStatus
from recoverx.domain.session import (
    CancellationToken,
    DestinationConflictError,
    DuplicateSourceJobError,
    ScanJobRecord,
)
from recoverx.infrastructure.persistence.repositories import JobRepository

logger = logging.getLogger(__name__)


class JobManager:
    """Orchestrates job lifecycle and enforces resource locking rules.

    Rules:
    - No duplicate concurrent jobs on the same source device (DuplicateSourceJobError).
    - No concurrent jobs sharing or targeting the same destination path (DestinationConflictError).
    - Thread-safe cooperative cancellation tokens.
    - Automatic state persistence via JobRepository when provided.
    """

    def __init__(self, job_repository: JobRepository | None = None) -> None:
        self.repository = job_repository
        self._lock = threading.Lock()
        # source_identifier -> job_id
        self._active_sources: dict[str, str] = {}
        # canonical_dest_path -> job_id
        self._active_destinations: dict[str, str] = {}
        # job_id -> CancellationToken
        self._tokens: dict[str, CancellationToken] = {}
        # job_id -> ScanJobRecord
        self._active_jobs: dict[str, ScanJobRecord] = {}

    def is_source_active(self, source_identifier: str) -> bool:
        """Check if an active job is already running on this source."""
        with self._lock:
            return source_identifier in self._active_sources

    def is_destination_active(self, destination_path: Path | str) -> bool:
        """Check if an active job is already writing to this destination path."""
        norm_dest = str(Path(destination_path).resolve())
        with self._lock:
            return any(
                norm_dest == active
                or norm_dest.startswith(active + "\\")
                or active.startswith(norm_dest + "\\")
                for active in self._active_destinations
            )

    def register_job(
        self,
        job_id: str,
        session_id: str,
        job_type: str,
        source_identifier: str,
        destination_path: Path | str | None = None,
    ) -> CancellationToken:
        """Register a new job and acquire necessary source/destination locks."""
        norm_dest: str | None = None
        if destination_path is not None:
            norm_dest = str(Path(destination_path).resolve())

        with self._lock:
            # 1. Enforce no duplicate jobs on the same source
            if source_identifier in self._active_sources:
                existing_job_id = self._active_sources[source_identifier]
                raise DuplicateSourceJobError(
                    f"A job ({existing_job_id}) is already active on source '{source_identifier}'"
                )

            # 2. Enforce no destination conflicts
            if norm_dest is not None:
                for active_dest, existing_job_id in self._active_destinations.items():
                    if (
                        norm_dest == active_dest
                        or norm_dest.startswith(active_dest + "\\")
                        or active_dest.startswith(norm_dest + "\\")
                    ):
                        raise DestinationConflictError(
                            f"Destination '{norm_dest}' conflicts with active job "
                            f"{existing_job_id} targeting '{active_dest}'"
                        )

            token = CancellationToken()
            job = ScanJobRecord(
                job_id=job_id,
                session_id=session_id,
                job_type=job_type,
                status=JobStatus.RUNNING,
                source_identifier=source_identifier,
                destination_path=norm_dest,
                created_at=time.time(),
                started_at=time.time(),
            )

            self._active_sources[source_identifier] = job_id
            if norm_dest is not None:
                self._active_destinations[norm_dest] = job_id
            self._tokens[job_id] = token
            self._active_jobs[job_id] = job

            if self.repository is not None:
                self.repository.save(job)

            logger.info("Job %s (%s) registered on source %s", job_id, job_type, source_identifier)
            return token

    def release_job(
        self,
        job_id: str,
        status: JobStatus = JobStatus.COMPLETED,
        error_message: str | None = None,
    ) -> None:
        """Release locks and mark job as finished."""
        with self._lock:
            job = self._active_jobs.pop(job_id, None)
            self._tokens.pop(job_id, None)

            if job is not None:
                self._active_sources.pop(job.source_identifier, None)
                if job.destination_path is not None:
                    self._active_destinations.pop(job.destination_path, None)

                if self.repository is not None:
                    self.repository.update_status(job_id, status, error_message=error_message)

            logger.info("Job %s released with status %s", job_id, status.value)

    def cancel_job(self, job_id: str) -> bool:
        """Signal cooperative cancellation to a registered job."""
        with self._lock:
            token = self._tokens.get(job_id)
            if token is not None:
                token.cancel()
                logger.info("Cancellation signaled to job %s", job_id)
                return True
            return False

    def get_token(self, job_id: str) -> CancellationToken | None:
        """Retrieve the cancellation token for a running job."""
        with self._lock:
            return self._tokens.get(job_id)

    @contextmanager
    def run_job(
        self,
        job_id: str,
        session_id: str,
        job_type: str,
        source_identifier: str,
        destination_path: Path | str | None = None,
    ) -> Iterator[CancellationToken]:
        """Context manager for acquiring and releasing a job cleanly."""
        token = self.register_job(
            job_id=job_id,
            session_id=session_id,
            job_type=job_type,
            source_identifier=source_identifier,
            destination_path=destination_path,
        )
        try:
            yield token
            self.release_job(job_id, status=JobStatus.COMPLETED)
        except Exception as exc:
            from recoverx.domain.session import ScanCancelledError

            if isinstance(exc, ScanCancelledError) or token.is_cancelled:
                self.release_job(job_id, status=JobStatus.CANCELLED)
            else:
                self.release_job(job_id, status=JobStatus.FAILED, error_message=str(exc))
            raise
