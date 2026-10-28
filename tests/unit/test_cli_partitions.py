"""Unit tests for `recoverx partitions` CLI command."""

import json
from pathlib import Path

import pytest

from recoverx.cli import main
from tests.fixtures.partition_builder import SyntheticPartitionBuilder


def test_cli_partitions_mbr_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="Test Part")
    image_data = builder.build_mbr_image()

    img_path = tmp_path / "cli_part_mbr.img"
    img_path.write_bytes(image_data)

    exit_code = main(["partitions", str(img_path), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["table_type"] == "MBR"
    assert len(data["partitions"]) == 1
    assert data["partitions"][0]["start_sector"] == 2048
    assert data["partitions"][0]["sector_count"] == 4096


def test_cli_partitions_gpt_damaged_primary_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="Backup Recov")
    image_data = builder.build_gpt_image(corrupt_primary_header_crc=True)

    img_path = tmp_path / "cli_damaged_gpt.img"
    img_path.write_bytes(image_data)

    exit_code = main(["partitions", str(img_path), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["table_type"] == "GPT"
    assert data["gpt_health"] == "Backup valid, primary corrupt"
    assert len(data["partitions"]) == 1
    assert data["partitions"][0]["name"] == "Backup Recov"


def test_cli_partitions_human_readable_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    builder = SyntheticPartitionBuilder(total_sectors=10000)
    builder.add_partition(start_lba=2048, sector_count=4096, name="Data Volume")
    image_data = builder.build_mbr_image()

    img_path = tmp_path / "cli_table.img"
    img_path.write_bytes(image_data)

    exit_code = main(["partitions", str(img_path)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Partition Scheme: MBR" in captured.out
    assert "Discovered 1 partition(s):" in captured.out
    assert "2048" in captured.out
