"""Unit tests for `recoverx recover` CLI command."""

import json
from pathlib import Path

import pytest

from recoverx.cli import main
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from tests.fixtures.sample_files import create_minimal_png


@pytest.fixture
def cli_image_and_dest(tmp_path: Path) -> tuple[Path, Path]:
    png_data = create_minimal_png()
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    builder.add_file("icon.png", png_data, offset=2048)
    manifest = builder.build(tmp_path / "cli_source.img")

    dest_dir = tmp_path / "cli_recovered"
    dest_dir.mkdir()
    return manifest.image_path, dest_dir


def test_cli_recover_json_output(
    cli_image_and_dest: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    img_path, dest_dir = cli_image_and_dest

    exit_code = main(["recover", str(img_path), str(dest_dir), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["status"] == "success"
    assert data[0]["bytes_written"] == 69
    assert data[0]["hash_verified"] is True

    # Verify file was written to disk
    recovered_file = Path(data[0]["destination_path"])
    assert recovered_file.exists()


def test_cli_recover_table_output(
    cli_image_and_dest: tuple[Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    img_path, dest_dir = cli_image_and_dest

    exit_code = main(["recover", str(img_path), str(dest_dir)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Recovered 1 file(s)" in captured.out
    assert "success" in captured.out


def test_cli_recover_missing_image(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["recover", "missing_image.img", str(tmp_path)])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Error: Disk image not found" in captured.err
