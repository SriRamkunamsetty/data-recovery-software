"""Unit tests for JobManager concurrency, locking, and cancellation."""

from pathlib import Path

import pytest

from recoverx.domain.enums import JobStatus
from recoverx.domain.session import (
    DestinationConflictError,
    DuplicateSourceJobError,
    ScanCancelledError,
)
from recoverx.services.job_manager import JobManager


def test_job_manager_clean_lifecycle() -> None:
    """Test standard single-job acquisition and clean release."""
    manager = JobManager()
    source_id = "DISK_001"

    assert not manager.is_source_active(source_id)

    with manager.run_job(
        job_id="job_1",
        session_id="sess_1",
        job_type="scan",
        source_identifier=source_id,
    ) as token:
        assert manager.is_source_active(source_id)
        assert not token.is_cancelled

    assert not manager.is_source_active(source_id)


def test_duplicate_source_job_refused() -> None:
    """Acceptance check: duplicate-job on a source is refused."""
    manager = JobManager()
    source_id = "DISK_SANDISK_123"

    with manager.run_job(
        job_id="job_active",
        session_id="sess_1",
        job_type="scan",
        source_identifier=source_id,
    ):
        assert manager.is_source_active(source_id)

        # Attempt to launch second concurrent job on same source
        with pytest.raises(DuplicateSourceJobError, match="already active on source"):
            manager.register_job(
                job_id="job_duplicate",
                session_id="sess_2",
                job_type="imaging",
                source_identifier=source_id,
            )

    # After exit, source is freed
    assert not manager.is_source_active(source_id)


def test_destination_conflict_refused(tmp_path: Path) -> None:
    """Acceptance check: concurrent jobs targeting conflicting destinations are refused."""
    manager = JobManager()
    dest_dir = tmp_path / "recovered_files"
    dest_sub = dest_dir / "subfolder"

    with manager.run_job(
        job_id="job_rec_1",
        session_id="sess_1",
        job_type="recovery",
        source_identifier="DISK_SRC_A",
        destination_path=dest_dir,
    ):
        assert manager.is_destination_active(dest_dir)

        # Subdirectory under active destination must be refused
        with pytest.raises(DestinationConflictError, match="conflicts with active job"):
            manager.register_job(
                job_id="job_rec_2",
                session_id="sess_2",
                job_type="recovery",
                source_identifier="DISK_SRC_B",
                destination_path=dest_sub,
            )

    # After release, destination is available again
    assert not manager.is_destination_active(dest_dir)


def test_job_cancellation_signaling() -> None:
    """Test cooperative cancellation token signaling and handling."""
    manager = JobManager()

    token = manager.register_job(
        job_id="job_cancel_test",
        session_id="sess_1",
        job_type="scan",
        source_identifier="DISK_XYZ",
    )

    token.check_cancelled()  # Does not raise

    # Signal cancellation
    assert manager.cancel_job("job_cancel_test") is True

    with pytest.raises(ScanCancelledError, match="cancelled by user"):
        token.check_cancelled()

    manager.release_job("job_cancel_test", status=JobStatus.CANCELLED)
    assert not manager.is_source_active("DISK_XYZ")
