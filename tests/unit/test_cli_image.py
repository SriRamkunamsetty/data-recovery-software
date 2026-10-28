"""Unit tests for `recoverx image` CLI command."""

import json
from pathlib import Path

import pytest

from recoverx.cli import main


def _create_source(path: Path, size_bytes: int = 32 * 1024) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pattern = b"TEST_CLI_IMAGE_PAYLOAD_12345"
    data = (pattern * ((size_bytes // len(pattern)) + 1))[:size_bytes]
    path.write_bytes(data)


def test_cli_image_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src_path = tmp_path / "cli_source.img"
    _create_source(src_path)
    dest_path = tmp_path / "dest" / "cli_output.img"

    exit_code = main(["image", str(src_path), str(dest_path), "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["is_complete"] is True
    assert data["bad_sectors"] == 0
    assert data["total_sectors"] > 0
    assert data["sha256"] is not None
    assert dest_path.exists()


def test_cli_image_table_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src_path = tmp_path / "table_source.img"
    _create_source(src_path)
    dest_path = tmp_path / "dest" / "table_output.img"

    exit_code = main(["image", str(src_path), str(dest_path)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Destination Image :" in captured.out
    assert "Acquisition Status: COMPLETE" in captured.out


def test_cli_image_missing_source_returns_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src_path = tmp_path / "missing.img"
    dest_path = tmp_path / "dest" / "out.img"

    exit_code = main(["image", str(src_path), str(dest_path)])
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "Error: Source image not found" in captured.err
