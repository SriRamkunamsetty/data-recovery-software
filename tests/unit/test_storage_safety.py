"""Safety verification tests for read-only block storage abstractions.

Enforces Rule 1 of CLAUDE.md:
The source is read-only by construction.
"""

from pathlib import Path

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceOutOfBoundsError,
    ReadOnlyBlockDevice,
)
from recoverx.infrastructure.storage.fault import FaultInjectionReader
from recoverx.infrastructure.storage.fixtures import (
    ImageHashSnapshot,
    SyntheticImageBuilder,
)
from recoverx.infrastructure.storage.image import DiskImageReader

FORBIDDEN_WRITE_SUBSTRINGS = (
    "write",
    "erase",
    "format",
    "repair",
    "truncate",
    "modify",
    "delete",
    "dismount",
    "lock",
)


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a temporary synthetic disk image for tests."""
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024, fill_byte=b"\xaa")
    builder.add_file("test.txt", b"Hello, Forensics!", offset=2048)
    manifest = builder.build(tmp_path / "safety_test.img")
    return manifest.image_path


def test_no_write_api_on_classes() -> None:
    """Verify ReadOnlyBlockDevice, DiskImageReader, and FaultInjectionReader have no write API."""
    classes_to_check = [ReadOnlyBlockDevice, DiskImageReader, FaultInjectionReader]

    for cls in classes_to_check:
        methods = dir(cls)
        for method_name in methods:
            if method_name.startswith("__"):
                continue
            lower_name = method_name.lower()
            for forbidden in FORBIDDEN_WRITE_SUBSTRINGS:
                assert forbidden not in lower_name, (
                    f"Forbidden write operation '{method_name}' found on {cls.__name__}!"
                )


def test_file_handle_is_strictly_read_only(sample_image: Path) -> None:
    """Verify that the underlying file handle in DiskImageReader is strictly not writable."""
    with DiskImageReader(sample_image) as reader:
        assert reader._handle is not None
        assert not reader._handle.writable()
        assert "b" in reader._handle.mode
        assert "r" in reader._handle.mode
        assert "+" not in reader._handle.mode
        assert "w" not in reader._handle.mode
        assert "a" not in reader._handle.mode


def test_image_hash_unchanged_after_reads(sample_image: Path) -> None:
    """Verify image bytes and cryptographic hash remain 100% unchanged after extensive reads."""
    snapshot = ImageHashSnapshot(sample_image)
    initial_hash = snapshot.initial_sha256

    with DiskImageReader(sample_image) as reader:
        # Read various sectors, boundaries, and chunks
        _ = reader.read_at(0, 512)
        _ = reader.read_at(2048, 17)
        _ = reader.read_at(reader.size_bytes - 512, 512)
        _ = reader.read_at(1024, 4096)

        # Trigger boundary errors
        with pytest.raises(DeviceOutOfBoundsError):
            reader.read_at(reader.size_bytes - 10, 100)

    # Prove immutability
    assert snapshot.verify_unchanged()
    assert snapshot.initial_sha256 == initial_hash
