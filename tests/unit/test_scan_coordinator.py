"""Unit tests for ScanCoordinator orchestration, carving offer check, and candidate merging."""

from pathlib import Path

import pytest

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, FileSystemType, RecoverySourceMethod
from recoverx.domain.session import CancellationToken, ScanCancelledError
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.services.scan_coordinator import ScanCoordinator
from tests.fixtures.fat_builder import SyntheticFatBuilder


def test_deep_scan_never_starts_without_explicit_request(tmp_path: Path) -> None:
    """Acceptance check: deep scan (carving) NEVER starts without an explicit request."""
    img_path = tmp_path / "fat_test.img"
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="TEST_FAT")
    builder.build(img_path)

    with DiskImageReader(img_path) as reader:
        coordinator = ScanCoordinator()

        # Call without enable_carving (default is False)
        result = coordinator.coordinate_scan(reader, enable_carving=False)

        assert result.carving_executed is False
        # All found candidates must have come from metadata, not carving
        for cand in result.candidates:
            assert cand.source_method == RecoverySourceMethod.METADATA


def test_carving_runs_when_explicitly_requested(tmp_path: Path) -> None:
    """Test that carving runs when enable_carving=True and candidates are merged."""
    img_path = tmp_path / "fat_with_deleted.img"
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="TEST_FAT")
    # Add a deleted JPEG file
    builder.add_file(
        filename="PHOTO.JPG",
        content=(
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00"
            + b"\x01" * 64
            + b"\xff\xc0\x00\x0b\x08\x00\x08\x00\x08\x01\x01\x11\x00"
            + b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf"
            + b"\xff\xd9"
        ),
        is_deleted=True,
    )
    builder.build(img_path)

    with DiskImageReader(img_path) as reader:
        coordinator = ScanCoordinator()
        result = coordinator.coordinate_scan(reader, enable_carving=True)

        assert result.carving_executed is True
        assert len(result.candidates) >= 1

        # The deleted photo should be found and merged
        found = next((c for c in result.candidates if "PHOTO" in c.filename), None)
        assert found is not None
        # Merged candidate preserves metadata name and path
        assert found.filename == "PHOTO.JPG"
        assert found.source_method == RecoverySourceMethod.METADATA


def test_merge_and_deduplicate_status_upgrade() -> None:
    """Test candidate merging upgrades status to PREVIEW_VALIDATED while preserving metadata."""
    coordinator = ScanCoordinator()

    meta_cand = RecoveryCandidate(
        candidate_id="meta_1",
        filename="FAMILY.JPG",
        relative_path="DCIM/100CANON/FAMILY.JPG",
        extension=".jpg",
        size_bytes=5000,
        source_offset=1048576,
        source_method=RecoverySourceMethod.METADATA,
        status=CandidateStatus.METADATA_RECOVERED,
        created_at=1600000000.0,
        modified_at=1600000100.0,
    )

    carved_cand = RecoveryCandidate(
        candidate_id="carved_1",
        filename="carved_001048576.jpg",
        relative_path="",
        extension=".jpg",
        size_bytes=5000,
        source_offset=1048576,  # Same offset
        source_method=RecoverySourceMethod.CARVED,
        status=CandidateStatus.PREVIEW_VALIDATED,  # Carving verified payload
        sha256_hash="c" * 64,
    )

    merged = coordinator._merge_and_deduplicate([meta_cand], [carved_cand])
    assert len(merged) == 1

    result = merged[0]
    # Retains rich metadata attributes
    assert result.filename == "FAMILY.JPG"
    assert result.relative_path == "DCIM/100CANON/FAMILY.JPG"
    assert result.created_at == 1600000000.0
    assert result.modified_at == 1600000100.0
    # Status upgraded to Preview validated
    assert result.status == CandidateStatus.PREVIEW_VALIDATED
    assert result.sha256_hash == "c" * 64
    assert "Carving validated" in result.notes


def test_scan_coordinator_cancellation(tmp_path: Path) -> None:
    """Test that cancellation token immediately halts coordination."""
    img_path = tmp_path / "cancel.img"
    img_path.write_bytes(b"\x00" * 32768)

    with DiskImageReader(img_path) as reader:
        coordinator = ScanCoordinator()
        token = CancellationToken()
        token.cancel()  # Pre-cancel

        with pytest.raises(ScanCancelledError, match="cancelled by user"):
            coordinator.coordinate_scan(reader, cancellation_token=token)
