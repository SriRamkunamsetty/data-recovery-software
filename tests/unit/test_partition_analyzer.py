"""Unit tests for the top-level PartitionAnalyzer orchestrator."""

from pathlib import Path

from recoverx.domain.enums import FileSystemType
from recoverx.filesystems.fat.parser import FatFileSystem
from recoverx.infrastructure.storage.fixtures import ImageHashSnapshot
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.partitions.analyzer import PartitionAnalyzer
from recoverx.partitions.models import (
    GptHeaderHealth,
    PartitionTableType,
)
from tests.fixtures.fat_builder import SyntheticFatBuilder
from tests.fixtures.partition_builder import SyntheticPartitionBuilder


def test_analyze_mbr_disk(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="MBR Data")
    image_data = builder.build_mbr_image()

    img_path = tmp_path / "analyzer_mbr.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        result = PartitionAnalyzer.analyze(reader)
        assert result.table_type == PartitionTableType.MBR
        assert len(result.partitions) == 1
        assert result.partitions[0].start_sector == 2048
        assert result.partitions[0].sector_count == 4096
        assert len(result.volume_candidates) == 1
        assert result.volume_candidates[0].start_sector == 2048


def test_analyze_gpt_disk_healthy(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="GPT Data")
    image_data = builder.build_gpt_image()

    img_path = tmp_path / "analyzer_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        result = PartitionAnalyzer.analyze(reader)
        assert result.table_type == PartitionTableType.GPT
        assert result.gpt_health == GptHeaderHealth.BOTH_VALID
        assert len(result.partitions) == 1
        assert result.partitions[0].start_sector == 2048
        assert result.partitions[0].name == "GPT Data"


def test_analyze_gpt_damaged_primary_recovers_via_backup(tmp_path: Path) -> None:
    """Acceptance check: damaged-primary and intact-backup GPT case is reported and recovered."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="Backup Recov Partition")
    image_data = builder.build_gpt_image(corrupt_primary_header_crc=True)

    img_path = tmp_path / "analyzer_damaged_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        result = PartitionAnalyzer.analyze(reader)
        assert result.table_type == PartitionTableType.GPT
        assert result.gpt_health == GptHeaderHealth.BACKUP_VALID_PRIMARY_CORRUPT
        assert len(result.partitions) == 1
        assert result.partitions[0].start_sector == 2048
        assert result.partitions[0].name == "Backup Recov Partition"


def test_analyze_wiped_table_lost_volumes(tmp_path: Path) -> None:
    """Acceptance check: wiped partition table triggers lost volume discovery."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    image = bytearray(10000 * 512)

    # Embed FAT32 volume with primary wiped, surviving backup at sector 2054
    builder.embed_fat32_volume(
        image=image,
        start_sector=2048,
        total_sectors=3000,
        corrupt_primary=True,
    )

    img_path = tmp_path / "wiped_table.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        result = PartitionAnalyzer.analyze(reader, scan_lost_volumes_if_empty=True)
        assert result.table_type == PartitionTableType.NONE
        assert len(result.partitions) == 0
        assert len(result.volume_candidates) == 1
        cand = result.volume_candidates[0]
        assert cand.start_sector == 2048
        assert cand.filesystem_type == FileSystemType.FAT32
        assert cand.is_backup_structure is True


def test_in_memory_subdevice_and_metadata_recovery_immutability(tmp_path: Path) -> None:
    """Verify that recovered volume offset feeds into metadata parser without modifying device."""
    # 1. Build a genuine FAT32 volume image with files using SyntheticFatBuilder
    fat_builder = SyntheticFatBuilder(
        fs_type=FileSystemType.FAT32,
        volume_label="PART_FAT32",
    )
    fat_builder.add_file(
        "TEST_DOC.TXT",
        b"Forensic recovered text via partition subdevice!",
        is_deleted=True,
    )
    fat_inner_path = tmp_path / "fat32_inner.img"
    fat_builder.build(fat_inner_path)
    fat_image_bytes = fat_inner_path.read_bytes()

    # 2. Place this FAT32 filesystem inside a partitioned disk image at sector 2048
    part_start_sector = 2048
    part_sector_count = len(fat_image_bytes) // 512
    total_disk_sectors = part_start_sector + part_sector_count + 100

    disk_builder = SyntheticPartitionBuilder(total_sectors=total_disk_sectors)
    disk_builder.add_partition(
        start_lba=part_start_sector,
        sector_count=part_sector_count,
        name="FAT32 Volume",
    )
    disk_image = disk_builder.build_mbr_image()

    # Copy the FAT32 volume into the partition area
    part_start_offset = part_start_sector * 512
    disk_image[part_start_offset : part_start_offset + len(fat_image_bytes)] = fat_image_bytes

    img_path = tmp_path / "partitioned_disk.img"
    img_path.write_bytes(disk_image)

    # Record snapshot hash to assert source immutability
    snapshot = ImageHashSnapshot(img_path)

    # 3. Analyze partitions on the disk image
    with DiskImageReader(img_path) as reader:
        result = PartitionAnalyzer.analyze(reader)
        assert result.table_type == PartitionTableType.MBR
        assert len(result.partitions) == 1
        part_info = result.partitions[0]

        # 4. Create in-memory SubDeviceReader
        sub_dev = PartitionAnalyzer.create_subdevice(reader, part_info)
        assert sub_dev.base_offset == part_start_offset
        assert sub_dev.size_bytes == part_info.size_bytes

        # 5. Run real metadata recovery on the sub-device
        fs = FatFileSystem()
        assert fs.detect(sub_dev) is True

        fs_info = fs.get_fs_info(sub_dev)
        assert fs_info is not None
        assert fs_info.fs_type == FileSystemType.FAT32

        candidates = list(fs.recover_candidates(sub_dev))
        assert len(candidates) >= 1
        found_file = next(c for c in candidates if "TEST_DOC.TXT" in c.filename)
        assert found_file is not None

        sub_dev.close()

    # 6. Verify source device was NEVER written to (immutability check)
    assert snapshot.verify_unchanged()
