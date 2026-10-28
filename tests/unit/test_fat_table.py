"""Unit tests for FAT12, FAT16, and FAT32 allocation table decoding and chain checking."""

import struct
from pathlib import Path

from recoverx.domain.enums import FileSystemType
from recoverx.filesystems.fat.fat_table import FatTableReader
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader


def test_fat12_table_decoding(tmp_path: Path) -> None:
    """Verify FAT12 12-bit entry unpacking for even and odd cluster indices."""
    # Build a small dummy image for testing FAT12 decoding
    builder = SyntheticImageBuilder(total_size_bytes=4096)
    manifest = builder.build(tmp_path / "fat12_test.bin")

    # Construct FAT12 table bytes:
    # Cluster 0 and 1: F8 FF FF (3 bytes)
    # Cluster 2: 0x003 (even), Cluster 3: 0xFFF (odd)
    # Combined into 3 bytes: 0x003 and 0xFFF ->
    # Byte 0: 0x03
    # Byte 1: (0x0F << 4) | (0x00) = 0xF0
    # Byte 2: 0xFF
    fat12_raw = bytearray(512)
    fat12_raw[0:3] = b"\xf8\xff\xff"
    fat12_raw[3:6] = b"\x03\xf0\xff"

    with open(manifest.image_path, "r+b") as f:
        f.seek(0)
        f.write(fat12_raw)

    with DiskImageReader(manifest.image_path) as reader:
        fat_reader = FatTableReader(
            reader=reader,
            fat_offset_bytes=0,
            fat_size_bytes=512,
            filesystem_type=FileSystemType.FAT12,
            total_clusters=100,
        )

        assert fat_reader.get_cluster_value(2) == 0x003
        assert fat_reader.get_cluster_value(3) == 0x0FFF
        assert fat_reader.is_end_of_chain(fat_reader.get_cluster_value(3))
        assert not fat_reader.is_cluster_free(2)
        assert fat_reader.is_cluster_free(4)  # cluster 4 is 0


def test_fat16_table_decoding(tmp_path: Path) -> None:
    """Verify FAT16 16-bit word decoding and contiguous chain verification."""
    builder = SyntheticImageBuilder(total_size_bytes=4096)
    manifest = builder.build(tmp_path / "fat16_test.bin")

    fat16_raw = bytearray(512)
    struct.pack_into("<H", fat16_raw, 0, 0xFFF8)
    struct.pack_into("<H", fat16_raw, 2, 0xFFFF)
    struct.pack_into("<H", fat16_raw, 4, 0x0000)  # cluster 2 free
    struct.pack_into("<H", fat16_raw, 6, 0x0000)  # cluster 3 free
    struct.pack_into("<H", fat16_raw, 8, 0x0005)  # cluster 4 allocated!

    with open(manifest.image_path, "r+b") as f:
        f.seek(0)
        f.write(fat16_raw)

    with DiskImageReader(manifest.image_path) as reader:
        fat_reader = FatTableReader(
            reader=reader,
            fat_offset_bytes=0,
            fat_size_bytes=512,
            filesystem_type=FileSystemType.FAT16,
            total_clusters=100,
        )

        # Contiguous check for 2 clusters starting at cluster 2 (clusters 2 and 3)
        all_free, bad = fat_reader.check_contiguous_chain(start_cluster=2, count=2)
        assert all_free
        assert len(bad) == 0

        # Contiguous check for 3 clusters (2, 3, 4) -> cluster 4 is allocated!
        all_free_3, bad_3 = fat_reader.check_contiguous_chain(start_cluster=2, count=3)
        assert not all_free_3
        assert bad_3 == [4]


def test_fat32_table_decoding(tmp_path: Path) -> None:
    """Verify FAT32 32-bit dword decoding with 28-bit cluster masking."""
    builder = SyntheticImageBuilder(total_size_bytes=4096)
    manifest = builder.build(tmp_path / "fat32_test.bin")

    fat32_raw = bytearray(512)
    # Upper 4 bits set to 0xF, cluster pointer 0x01234567
    struct.pack_into("<I", fat32_raw, 8, 0xF1234567)  # cluster 2

    with open(manifest.image_path, "r+b") as f:
        f.seek(0)
        f.write(fat32_raw)

    with DiskImageReader(manifest.image_path) as reader:
        fat_reader = FatTableReader(
            reader=reader,
            fat_offset_bytes=0,
            fat_size_bytes=512,
            filesystem_type=FileSystemType.FAT32,
            total_clusters=100,
        )

        # Upper 4 bits must be masked away!
        assert fat_reader.get_cluster_value(2) == 0x01234567
