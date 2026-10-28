"""Unit tests for LostVolumeScanner and backup boot structure recovery."""

from pathlib import Path

from recoverx.domain.enums import FileSystemType
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.partitions.scanner import LostVolumeScanner
from tests.fixtures.partition_builder import SyntheticPartitionBuilder


def test_scan_lost_fat32_primary(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    # Embed FAT32 volume at sector 2048
    builder.embed_fat32_volume(
        image=image,
        start_sector=2048,
        total_sectors=4000,
        corrupt_primary=False,
    )

    img_path = tmp_path / "fat32_primary.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        candidates = LostVolumeScanner.scan(reader, step_sectors=8)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 2048
        assert cand.sector_count == 4000
        assert cand.filesystem_type == FileSystemType.FAT32
        assert cand.is_backup_structure is False
        assert "Primary FAT32 boot sector" in cand.detection_source


def test_scan_lost_fat32_backup_when_primary_wiped(tmp_path: Path) -> None:
    """Acceptance check: wiped primary boot sector recovered via FAT32 backup boot sector."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    # Embed FAT32 with WIPED primary at sector 2048, surviving backup at sector 2054
    builder.embed_fat32_volume(
        image=image,
        start_sector=2048,
        total_sectors=4000,
        corrupt_primary=True,
    )

    img_path = tmp_path / "fat32_backup_only.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        # Sector 2048 is 0x00, but sector 2054 has valid backup boot sector
        candidates = LostVolumeScanner.scan(reader, step_sectors=1)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 2048  # Reconstructed volume start!
        assert cand.sector_count == 4000
        assert cand.filesystem_type == FileSystemType.FAT32
        assert cand.is_backup_structure is True
        assert "FAT32 backup boot sector" in cand.detection_source
        assert "primary missing" in cand.evidence


def test_scan_lost_exfat_primary(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    builder.embed_exfat_volume(
        image=image,
        start_sector=4096,
        total_sectors=3000,
        corrupt_primary=False,
    )

    img_path = tmp_path / "exfat_primary.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        candidates = LostVolumeScanner.scan(reader, step_sectors=8)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 4096
        assert cand.sector_count == 3000
        assert cand.filesystem_type == FileSystemType.EXFAT
        assert cand.is_backup_structure is False


def test_scan_lost_exfat_backup_when_primary_wiped(tmp_path: Path) -> None:
    """Acceptance check: wiped primary VBR recovered via exFAT backup boot region."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    # Embed exFAT with WIPED primary VBR at sector 4096, surviving backup at sector 4108
    builder.embed_exfat_volume(
        image=image,
        start_sector=4096,
        total_sectors=3000,
        corrupt_primary=True,
    )

    img_path = tmp_path / "exfat_backup_only.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        candidates = LostVolumeScanner.scan(reader, step_sectors=1)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 4096  # Reconstructed volume start!
        assert cand.sector_count == 3000
        assert cand.filesystem_type == FileSystemType.EXFAT
        assert cand.is_backup_structure is True
        assert "exFAT backup boot region" in cand.detection_source


def test_scan_lost_ntfs_primary(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    builder.embed_ntfs_volume(
        image=image,
        start_sector=2048,
        total_sectors=5000,
        corrupt_primary=False,
    )

    img_path = tmp_path / "ntfs_primary.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        candidates = LostVolumeScanner.scan(reader, step_sectors=8)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 2048
        assert cand.sector_count == 5000
        assert cand.filesystem_type == FileSystemType.NTFS
        assert cand.is_backup_structure is False


def test_scan_lost_ntfs_backup_when_primary_wiped(tmp_path: Path) -> None:
    """Acceptance check: wiped primary boot sector recovered via NTFS backup boot sector."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    # Embed NTFS with WIPED primary at sector 2048, surviving backup at sector 2048 + 5000 = 7048
    builder.embed_ntfs_volume(
        image=image,
        start_sector=2048,
        total_sectors=5000,
        corrupt_primary=True,
    )

    img_path = tmp_path / "ntfs_backup_only.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        candidates = LostVolumeScanner.scan(reader, step_sectors=1)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.start_sector == 2048  # Reconstructed volume start!
        assert cand.sector_count == 5000
        assert cand.filesystem_type == FileSystemType.NTFS
        assert cand.is_backup_structure is True
        assert "NTFS backup boot sector" in cand.detection_source
