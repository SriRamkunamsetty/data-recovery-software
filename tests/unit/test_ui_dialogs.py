"""Unit tests for UI modal dialogs: FilePreviewDialog and RecoveryDestinationDialog."""

from pathlib import Path

from PySide6.QtWidgets import QApplication

from recoverx.config import CollisionPolicy
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.presentation.demo import _create_minimal_jpeg, create_demo_fat16_image
from recoverx.presentation.dialogs.destination_dialog import RecoveryDestinationDialog
from recoverx.presentation.dialogs.preview_dialog import FilePreviewDialog


def test_preview_dialog_valid_text(qapp: QApplication, tmp_path: Path) -> None:
    """Test preview dialog safely loads and renders text content."""
    img_path = tmp_path / "test_demo.raw"
    create_demo_fat16_image(img_path)

    reader = DiskImageReader(img_path)
    try:
        cand = RecoveryCandidate(
            candidate_id="cand_1",
            filename="README.TXT",
            relative_path="README.TXT",
            extension=".txt",
            size_bytes=40,
            source_offset=0x200,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.METADATA_RECOVERED,
        )

        dialog = FilePreviewDialog(candidate=cand, device=reader)
        assert dialog.accessibleName() == "File Preview Dialog"
        dialog.close()
    finally:
        reader.close()


def test_preview_dialog_valid_jpeg(qapp: QApplication, tmp_path: Path) -> None:
    """Test preview dialog safely decodes and renders JPEG image bytes."""
    jpeg_bytes = _create_minimal_jpeg()
    img_path = tmp_path / "test_jpeg.raw"
    img_path.write_bytes(jpeg_bytes + b"\x00" * 4096)

    reader = DiskImageReader(img_path)
    try:
        cand = RecoveryCandidate(
            candidate_id="cand_jpg",
            filename="PHOTO.JPG",
            relative_path="PHOTO.JPG",
            extension=".jpg",
            size_bytes=len(jpeg_bytes),
            source_offset=0,
            source_method=RecoverySourceMethod.CARVED,
            status=CandidateStatus.PREVIEW_VALIDATED,
        )

        dialog = FilePreviewDialog(candidate=cand, device=reader)
        assert dialog.accessibleName() == "File Preview Dialog"
        dialog.close()
    finally:
        reader.close()


def test_preview_dialog_exceeding_ceiling(qapp: QApplication, tmp_path: Path) -> None:
    """Test preview dialog rejects files exceeding preview size ceiling."""
    img_path = tmp_path / "test_large.raw"
    img_path.write_bytes(b"\x00" * 8192)

    reader = DiskImageReader(img_path)
    try:
        cand = RecoveryCandidate(
            candidate_id="cand_huge",
            filename="HUGE.DAT",
            relative_path="HUGE.DAT",
            extension=".dat",
            size_bytes=10 * 1024 * 1024,  # 10 MiB > 5 MiB ceiling
            source_offset=0,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.METADATA_RECOVERED,
        )

        dialog = FilePreviewDialog(candidate=cand, device=reader)
        dialog.close()
    finally:
        reader.close()


def test_destination_dialog_separation_check(qapp: QApplication, tmp_path: Path) -> None:
    """Test destination dialog enforces strict source-destination separation."""
    img_path = tmp_path / "source_image.raw"
    img_path.write_bytes(b"\x00" * 4096)
    dest_path = tmp_path / "safe_destination"
    dest_path.mkdir()

    reader = DiskImageReader(img_path)
    try:
        resolver = FakeVolumeIdentityResolver()
        # Register source image on Disk 1, volume VOL-SOURCE
        resolver.register_device_volume(reader, volume_id="VOL-SOURCE", physical_disk_number=1)
        # Register destination on Disk 2, volume VOL-DEST
        resolver.register_path_volume(dest_path, volume_id="VOL-DEST", physical_disk_number=2)

        dialog = RecoveryDestinationDialog(
            source_device=reader,
            resolver=resolver,
            total_files=5,
            total_bytes=10240,
        )

        # Set valid separate path
        dialog.path_edit.setText(str(dest_path))
        dialog._validate_destination()
        assert "Verified" in dialog.status_label.text()

        # Set collision policy
        dialog.skip_radio.setChecked(True)
        dialog._on_confirm()
        assert dialog.selected_policy == CollisionPolicy.SKIP
        assert dialog.selected_destination == dest_path

        # Now test invalid conflict path (same volume)
        conflict_path = tmp_path / "conflict_dir"
        conflict_path.mkdir()
        resolver.register_path_volume(conflict_path, volume_id="VOL-SOURCE", physical_disk_number=1)

        dialog.path_edit.setText(str(conflict_path))
        dialog._validate_destination()
        assert "Refused" in dialog.status_label.text()

        dialog.close()
    finally:
        reader.close()
