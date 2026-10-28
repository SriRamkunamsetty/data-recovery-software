"""Unit tests for background ScanWorker and RecoveryWorker threads."""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from recoverx.config import CollisionPolicy
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.presentation.demo import create_demo_fat16_image
from recoverx.presentation.workers import RecoveryWorker, ScanWorker
from recoverx.services.session_service import SessionService


def test_scan_worker_execution(qapp: QApplication, tmp_path: Path) -> None:
    """Test ScanWorker emits progress and completed signals with discovered candidates."""
    img_path = tmp_path / "test_demo.raw"
    create_demo_fat16_image(img_path)

    db_path = tmp_path / "test.db"
    db_mgr = DatabaseManager(db_path)
    resolver = FakeVolumeIdentityResolver()
    service = SessionService(db_manager=db_mgr, resolver=resolver)

    reader = DiskImageReader(img_path)
    try:
        session = service.create_session(str(img_path), reader)

        worker = ScanWorker(
            session_service=service,
            session_id=session.session_id,
            device=reader,
            enable_carving=True,
            scan_lost_volumes=True,
        )

        progresses: list[Any] = []
        completed_results: list[Any] = []
        failed_errors: list[str] = []

        worker.progress_updated.connect(progresses.append)
        worker.scan_completed.connect(completed_results.append)
        worker.scan_failed.connect(failed_errors.append)

        # Run synchronously on the current thread for deterministic testing
        worker.run()

        assert len(failed_errors) == 0
        assert len(completed_results) == 1
        result = completed_results[0]
        assert len(result.candidates) >= 1
        assert len(progresses) >= 1
    finally:
        reader.close()


def test_scan_worker_cancellation(qapp: QApplication, tmp_path: Path) -> None:
    """Test ScanWorker responds to cancellation token and emits scan_cancelled."""
    img_path = tmp_path / "test_demo.raw"
    create_demo_fat16_image(img_path)

    db_path = tmp_path / "test.db"
    db_mgr = DatabaseManager(db_path)
    resolver = FakeVolumeIdentityResolver()
    service = SessionService(db_manager=db_mgr, resolver=resolver)

    reader = DiskImageReader(img_path)
    try:
        session = service.create_session(str(img_path), reader)

        worker = ScanWorker(
            session_service=service,
            session_id=session.session_id,
            device=reader,
            enable_carving=False,
            scan_lost_volumes=False,
        )

        cancelled_events: list[bool] = []
        worker.scan_cancelled.connect(lambda: cancelled_events.append(True))

        # Cancel immediately before execution
        worker.cancel()
        worker.run()

        assert len(cancelled_events) == 1
    finally:
        reader.close()


def test_recovery_worker_execution(qapp: QApplication, tmp_path: Path) -> None:
    """Test RecoveryWorker extracts candidates safely to destination directory."""
    img_path = tmp_path / "test_demo.raw"
    create_demo_fat16_image(img_path)

    dest_dir = tmp_path / "recovered_out"
    dest_dir.mkdir()

    db_path = tmp_path / "test.db"
    db_mgr = DatabaseManager(db_path)
    resolver = FakeVolumeIdentityResolver()
    service = SessionService(db_manager=db_mgr, resolver=resolver)

    reader = DiskImageReader(img_path)
    try:
        session = service.create_session(str(img_path), reader)

        # Seed candidate in candidate repo
        candidate = RecoveryCandidate(
            candidate_id="cand_test_01",
            filename="README.TXT",
            relative_path="README.TXT",
            extension=".txt",
            size_bytes=50,
            source_offset=0x200,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.METADATA_RECOVERED,
        )
        service.candidate_repo.save_batch(session.session_id, [candidate])

        worker = RecoveryWorker(
            session_service=service,
            session_id=session.session_id,
            device=reader,
            candidate_ids=[candidate.candidate_id],
            destination_dir=dest_dir,
            collision_policy=CollisionPolicy.RENAME,
        )

        progress_calls: list[tuple[int, int, str]] = []
        completed_results: list[Any] = []
        failed_errors: list[str] = []

        worker.progress_updated.connect(lambda c, t, f: progress_calls.append((c, t, f)))
        worker.recovery_completed.connect(completed_results.append)
        worker.recovery_failed.connect(failed_errors.append)

        worker.run()

        assert len(failed_errors) == 0
        assert len(completed_results) == 1
        assert len(progress_calls) == 1
    finally:
        reader.close()
