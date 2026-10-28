"""Unit tests for Windows raw device reader with sector alignment and safety invariants."""

import hashlib
from unittest.mock import patch

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceDisconnectedError,
    DeviceOutOfBoundsError,
)
from recoverx.infrastructure.storage.win32.reader import WindowsRawDeviceReader


@pytest.fixture
def mock_storage_data() -> bytes:
    """Deterministic synthetic disk content: 16 sectors of 512 bytes = 8192 bytes."""
    sectors = [bytes([(s * 17 + i) % 256 for i in range(512)]) for s in range(16)]
    return b"".join(sectors)


def test_windows_raw_device_reader_open_and_properties(mock_storage_data: bytes) -> None:
    """Test device initialization, geometry queries, and identity hashing."""
    with (
        patch("recoverx.infrastructure.storage.win32.reader.win32_create_file", return_value=101),
        patch("recoverx.infrastructure.storage.win32.reader.win32_close_handle") as mock_close,
        patch.object(WindowsRawDeviceReader, "_query_geometry", return_value=(8192, 512)),
        patch("recoverx.infrastructure.storage.win32.reader.win32_seek"),
        patch(
            "recoverx.infrastructure.storage.win32.reader.win32_read_file",
            return_value=mock_storage_data[:512],
        ),
    ):
        reader = WindowsRawDeviceReader(
            device_path=r"\\.\PhysicalDrive2",
            physical_disk_number=2,
        )

        assert reader.size_bytes == 8192
        assert reader.logical_sector_size == 512
        closed_initially = reader.is_closed
        assert not closed_initially
        assert reader.device_path == r"\\.\PhysicalDrive2"
        assert reader.device_info.physical_disk_number == 2
        assert reader.identity.sector0_hash == hashlib.sha256(mock_storage_data[:512]).hexdigest()

        reader.close()
        assert reader.is_closed
        mock_close.assert_called_once_with(101)


def test_windows_raw_device_reader_aligned_and_unaligned_read(mock_storage_data: bytes) -> None:
    """Test read_at handles sector alignment slicing accurately."""

    def fake_seek_and_read(handle: int, length: int) -> bytes:
        # Mock reading based on current offset
        return mock_storage_data[current_offset[0] : current_offset[0] + length]

    current_offset = [0]

    def fake_seek(handle: int, offset: int) -> int:
        current_offset[0] = offset
        return offset

    with (
        patch("recoverx.infrastructure.storage.win32.reader.win32_create_file", return_value=102),
        patch("recoverx.infrastructure.storage.win32.reader.win32_close_handle"),
        patch.object(WindowsRawDeviceReader, "_query_geometry", return_value=(8192, 512)),
        patch("recoverx.infrastructure.storage.win32.reader.win32_seek", side_effect=fake_seek),
        patch(
            "recoverx.infrastructure.storage.win32.reader.win32_read_file",
            side_effect=fake_seek_and_read,
        ),
    ):
        reader = WindowsRawDeviceReader(
            device_path=r"\\.\PhysicalDrive3",
            physical_disk_number=3,
        )

        # 1. Zero length read
        assert reader.read_at(0, 0) == b""

        # 2. Exactly aligned read of sector 0
        s0 = reader.read_at(0, 512)
        assert s0 == mock_storage_data[0:512]

        # 3. Unaligned read within sector 1 (e.g. offset 600, len 50)
        unaligned = reader.read_at(600, 50)
        assert unaligned == mock_storage_data[600:650]

        # 4. Read spanning sector boundary (e.g. offset 500, len 100 spans sector 0 and 1)
        spanning = reader.read_at(500, 100)
        assert spanning == mock_storage_data[500:600]

        # 5. Out of bounds read raises DeviceOutOfBoundsError
        with pytest.raises(DeviceOutOfBoundsError):
            reader.read_at(8100, 200)

        reader.close()
        # 6. Read after close raises DeviceClosedError
        with pytest.raises(DeviceClosedError):
            reader.read_at(0, 512)


def test_windows_raw_device_reader_revalidation(mock_storage_data: bytes) -> None:
    """Section 5 of MASTER_PROMPT.md: revalidate_identity detects drive removal or swap."""
    sector0_orig = mock_storage_data[:512]
    sector0_swapped = bytes([(b + 1) % 256 for b in sector0_orig])

    current_data = [sector0_orig]

    def fake_seek_and_read(handle: int, length: int) -> bytes:
        return current_data[0]

    with (
        patch("recoverx.infrastructure.storage.win32.reader.win32_create_file", return_value=103),
        patch("recoverx.infrastructure.storage.win32.reader.win32_close_handle"),
        patch.object(WindowsRawDeviceReader, "_query_geometry", return_value=(8192, 512)),
        patch("recoverx.infrastructure.storage.win32.reader.win32_seek"),
        patch(
            "recoverx.infrastructure.storage.win32.reader.win32_read_file",
            side_effect=fake_seek_and_read,
        ),
    ):
        reader = WindowsRawDeviceReader(
            device_path=r"\\.\PhysicalDrive4",
            physical_disk_number=4,
        )

        # Same sector 0 -> passes revalidation
        reader.revalidate_identity()

        # Swapped drive -> sector 0 hash changes -> raises DeviceDisconnectedError
        current_data[0] = sector0_swapped
        with pytest.raises(DeviceDisconnectedError, match="identity mismatch"):
            reader.revalidate_identity()

        reader.close()
        with pytest.raises(DeviceClosedError):
            reader.revalidate_identity()


def test_windows_raw_device_reader_cancel() -> None:
    """Test reader.cancel calls win32_cancel_io."""
    with (
        patch("recoverx.infrastructure.storage.win32.reader.win32_create_file", return_value=104),
        patch("recoverx.infrastructure.storage.win32.reader.win32_close_handle"),
        patch.object(WindowsRawDeviceReader, "_query_geometry", return_value=(8192, 512)),
        patch("recoverx.infrastructure.storage.win32.reader.win32_seek"),
        patch(
            "recoverx.infrastructure.storage.win32.reader.win32_read_file",
            return_value=b"\x00" * 512,
        ),
        patch(
            "recoverx.infrastructure.storage.win32.reader.win32_cancel_io", return_value=True
        ) as mock_cancel,
    ):
        reader = WindowsRawDeviceReader(device_path=r"\\.\PhysicalDrive5", physical_disk_number=5)
        assert reader.cancel() is True
        mock_cancel.assert_called_once_with(104)
        reader.close()
        assert reader.cancel() is False
