"""Background execution worker threads for non-blocking UI scans and recoveries."""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from recoverx.config import CollisionPolicy
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.scan import ScanProgress
from recoverx.domain.session import CancellationToken, ScanCancelledError
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.services.session_service import SessionService

logger = logging.getLogger(__name__)


class ScanWorker(QThread):
    """Background worker thread executing coordinated device scans without blocking the UI.

    Section 14 of MASTER_PROMPT.md:
    Scans, imaging, and recovery run in workers (QThread with signals and slots only;
    never touch widgets from workers).
    """

    progress_updated = Signal(object)  # ScanProgress
    scan_completed = Signal(object)  # ScanCoordinatorResult
    scan_failed = Signal(str)  # error message
    scan_cancelled = Signal()

    def __init__(
        self,
        session_service: SessionService,
        session_id: str,
        device: ReadOnlyBlockDevice,
        enable_carving: bool = False,
        scan_lost_volumes: bool = True,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.session_service = session_service
        self.session_id = session_id
        self.device = device
        self.enable_carving = enable_carving
        self.scan_lost_volumes = scan_lost_volumes
        self._cancellation_token = CancellationToken()

    def cancel(self) -> None:
        """Signal cooperative cancellation to this scan worker."""
        logger.info("Signaling cancellation to ScanWorker for session %s", self.session_id)
        self._cancellation_token.cancel()

    def run(self) -> None:
        """Worker main loop running on the dedicated background thread."""
        try:

            def progress_callback(progress: ScanProgress) -> None:
                self.progress_updated.emit(progress)

            # Pass progress callback to session_service.run_scan
            result = self.session_service.coordinator.coordinate_scan(
                device=self.device,
                enable_carving=self.enable_carving,
                scan_lost_volumes=self.scan_lost_volumes,
                progress_callback=progress_callback,
                cancellation_token=self._cancellation_token,
            )

            # Persist partitions and candidates in database
            if result.partitions:
                self.session_service.partition_repo.save_batch(self.session_id, result.partitions)

            if result.candidates:
                self.session_service.candidate_repo.save_batch(self.session_id, result.candidates)

            self.scan_completed.emit(result)

        except ScanCancelledError:
            logger.info("ScanWorker cancelled cleanly for session %s", self.session_id)
            self.scan_cancelled.emit()
        except Exception as exc:
            logger.exception("ScanWorker failed with error: %s", exc)
            self.scan_failed.emit(str(exc))


class RecoveryWorker(QThread):
    """Background worker thread executing safe file recovery without blocking the UI."""

    progress_updated = Signal(int, int, str)  # current, total, filename
    recovery_completed = Signal(list)  # list of RecoveryResult
    recovery_failed = Signal(str)  # error message

    def __init__(
        self,
        session_service: SessionService,
        session_id: str,
        device: ReadOnlyBlockDevice,
        candidate_ids: list[str],
        destination_dir: Path | str,
        collision_policy: CollisionPolicy = CollisionPolicy.RENAME,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.session_service = session_service
        self.session_id = session_id
        self.device = device
        self.candidate_ids = candidate_ids
        self.destination_dir = destination_dir
        self.collision_policy = collision_policy

    def run(self) -> None:
        """Extract candidates in background thread."""
        try:

            def progress_callback(
                current: int,
                total: int,
                cand: RecoveryCandidate,
                res: RecoveryResult,
            ) -> None:
                self.progress_updated.emit(current, total, cand.filename)

            results = self.session_service.recover_candidates(
                session_id=self.session_id,
                device=self.device,
                candidate_ids=self.candidate_ids,
                destination_dir=self.destination_dir,
                collision_policy=self.collision_policy,
                progress_callback=progress_callback,
            )
            self.recovery_completed.emit(results)
        except Exception as exc:
            logger.exception("RecoveryWorker failed with error: %s", exc)
            self.recovery_failed.emit(str(exc))
