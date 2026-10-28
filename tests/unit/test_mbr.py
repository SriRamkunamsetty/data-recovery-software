"""Unit tests for Master Boot Record (MBR) and EBR parsing."""

from pathlib import Path

from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.partitions.mbr import (
    MBR_SIGNATURE,
    MBR_TABLE_OFFSET,
    MBR_TYPE_FAT32_LBA,
    MBR_TYPE_NTFS_EXFAT,
    MBR_TYPE_PROTECTIVE_GPT,
    MbrParser,
)
from tests.fixtures.partition_builder import SyntheticPartitionBuilder


def test_parse_valid_mbr_two_partitions(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=20000)
    builder.add_partition(
        start_lba=2048,
        sector_count=4096,
        type_code_or_guid=f"0x{MBR_TYPE_FAT32_LBA:02X}",
        name="Data FAT32",
        is_bootable=True,
    )
    builder.add_partition(
        start_lba=8192,
        sector_count=8192,
        type_code_or_guid=f"0x{MBR_TYPE_NTFS_EXFAT:02X}",
        name="Data NTFS",
        is_bootable=False,
    )

    image_data = builder.build_mbr_image()
    img_path = tmp_path / "test_mbr.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is not None
        assert mbr_table.disk_signature == 0x12345678
        assert not mbr_table.is_protective

        infos = mbr_table.to_partition_infos()
        assert len(infos) == 2

        part1 = infos[0]
        assert part1.partition_number == 1
        assert part1.start_sector == 2048
        assert part1.sector_count == 4096
        assert part1.start_offset_bytes == 2048 * 512
        assert part1.size_bytes == 4096 * 512
        assert part1.is_bootable is True

        part2 = infos[1]
        assert part2.partition_number == 2
        assert part2.start_sector == 8192
        assert part2.sector_count == 8192
        assert part2.is_bootable is False


def test_parse_mbr_missing_signature_returns_none(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=5000)
    builder.add_partition(start_lba=100, sector_count=1000)
    image_data = builder.build_mbr_image(corrupt_signature=True)

    img_path = tmp_path / "bad_sig_mbr.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is None


def test_parse_protective_mbr(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(
        start_lba=1,
        sector_count=9999,
        type_code_or_guid=f"0x{MBR_TYPE_PROTECTIVE_GPT:02X}",
    )
    image_data = builder.build_mbr_image()

    img_path = tmp_path / "protective_mbr.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is not None
        assert mbr_table.is_protective is True
        # Protective partition should not be exposed as a normal data partition
        infos = mbr_table.to_partition_infos()
        assert len(infos) == 0


def test_parse_mbr_corrupted_boot_indicator_notes(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=2048)
    image_data = builder.build_mbr_image(corrupt_boot_indicator=True)

    img_path = tmp_path / "corrupt_flag_mbr.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is not None
        assert any("non-standard boot indicator" in note for note in mbr_table.notes)


def test_parse_mbr_ebr_chain_logical_partitions(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=20000)
    image_data = builder.build_ebr_chain_image()

    img_path = tmp_path / "ebr_chain.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is not None

        # Should contain 1 primary (extended) + 2 logical partitions
        assert len(mbr_table.entries) == 6  # 4 primary slots + 2 logical
        logical = [e for e in mbr_table.entries if e.is_logical]
        assert len(logical) == 2

        # First logical partition: ext_base (2000) + 1 = 2001, count 1000
        assert logical[0].lba_start == 2001
        assert logical[0].sector_count == 1000

        # Second logical partition: ext_base (2000) + rel (2000) + 1 = 4001, count 800
        assert logical[1].lba_start == 4001
        assert logical[1].sector_count == 800


def test_parse_mbr_ebr_loop_protection(tmp_path: Path) -> None:
    image = bytearray(10000 * 512)
    image[510:512] = MBR_SIGNATURE

    # Primary entry 0 points to EBR at sector 100
    ext_lba = 100
    image[MBR_TABLE_OFFSET + 4] = 0x05  # Extended CHS
    image[MBR_TABLE_OFFSET + 8 : MBR_TABLE_OFFSET + 12] = ext_lba.to_bytes(4, "little")
    image[MBR_TABLE_OFFSET + 12 : MBR_TABLE_OFFSET + 16] = (5000).to_bytes(4, "little")

    # EBR at sector 100 points entry 2 back to sector 100 (rel offset 0) -> circular loop!
    ebr_offset = ext_lba * 512
    image[ebr_offset + 510 : ebr_offset + 512] = MBR_SIGNATURE
    e2 = ebr_offset + MBR_TABLE_OFFSET + 16
    image[e2 + 4] = 0x05
    image[e2 + 8 : e2 + 12] = (0).to_bytes(4, "little")  # 100 + 0 = 100
    image[e2 + 12 : e2 + 16] = (100).to_bytes(4, "little")

    img_path = tmp_path / "ebr_loop.img"
    img_path.write_bytes(image)

    with DiskImageReader(img_path) as reader:
        mbr_table = MbrParser.parse(reader)
        assert mbr_table is not None
        assert any("EBR loop detected" in n for n in mbr_table.notes)
