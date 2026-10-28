"""Session application service managing recovery lifecycles, persistence, and execution."""

import logging
import time
import uuid
from pathlib import Path

from recoverx.config import CollisionPolicy
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.session import (
    RecoverySession,
)
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.persistence.repositories import (
    CandidateRepository,
    JobRepository,
    PartitionRepository,
    SessionRepository,
)
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import VolumeIdentityResolver
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.job_manager import JobManager
from recoverx.services.recovery_service import RecoveryProgressCallback, RecoveryService
from recoverx.services.scan_coordinator import (
    ScanCoordinator,
    ScanCoordinatorResult,
    ScanProgressCallback,
)

logger = logging.getLogger(__name__)


class SessionService:
    """Application service coordinating recovery sessions, storage, and worker execution."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        resolver: VolumeIdentityResolver,
        job_manager: JobManager | None = None,
        coordinator: ScanCoordinator | None = None,
        recovery_service: RecoveryService | None = None,
    ) -> None:
        self.db = db_manager
        self.resolver = resolver
        self.session_repo = SessionRepository(self.db.connection)
        self.job_repo = JobRepository(self.db.connection)
        self.candidate_repo = CandidateRepository(self.db.connection)
        self.partition_repo = PartitionRepository(self.db.connection)

        self.job_manager = job_manager or JobManager(job_repository=self.job_repo)
        self.coordinator = coordinator or ScanCoordinator()
        self.recovery_service = recovery_service or RecoveryService(resolver=self.resolver)
        self.triage_service = DeviceTriageService()

    def create_session(
        self,
        source_path: str,
        source_device: ReadOnlyBlockDevice,
        name: str | None = None,
        notes: str = "",
    ) -> RecoverySession:
        """Create and persist a new recovery session for a storage device."""
        now = time.time()
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session_name = (
            name or f"Recovery {source_device.identity.product} ({time.strftime('%Y-%m-%d %H:%M')})"
        )

        # Run triage to establish baseline health
        triage = self.triage_service.triage_device(source_device)

        session = RecoverySession(
            session_id=session_id,
            name=session_name,
            created_at=now,
            updated_at=now,
            status="active",
            source_path=source_path,
            source_identity=source_device.identity,
            triage_status=triage.status,
            triage_notes=triage.explanation,
            notes=notes,
        )

        self.session_repo.save(session)
        logger.info(
            "Created session %s for device %s", session_id, source_device.identity.disk_identifier
        )
        return session

    def get_session(self, session_id: str) -> RecoverySession | None:
        """Retrieve a session by its ID."""
        return self.session_repo.get(session_id)

    def list_sessions(self) -> list[RecoverySession]:
        """List all historical recovery sessions."""
        return self.session_repo.list_all()

    def run_scan(
        self,
        session_id: str,
        device: ReadOnlyBlockDevice,
        enable_carving: bool = False,
        scan_lost_volumes: bool = True,
        progress_callback: ScanProgressCallback | None = None,
    ) -> ScanCoordinatorResult:
        """Execute a coordinated recovery scan on a session's source device."""
        session = self.session_repo.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        job_id = f"job_scan_{uuid.uuid4().hex[:8]}"
        source_id = device.identity.disk_identifier or session.source_path

        # Enforce resource locking: no duplicate jobs on this source
        with self.job_manager.run_job(
            job_id=job_id,
            session_id=session_id,
            job_type="scan",
            source_identifier=source_id,
        ) as token:
            result = self.coordinator.coordinate_scan(
                device=device,
                expected_identity=session.source_identity,
                enable_carving=enable_carving,
                scan_lost_volumes=scan_lost_volumes,
                progress_callback=progress_callback,
                cancellation_token=token,
            )

            # Persist discovered partitions and candidates
            if result.partitions:
                self.partition_repo.save_batch(session_id, result.partitions)

            if result.candidates:
                self.candidate_repo.save_batch(session_id, result.candidates)

            # Update session status
            updated_session = RecoverySession(
                session_id=session.session_id,
                name=session.name,
                created_at=session.created_at,
                updated_at=time.time(),
                status="completed",
                source_path=session.source_path,
                source_identity=session.source_identity,
                triage_status=result.triage_result.status,
                triage_notes=result.triage_result.explanation,
                notes=session.notes,
            )
            self.session_repo.save(updated_session)

            return result

    def recover_candidates(
        self,
        session_id: str,
        device: ReadOnlyBlockDevice,
        candidate_ids: list[str],
        destination_dir: Path | str,
        collision_policy: CollisionPolicy = CollisionPolicy.RENAME,
        work_directory: Path | str | None = None,
        progress_callback: RecoveryProgressCallback | None = None,
    ) -> list[RecoveryResult]:
        """Recover selected candidate files to a safe separate destination."""
        session = self.session_repo.get(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        all_candidates = self.candidate_repo.get_by_session(session_id)
        target_ids = set(candidate_ids)
        selected = [c for c in all_candidates if c.candidate_id in target_ids]

        if not selected:
            logger.warning("No matching candidates found for recovery in session %s", session_id)
            return []

        job_id = f"job_rec_{uuid.uuid4().hex[:8]}"
        source_id = device.identity.disk_identifier or session.source_path

        # Enforce resource locking: no duplicate jobs on source AND no destination conflicts
        with self.job_manager.run_job(
            job_id=job_id,
            session_id=session_id,
            job_type="recovery",
            source_identifier=source_id,
            destination_path=destination_dir,
        ):
            results = self.recovery_service.recover_candidates(
                device=device,
                destination_directory=destination_dir,
                candidates=selected,
                collision_policy=collision_policy,
                work_directory=work_directory,
                progress_callback=progress_callback,
            )

            # Update database records for recovered candidates
            for res in results:
                if res.is_successful:
                    self.candidate_repo.update_candidate_recovered(
                        candidate_id=res.candidate_id,
                        recovered_path=res.destination_path,
                        sha256_hash=res.actual_sha256,
                    )

            return results
