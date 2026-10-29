"""Unit tests for NTFS boot sector parsing and backup validation."""

import pytest

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.infrastructure.storage.memory import MemoryBlockDevice


def create_minimal_ntfs_boot_sector(
    bytes_per_sec: int = 512,
    sec_per_clus: int = 8,
    total_sectors: int = 16384,
    mft_lcn: int = 4,
    mft_mirr_lcn: int = 2,
    clusters_per_mft: int = -10,
) -> bytes:
    """Build a minimal valid NTFS boot sector byte sequence."""
    buf = bytearray(512)
    buf[0:3] = b"\xeb\x52\x90"
    buf[3:11] = b"NTFS    "
    buf[11:13] = bytes_per_sec.to_bytes(2, "little")
    buf[13] = sec_per_clus
    buf[40:48] = total_sectors.to_bytes(8, "little")
    buf[48:56] = mft_lcn.to_bytes(8, "little")
    buf[56:64] = mft_mirr_lcn.to_bytes(8, "little")
    buf[64] = clusters_per_mft & 0xFF
    buf[68] = (-12) & 0xFF
    buf[72:80] = (0x123456789ABCDEF0).to_bytes(8, "little")
    buf[510:512] = b"\x55\xaa"
    return bytes(buf)


def test_ntfs_boot_sector_valid() -> None:
    """Test parsing a valid 512-byte NTFS boot sector."""
    raw = create_minimal_ntfs_boot_sector(
        bytes_per_sec=512,
        sec_per_clus=8,
        total_sectors=32768,
        mft_lcn=10,
        mft_mirr_lcn=5,
        clusters_per_mft=-10,
    )
    boot = NtfsBootSector.from_bytes(raw, base_offset=1024)

    assert boot.oem_id == b"NTFS    "
    assert boot.bytes_per_sector == 512
    assert boot.sectors_per_cluster == 8
    assert boot.cluster_size == 4096
    assert boot.total_sectors == 32768
    assert boot.total_clusters == 4096
    assert boot.volume_size_bytes == 32768 * 512
    assert boot.mft_record_size == 1024  # 2**10
    assert boot.mft_start_lcn == 10
    assert boot.mft_mirr_start_lcn == 5
    assert boot.mft_byte_offset == 1024 + (10 * 4096)
    assert boot.mft_mirr_byte_offset == 1024 + (5 * 4096)
    assert boot.is_backup is False


def test_ntfs_boot_sector_positive_clusters_per_mft() -> None:
    """Test clusters_per_mft_record when specified as positive cluster count."""
    raw = create_minimal_ntfs_boot_sector(clusters_per_mft=1)
    boot = NtfsBootSector.from_bytes(raw)
    assert boot.mft_record_size == 4096  # 1 * cluster_size


def test_ntfs_boot_sector_corrupt_oem() -> None:
    """Test rejection when OEM ID is invalid."""
    buf = bytearray(create_minimal_ntfs_boot_sector())
    buf[3:11] = b"FAT32   "
    with pytest.raises(CorruptedBootSectorError, match="Invalid NTFS OEM ID"):
        NtfsBootSector.from_bytes(bytes(buf))


def test_ntfs_boot_sector_corrupt_signature() -> None:
    """Test rejection when 0x55AA signature is corrupted."""
    buf = bytearray(create_minimal_ntfs_boot_sector())
    buf[510:512] = b"\x00\x00"
    with pytest.raises(CorruptedBootSectorError, match="Invalid boot sector signature"):
        NtfsBootSector.from_bytes(bytes(buf))


def test_ntfs_boot_sector_backup_fallback() -> None:
    """Test automatic fallback to backup boot sector at the end of volume."""
    valid_boot = create_minimal_ntfs_boot_sector(total_sectors=2048)
    total_bytes = 2048 * 512

    raw_img = bytearray(total_bytes)
    # Primary at offset 0 is zeroed/corrupt
    # Backup placed at the very last sector
    raw_img[total_bytes - 512 :] = valid_boot

    reader = MemoryBlockDevice(data=bytes(raw_img))
    try:
        boot = NtfsBootSector.from_reader(reader, base_offset=0)
        assert boot.is_backup is True
        assert boot.cluster_size == 4096
        assert boot.total_sectors == 2048
    finally:
        reader.close()
