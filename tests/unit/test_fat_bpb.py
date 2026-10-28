"""Unit tests for FAT12/16/32 BIOS Parameter Block (BPB) parsing and validation."""

import struct
from pathlib import Path

import pytest

from recoverx.domain.enums import FileSystemType
from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.filesystems.fat.bpb import FatBpb
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.fat_builder import SyntheticFatBuilder


def test_fat32_bpb_parsing_and_geometry(tmp_path: Path) -> None:
    """Verify FAT32 BPB parses geometry, cluster sizes, and calculates offsets accurately."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="USB_FAT32")
    manifest = builder.build(tmp_path / "fat32.img")

    with DiskImageReader(manifest.image_path) as reader:
        bpb = FatBpb.from_reader(reader, base_offset=0)

        assert bpb.filesystem_type == FileSystemType.FAT32
        assert bpb.volume_label == "USB_FAT32"
        assert bpb.bytes_per_sector == 512
        assert bpb.sectors_per_cluster == 1
        assert bpb.cluster_size_bytes == 512
        assert bpb.root_entry_count == 0
        assert bpb.root_cluster == 2
        assert bpb.backup_boot_sector == 6
        assert bpb.num_fats == 2
        assert bpb.total_clusters >= 65525
        assert not bpb.is_backup

        # Offsets
        fat0_off = bpb.fat_offset_bytes(0)
        assert fat0_off == 32 * 512
        fat1_off = bpb.fat_offset_bytes(1)
        assert fat1_off == (32 + 1024) * 512

        # Data cluster 2 offset
        clus2_off = bpb.cluster_to_byte_offset(2)
        assert clus2_off == bpb.first_data_byte_offset


def test_fat16_bpb_parsing_and_geometry(tmp_path: Path) -> None:
    """Verify FAT16 BPB parses root directory offset and cluster counts."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT16, volume_label="USB_FAT16")
    manifest = builder.build(tmp_path / "fat16.img")

    with DiskImageReader(manifest.image_path) as reader:
        bpb = FatBpb.from_reader(reader, base_offset=0)

        assert bpb.filesystem_type == FileSystemType.FAT16
        assert bpb.volume_label == "USB_FAT16"
        assert bpb.sectors_per_cluster == 4
        assert bpb.cluster_size_bytes == 2048
        assert bpb.root_entry_count == 512
        assert 4085 <= bpb.total_clusters < 65525

        root_off = bpb.root_dir_offset_bytes
        assert root_off == (1 + (2 * 32)) * 512


def test_fat12_bpb_parsing_and_geometry(tmp_path: Path) -> None:
    """Verify FAT12 BPB geometry for 1.44M floppy layout."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT12, volume_label="FLOPPY")
    manifest = builder.build(tmp_path / "fat12.img")

    with DiskImageReader(manifest.image_path) as reader:
        bpb = FatBpb.from_reader(reader, base_offset=0)

        assert bpb.filesystem_type == FileSystemType.FAT12
        assert bpb.volume_label == "FLOPPY"
        assert bpb.total_clusters < 4085
        assert bpb.root_entry_count == 224


def test_corrupted_boot_signature_triggers_backup_boot_sector(tmp_path: Path) -> None:
    """If sector 0 signature is bad, FAT32 falls back to backup boot sector (sector 6)."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="BK_TEST")
    manifest = builder.build(tmp_path / "fat32_corrupt_sec0.img")

    # Corrupt sector 0 signature
    img_bytes = bytearray(manifest.image_path.read_bytes())
    img_bytes[510:512] = b"\x00\x00"  # Ruin 0x55, 0xAA signature
    manifest.image_path.write_bytes(img_bytes)

    with DiskImageReader(manifest.image_path) as reader:
        # Should cleanly recover via backup sector 6
        bpb = FatBpb.from_reader(reader, base_offset=0)
        assert bpb.is_backup
        assert bpb.filesystem_type == FileSystemType.FAT32
        assert bpb.volume_label == "BK_TEST"


def test_corrupted_bpb_parameters_rejected() -> None:
    """Invalid sector size or non-power-of-two clusters must raise CorruptedBootSectorError."""
    # Sector too short
    with pytest.raises(CorruptedBootSectorError, match="too short"):
        FatBpb.from_bytes(b"\x00" * 100)

    # Missing 0x55AA signature
    valid_sec = bytearray(512)
    valid_sec[510:512] = b"\x55\xaa"

    # Bad bytes per sector (e.g. 300)
    struct.pack_into("<H", valid_sec, 11, 300)
    with pytest.raises(CorruptedBootSectorError, match="Invalid bytes per sector"):
        FatBpb.from_bytes(bytes(valid_sec))

    # Bad sectors per cluster (e.g. 3, not power of 2)
    struct.pack_into("<H", valid_sec, 11, 512)
    valid_sec[13] = 3
    with pytest.raises(CorruptedBootSectorError, match="sectors per cluster"):
        FatBpb.from_bytes(bytes(valid_sec))
