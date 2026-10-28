"""Unit tests for `recoverx scan` CLI command."""

import json
from pathlib import Path

import pytest

from recoverx.cli import main
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from tests.fixtures.sample_files import create_minimal_png


@pytest.fixture
def cli_test_image(tmp_path: Path) -> Path:
    png_data = create_minimal_png()
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    builder.add_file("sample.png", png_data, offset=4096)
    manifest = builder.build(tmp_path / "cli_scan.img")
    return manifest.image_path


def test_cli_scan_json_output(cli_test_image: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test `recoverx scan IMAGE --json` outputs valid machine-readable JSON."""
    exit_code = main(["scan", str(cli_test_image), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 1
    item = data[0]
    assert item["extension"] == "png"
    assert item["source_offset"] == 4096
    assert item["status"] == "Preview validated"
    assert item["sha256"] is not None


def test_cli_scan_table_output(cli_test_image: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test `recoverx scan IMAGE` without --json prints human-readable table."""
    exit_code = main(["scan", str(cli_test_image)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Discovered 1 candidate(s)" in captured.out
    assert "png" in captured.out
    assert "0x00001000" in captured.out


def test_cli_scan_missing_file_returns_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test non-existent file produces error code 1."""
    exit_code = main(["scan", "nonexistent_disk_image.img"])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Error: Disk image not found" in captured.err


def test_cli_scan_fat_metadata(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test `recoverx scan` detects FAT filesystem and recovers deleted files via metadata."""
    from recoverx.domain.enums import FileSystemType
    from tests.fixtures.fat_builder import SyntheticFatBuilder

    png_data = create_minimal_png()
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="CLI_FAT")
    builder.add_file("DeletedPhoto.png", png_data, is_deleted=True)
    manifest = builder.build(tmp_path / "fat_cli.img")

    exit_code = main(["scan", str(manifest.image_path), "--no-carve", "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert len(data) == 1
    assert data[0]["filename"] == "DeletedPhoto.png"
    assert data[0]["status"] == "Preview validated"
