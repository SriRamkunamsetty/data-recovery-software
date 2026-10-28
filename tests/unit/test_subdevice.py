"""Unit tests for in-memory SubDeviceReader partition offset mapping."""

from pathlib import Path

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
)
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.subdevice import SubDeviceReader


def test_subdevice_read_translation(tmp_path: Path) -> None:
    # 20KB disk image filled with sequence
    data = bytearray(20480)
    # Fill partition at offset 4096 (size 8192) with pattern
    data[4096 : 4096 + 8192] = b"SUBDEVICE_PAYLOAD" * (8192 // 17) + b"END"

    img_path = tmp_path / "test_subdevice.img"
    img_path.write_bytes(data)

    with DiskImageReader(img_path) as parent:
        sub = SubDeviceReader(
            parent=parent,
            base_offset=4096,
            size_bytes=8192,
            name="partition1",
        )

        assert sub.base_offset == 4096
        assert sub.size_bytes == 8192
        assert sub.logical_sector_size == parent.logical_sector_size
        assert sub.name == "partition1"

        # Reading at offset 0 of subdevice should yield data at offset 4096 of parent
        content = sub.read_at(0, 17)
        assert content == b"SUBDEVICE_PAYLOAD"

        # Read across arbitrary inner range
        inner = sub.read_at(17, 17)
        assert inner == b"SUBDEVICE_PAYLOAD"

        # Reading 0 bytes returns empty bytes
        assert sub.read_at(100, 0) == b""


def test_subdevice_bounds_enforcement(tmp_path: Path) -> None:
    img_path = tmp_path / "bounds.img"
    img_path.write_bytes(b"\x00" * 10240)

    with DiskImageReader(img_path) as parent:
        # Invalid base_offset
        with pytest.raises(ValueError, match="base_offset cannot be negative"):
            SubDeviceReader(parent, base_offset=-1, size_bytes=1000)

        # Invalid size_bytes
        with pytest.raises(ValueError, match="size_bytes cannot be negative"):
            SubDeviceReader(parent, base_offset=0, size_bytes=-1)

        # Exceeds parent
        with pytest.raises(ValueError, match="exceeds parent device capacity"):
            SubDeviceReader(parent, base_offset=8000, size_bytes=5000)

        sub = SubDeviceReader(parent, base_offset=2048, size_bytes=4096)

        # Read out of bounds of the sub-device
        with pytest.raises(DeviceOutOfBoundsError):
            sub.read_at(4096, 1)

        with pytest.raises(DeviceOutOfBoundsError):
            sub.read_at(4000, 200)

        with pytest.raises(DeviceOutOfBoundsError):
            sub.read_at(-1, 10)


def test_subdevice_read_only_safety_by_construction(tmp_path: Path) -> None:
    """Verify that SubDeviceReader strictly enforces Rule 1 of CLAUDE.md."""
    img_path = tmp_path / "safety.img"
    img_path.write_bytes(b"\x00" * 4096)

    with DiskImageReader(img_path) as parent:
        sub = SubDeviceReader(parent, base_offset=512, size_bytes=1024)

        # Assert total absence of write/modify APIs
        for forbidden in ("write", "write_at", "erase", "format", "repair", "truncate", "flush"):
            assert not hasattr(sub, forbidden), f"SubDeviceReader must not expose {forbidden}()"


def test_subdevice_closed_behavior(tmp_path: Path) -> None:
    img_path = tmp_path / "closed.img"
    img_path.write_bytes(b"\x00" * 4096)

    with DiskImageReader(img_path) as parent:
        sub = SubDeviceReader(parent, base_offset=512, size_bytes=1024)
        sub.close()
        assert sub.is_closed

        with pytest.raises(DeviceClosedError):
            sub.read_at(0, 512)
