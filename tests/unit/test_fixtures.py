"""Unit tests for synthetic fixtures and image hash snapshot verification."""

from pathlib import Path

import pytest

from recoverx.infrastructure.storage.fixtures import (
    ImageHashSnapshot,
    SyntheticImageBuilder,
)


def test_synthetic_image_builder_creates_expected_manifest(tmp_path: Path) -> None:
    builder = SyntheticImageBuilder(total_size_bytes=8192, fill_byte=b"\x00")
    f1 = builder.add_file("file1.txt", b"ABCDEFGHIJ", offset=1024)
    f2 = builder.add_file("file2.bin", b"\xff\xfe\xfd", offset=4096)

    out_file = tmp_path / "test_manifest.img"
    manifest = builder.build(out_file)

    assert manifest.image_path == out_file
    assert manifest.total_size_bytes == 8192
    assert len(manifest.files) == 2
    assert manifest.get_file("file1.txt") == f1
    assert manifest.get_file("file2.bin") == f2

    # Verify bytes on disk match
    with open(out_file, "rb") as f:
        f.seek(1024)
        assert f.read(10) == b"ABCDEFGHIJ"
        f.seek(4096)
        assert f.read(3) == b"\xff\xfe\xfd"


def test_synthetic_image_builder_rejects_overflow() -> None:
    builder = SyntheticImageBuilder(total_size_bytes=1000)
    with pytest.raises(ValueError, match="exceeds image capacity"):
        builder.add_file("overflow.bin", b"X" * 500, offset=600)


def test_image_hash_snapshot_detects_tampering(tmp_path: Path) -> None:
    test_path = tmp_path / "tamper_test.img"
    content = b"ORIGINAL_IMMUTABLE_DATA" * 50
    test_path.write_bytes(content)

    snapshot = ImageHashSnapshot(test_path)
    assert snapshot.verify_unchanged()

    # Tamper with 1 byte in the file
    with open(test_path, "r+b") as f:
        f.seek(10)
        f.write(b"Z")

    with pytest.raises(AssertionError, match="Image content modified"):
        snapshot.verify_unchanged()


def test_image_hash_snapshot_detects_truncation(tmp_path: Path) -> None:
    test_path = tmp_path / "truncation_test.img"
    test_path.write_bytes(b"DATA" * 100)

    snapshot = ImageHashSnapshot(test_path)

    # Truncate file
    with open(test_path, "wb") as f:
        f.write(b"DATA" * 10)

    with pytest.raises(AssertionError, match="Image size modified"):
        snapshot.verify_unchanged()
