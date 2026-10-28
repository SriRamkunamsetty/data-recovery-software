"""Unit tests for Windows device enumerator and discovery model."""

from unittest.mock import patch

from recoverx.domain.device import StorageDevice
from recoverx.infrastructure.storage.win32.discovery import (
    DiscoveredWindowsDevice,
    WindowsDeviceEnumerator,
)


def test_discovered_windows_device_to_storage_device() -> None:
    """Test conversion of discovered device to domain StorageDevice."""
    disc = DiscoveredWindowsDevice(
        physical_disk_number=1,
        device_path=r"\\.\PhysicalDrive1",
        vendor="SanDisk",
        product="Ultra USB 3.0",
        serial="4C531001",
        bus_type="USB",
        capacity_bytes=32 * 1024 * 1024 * 1024,
        sector_size=512,
        is_removable=True,
        drive_letters=["E:"],
        filesystem_types=["FAT32"],
        can_open_direct=True,
        requires_elevation=False,
    )

    dev = disc.to_storage_device()
    assert isinstance(dev, StorageDevice)
    assert dev.physical_disk_number == 1
    assert dev.identity.vendor == "SanDisk"
    assert dev.identity.product == "Ultra USB 3.0"
    assert dev.identity.capacity_bytes == 32 * 1024 * 1024 * 1024
    assert dev.drive_letters == ("E:",)
    assert dev.is_removable is True
    assert dev.is_read_only is True


def test_windows_device_enumerator_non_windows() -> None:
    """Test enumerator returns empty list on non-Windows platforms."""
    enumerator = WindowsDeviceEnumerator(max_disks=4)
    with patch("sys.platform", "linux"):
        devices = enumerator.enumerate_devices()
        assert devices == []


def test_windows_device_enumerator_scans_disks() -> None:
    """Test enumerator iterates physical drives and maps volume letters."""
    enumerator = WindowsDeviceEnumerator(max_disks=3)

    mock_dev0 = DiscoveredWindowsDevice(
        physical_disk_number=0,
        device_path=r"\\.\PhysicalDrive0",
        vendor="NVMe",
        product="Samsung SSD",
        serial="S123",
        bus_type="NVMe",
        capacity_bytes=512 * 1024 * 1024 * 1024,
        sector_size=512,
        is_removable=False,
        drive_letters=["C:"],
    )

    mock_dev1 = DiscoveredWindowsDevice(
        physical_disk_number=1,
        device_path=r"\\.\PhysicalDrive1",
        vendor="SanDisk",
        product="Cruzer",
        serial="S456",
        bus_type="USB",
        capacity_bytes=16 * 1024 * 1024 * 1024,
        sector_size=512,
        is_removable=True,
        drive_letters=["D:"],
    )

    with (
        patch("sys.platform", "win32"),
        patch.object(enumerator, "_map_volumes_to_disks", return_value={0: ["C:"], 1: ["D:"]}),
        patch.object(
            enumerator, "_inspect_physical_drive", side_effect=[mock_dev0, mock_dev1, None]
        ),
    ):
        devices = enumerator.enumerate_devices()
        assert len(devices) == 2
        assert devices[0].physical_disk_number == 0
        assert devices[1].physical_disk_number == 1
