"""Unit tests for exFAT Volume Boot Record (VBR) parsing, geometry, and checksum verification."""

import struct
from pathlib import Path

import pytest

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.filesystems.exfat.vbr import ExFatVbr, calculate_exfat_vbr_checksum
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.exfat_builder import SyntheticExFatBuilder


def test_exfat_vbr_parsing_and_geometry(tmp_path: Path) -> None:
    """Verify exFAT VBR decodes geometry, shifts, and offsets accurately."""
    builder = SyntheticExFatBuilder(volume_label="MY_EXFAT", total_sectors=32768)
    manifest = builder.build(tmp_path / "exfat.img")

    with DiskImageReader(manifest.image_path) as reader:
        vbr = ExFatVbr.from_reader(reader, base_offset=0)

        assert vbr.bytes_per_sector == 512
        assert vbr.sectors_per_cluster == 8
        assert vbr.cluster_size_bytes == 4096
        assert vbr.cluster_count > 0
        assert vbr.root_cluster == 2
        assert not vbr.is_backup
        assert vbr.cluster_heap_offset_sectors == 128

        # Cluster 2 offset
        clus2_off = vbr.cluster_to_byte_offset(2)
        assert clus2_off == vbr.cluster_heap_byte_offset


def test_exfat_vbr_checksum_verification(tmp_path: Path) -> None:
    """Verify that sector 11 checksum matches calculation over sectors 0..10."""
    builder = SyntheticExFatBuilder(volume_label="CHECKSUM_TEST")
    manifest = builder.build(tmp_path / "exfat_chk.img")

    img_bytes = manifest.image_path.read_bytes()
    vbr_region = img_bytes[0 : 12 * 512]

    expected_chk = calculate_exfat_vbr_checksum(vbr_region, 512)
    (actual_chk,) = struct.unpack_from("<I", vbr_region, 11 * 512)
    assert expected_chk == actual_chk


def test_exfat_corrupted_primary_falls_back_to_backup_boot_region(tmp_path: Path) -> None:
    """When primary sector 0 has a corrupted signature, fallback to backup region (sector 12)."""
    builder = SyntheticExFatBuilder(volume_label="BACKUP_TEST")
    manifest = builder.build(tmp_path / "exfat_backup.img")

    # Corrupt primary sector 0 boot signature
    raw = bytearray(manifest.image_path.read_bytes())
    raw[510:512] = b"\x00\x00"
    manifest.image_path.write_bytes(raw)

    with DiskImageReader(manifest.image_path) as reader:
        vbr = ExFatVbr.from_reader(reader, base_offset=0)
        assert vbr.is_backup
        assert vbr.cluster_size_bytes == 4096


def test_exfat_corrupted_vbr_parameters_rejected() -> None:
    """Invalid OEM name or bad sector shift must raise CorruptedBootSectorError."""
    # Sector too short
    with pytest.raises(CorruptedBootSectorError, match="too short"):
        ExFatVbr.from_bytes(b"\x00" * 200)

    # Missing 0x55AA signature
    sec = bytearray(512)
    sec[3:11] = b"EXFAT   "
    sec[510:512] = b"\x12\x34"
    with pytest.raises(CorruptedBootSectorError, match="Invalid boot signature"):
        ExFatVbr.from_bytes(bytes(sec))

    # Invalid OEM name
    sec[510:512] = b"\x55\xaa"
    sec[3:11] = b"NOTEXFAT"
    with pytest.raises(CorruptedBootSectorError, match="Invalid exFAT OEM name"):
        ExFatVbr.from_bytes(bytes(sec))
