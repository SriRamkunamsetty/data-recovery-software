"""Unit tests for GUID Partition Table (GPT) parsing and backup CRC validation."""

from pathlib import Path

from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.partitions.gpt import (
    GPT_TYPE_WINDOWS_BASIC_DATA,
    GptParser,
)
from recoverx.partitions.models import GptHeaderHealth
from tests.fixtures.partition_builder import SyntheticPartitionBuilder


def test_parse_gpt_both_headers_valid(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(
        start_lba=2048,
        sector_count=4096,
        type_code_or_guid=GPT_TYPE_WINDOWS_BASIC_DATA,
        name="Recovered Volume",
    )
    image_data = builder.build_gpt_image()

    img_path = tmp_path / "valid_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        gpt_table = GptParser.parse(reader)
        assert gpt_table is not None
        assert gpt_table.health == GptHeaderHealth.BOTH_VALID
        assert gpt_table.recovered_from_backup is False
        assert gpt_table.disk_guid == builder.disk_guid

        infos = gpt_table.to_partition_infos()
        assert len(infos) == 1
        assert infos[0].partition_number == 1
        assert infos[0].start_sector == 2048
        assert infos[0].sector_count == 4096
        assert infos[0].name == "Recovered Volume"
        assert infos[0].partition_type_or_guid == GPT_TYPE_WINDOWS_BASIC_DATA


def test_parse_gpt_damaged_primary_intact_backup(tmp_path: Path) -> None:
    """Acceptance check: a damaged-primary and intact-backup GPT case is reported correctly."""
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(
        start_lba=2048,
        sector_count=4096,
        type_code_or_guid=GPT_TYPE_WINDOWS_BASIC_DATA,
        name="Backup Recovered Partition",
    )
    # Corrupt primary header CRC32
    image_data = builder.build_gpt_image(corrupt_primary_header_crc=True)

    img_path = tmp_path / "damaged_primary_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        gpt_table = GptParser.parse(reader)
        assert gpt_table is not None
        assert gpt_table.health == GptHeaderHealth.BACKUP_VALID_PRIMARY_CORRUPT
        assert gpt_table.recovered_from_backup is True

        # Partitions must be recovered from intact backup
        infos = gpt_table.to_partition_infos()
        assert len(infos) == 1
        assert infos[0].start_sector == 2048
        assert infos[0].sector_count == 4096
        assert infos[0].name == "Backup Recovered Partition"


def test_parse_gpt_intact_primary_damaged_backup(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(
        start_lba=2048,
        sector_count=2048,
        type_code_or_guid=GPT_TYPE_WINDOWS_BASIC_DATA,
        name="Primary Partition",
    )
    image_data = builder.build_gpt_image(corrupt_backup_header_crc=True)

    img_path = tmp_path / "damaged_backup_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        gpt_table = GptParser.parse(reader)
        assert gpt_table is not None
        assert gpt_table.health == GptHeaderHealth.PRIMARY_VALID_BACKUP_CORRUPT
        assert gpt_table.recovered_from_backup is False

        infos = gpt_table.to_partition_infos()
        assert len(infos) == 1
        assert infos[0].start_sector == 2048


def test_parse_gpt_both_corrupt(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=2048)
    image_data = builder.build_gpt_image(
        corrupt_primary_header_crc=True,
        corrupt_backup_header_crc=True,
    )

    img_path = tmp_path / "both_corrupt_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        gpt_table = GptParser.parse(reader)
        assert gpt_table is not None
        assert gpt_table.health == GptHeaderHealth.BOTH_CORRUPT
        assert any("failed CRC validation" in note for note in gpt_table.notes)


def test_parse_gpt_non_gpt_returns_none(tmp_path: Path) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=5000)
    image_data = builder.build_mbr_image()  # Pure MBR, no GPT headers

    img_path = tmp_path / "no_gpt.img"
    img_path.write_bytes(image_data)

    with DiskImageReader(img_path) as reader:
        gpt_table = GptParser.parse(reader)
        assert gpt_table is None
