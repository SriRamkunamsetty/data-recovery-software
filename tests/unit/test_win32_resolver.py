"""Unit tests for Windows native volume and physical disk identity resolver."""

from pathlib import Path
from unittest.mock import patch

import pytest

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import (
    AmbiguousSeparationError,
    DestinationOnSourceError,
    VolumeIdentity,
)
from recoverx.infrastructure.storage.win32.resolver import WindowsVolumeIdentityResolver


class DummyBlockDevice(ReadOnlyBlockDevice):
    def __init__(
        self, source_path: str, physical_disk_number: int | None, volume_id: str = ""
    ) -> None:
        self._source_path = source_path
        self._disk_num = physical_disk_number
        self._identity = DeviceIdentity(
            vendor="TestVendor",
            product="TestProduct",
            serial="123456",
            capacity_bytes=1024 * 1024,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier=volume_id or source_path,
            sector0_hash="",
        )
        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="USB",
            physical_disk_number=physical_disk_number,
            drive_letters=(),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=source_path,
        )

    @property
    def identity(self) -> DeviceIdentity:
        return self._identity

    @property
    def device_info(self) -> StorageDevice:
        return self._device_info

    @property
    def size_bytes(self) -> int:
        return 1024 * 1024

    @property
    def logical_sector_size(self) -> int:
        return 512

    @property
    def is_closed(self) -> bool:
        return False

    def read_at(self, offset: int, length: int) -> bytes:
        return b"\x00" * length

    def close(self) -> None:
        pass


def test_windows_resolver_resolve_path() -> None:
    """Test resolving drive letter paths to volume serial and physical disk number."""
    resolver = WindowsVolumeIdentityResolver()

    with (
        patch("sys.platform", "win32"),
        patch.object(resolver, "_get_volume_serial", return_value="VOL-SERIAL-1234ABCD"),
        patch.object(resolver, "_get_physical_disk_for_drive", return_value=0),
    ):
        ident = resolver.resolve_path(r"C:\recoverx_output\data")
        assert ident.physical_disk_number == 0
        assert ident.volume_id == "VOL-SERIAL-1234ABCD"
        assert ident.mount_point == "C:\\"


def test_windows_resolver_unc_path_ambiguity() -> None:
    """Test UNC or non-drive paths raise AmbiguousSeparationError on Windows."""
    resolver = WindowsVolumeIdentityResolver()
    with (
        patch("sys.platform", "win32"),
        pytest.raises(AmbiguousSeparationError, match="drive letter"),
    ):
        resolver.resolve_path(r"\\network_nas\backups")


def test_windows_resolver_device_resolution_and_separation_enforcement() -> None:
    """Rules 2 & 3 of CLAUDE.md: source and destination cannot share same disk or volume."""
    resolver = WindowsVolumeIdentityResolver()

    source_usb = DummyBlockDevice(
        r"\\.\PhysicalDrive1", physical_disk_number=1, volume_id="VOL-USB-1"
    )

    # Destination on disk 1 (same physical disk) -> MUST raise DestinationOnSourceError
    with (
        patch("sys.platform", "win32"),
        patch.object(
            resolver,
            "resolve_path",
            return_value=VolumeIdentity(
                volume_id="VOL-E",
                physical_disk_number=1,
                device_path=r"E:\recovered",
                mount_point="E:\\",
            ),
        ),
        pytest.raises(DestinationOnSourceError, match="SAME PHYSICAL DISK"),
    ):
        resolver.verify_separation(source_usb, Path(r"E:\recovered"))

    # Destination on disk 0 (different physical disk) -> MUST succeed
    with (
        patch("sys.platform", "win32"),
        patch.object(
            resolver,
            "resolve_path",
            return_value=VolumeIdentity(
                volume_id="VOL-C",
                physical_disk_number=0,
                device_path=r"C:\recovered",
                mount_point="C:\\",
            ),
        ),
    ):
        # Should not raise any error
        resolver.verify_separation(source_usb, Path(r"C:\recovered"))


def test_windows_resolver_disk_image_host_separation() -> None:
    """If source is an image on C:, destination on C: must be rejected (Rule 2)."""
    resolver = WindowsVolumeIdentityResolver()
    source_img = DummyBlockDevice(r"C:\images\source.raw", physical_disk_number=None)

    with (
        patch("sys.platform", "win32"),
        patch.object(
            resolver,
            "resolve_path",
            side_effect=[
                # First call resolving host volume of image:
                VolumeIdentity(
                    volume_id="VOL-C",
                    physical_disk_number=0,
                    device_path=r"C:\images\source.raw",
                    mount_point="C:\\",
                ),
                # Second call resolving destination path:
                VolumeIdentity(
                    volume_id="VOL-C",
                    physical_disk_number=0,
                    device_path=r"C:\recovered",
                    mount_point="C:\\",
                ),
            ],
        ),
        pytest.raises(DestinationOnSourceError),
    ):
        resolver.verify_separation(source_img, Path(r"C:\recovered"))
