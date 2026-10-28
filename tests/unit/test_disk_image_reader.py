"""Unit tests for DiskImageReader bounds checking and lifecycle."""

import sys
from pathlib import Path

import pytest

from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
)
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader


@pytest.fixture
def test_image(tmp_path: Path) -> Path:
    builder = SyntheticImageBuilder(total_size_bytes=10000, fill_byte=b"\x00")
    builder.add_file("greeting.bin", b"DATA_AT_100", offset=100)
    manifest = builder.build(tmp_path / "disk.img")
    return manifest.image_path


def test_disk_image_reader_properties(test_image: Path) -> None:
    with DiskImageReader(test_image, logical_sector_size=512) as reader:
        assert reader.size_bytes == 10000
        assert reader.logical_sector_size == 512
        assert reader.total_sectors == 20  # ceil(10000 / 512)
        assert not reader.is_closed
        assert reader.device_info.triage_status == DeviceTriageStatus.SUPPORTED_FILESYSTEM
        assert reader.identity.capacity_bytes == 10000


def test_disk_image_reader_successful_reads(test_image: Path) -> None:
    with DiskImageReader(test_image) as reader:
        # Read exact content placed by builder
        data = reader.read_at(100, 11)
        assert data == b"DATA_AT_100"

        # Read length 0 returns empty bytes
        empty = reader.read_at(500, 0)
        assert empty == b""

        # Read up to the exact last byte
        tail = reader.read_at(9990, 10)
        assert len(tail) == 10


def test_negative_offset_and_length_raise(test_image: Path) -> None:
    with DiskImageReader(test_image) as reader:
        with pytest.raises(DeviceOutOfBoundsError, match="Offset cannot be negative"):
            reader.read_at(-1, 10)

        with pytest.raises(DeviceOutOfBoundsError, match="Length cannot be negative"):
            reader.read_at(10, -1)


def test_out_of_bounds_raises_before_io(test_image: Path) -> None:
    with DiskImageReader(test_image) as reader:
        # Range extends past capacity by 1 byte
        with pytest.raises(DeviceOutOfBoundsError, match="exceeds device capacity"):
            reader.read_at(9995, 10)

        # Offset exactly at capacity
        with pytest.raises(DeviceOutOfBoundsError, match="exceeds device capacity"):
            reader.read_at(10000, 1)

        # Huge offset
        with pytest.raises(DeviceOutOfBoundsError, match="exceeds device capacity"):
            reader.read_at(20000, 10)


def test_integer_overflow_safety(test_image: Path) -> None:
    with DiskImageReader(test_image) as reader:
        # Enormous numbers that would wrap in 64-bit C arithmetic
        with pytest.raises(DeviceOutOfBoundsError):
            reader.read_at(sys.maxsize, 100)

        with pytest.raises(DeviceOutOfBoundsError):
            reader.read_at(100, sys.maxsize)


def test_closed_reader_raises(test_image: Path) -> None:
    reader = DiskImageReader(test_image)
    reader.close()
    assert reader.is_closed

    with pytest.raises(DeviceClosedError, match="closed"):
        reader.read_at(0, 10)

    # Calling close again is safe and idempotent
    reader.close()
