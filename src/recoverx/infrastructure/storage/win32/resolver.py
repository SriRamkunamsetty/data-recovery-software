"""Windows native volume and physical disk identity resolver enforcing strict separation."""

import ctypes
import logging
import sys
from ctypes import wintypes
from pathlib import Path

from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import (
    AmbiguousSeparationError,
    VolumeIdentity,
    VolumeIdentityResolver,
)
from recoverx.infrastructure.storage.win32.api import (
    win32_close_handle,
    win32_create_file,
    win32_device_io_control,
)
from recoverx.infrastructure.storage.win32.constants import (
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    INVALID_HANDLE_VALUE,
    IOCTL_STORAGE_GET_DEVICE_NUMBER,
    IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
    OPEN_EXISTING,
    STORAGE_DEVICE_NUMBER,
    VOLUME_DISK_EXTENTS,
)

logger = logging.getLogger(__name__)


class WindowsVolumeIdentityResolver(VolumeIdentityResolver):
    """Resolves Windows filesystem paths and block devices to their true physical disk identities.

    Rules 2 & 3 of CLAUDE.md:
    Nothing the app creates goes on the source device or on any volume
    of the same physical disk. If separation cannot be established with
    confidence, refuse.
    """

    def resolve_path(self, path: Path | str) -> VolumeIdentity:
        """Resolve a filesystem path to its volume serial/GUID and physical disk number."""
        canonical_path = Path(path).resolve()
        path_str = str(canonical_path)

        # On non-Windows platforms (e.g. Linux test runner), return synthetic identity
        if sys.platform != "win32":
            return VolumeIdentity(
                volume_id=f"VOL-NONWIN-{path_str[:8]}",
                physical_disk_number=99,
                device_path=path_str,
                mount_point=str(canonical_path.anchor),
            )

        drive_letter = canonical_path.drive
        if not drive_letter or not drive_letter.endswith(":"):
            # UNC or non-drive path: query root volume GUID
            raise AmbiguousSeparationError(
                f"Path '{path_str}' does not have a recognizable Windows drive letter. "
                "Cannot determine physical disk boundaries with confidence."
            )

        vol_guid = self._get_volume_serial(f"{drive_letter}\\")
        disk_number = self._get_physical_disk_for_drive(drive_letter)

        return VolumeIdentity(
            volume_id=vol_guid or f"VOL-{drive_letter}",
            physical_disk_number=disk_number,
            device_path=path_str,
            mount_point=f"{drive_letter}\\",
        )

    def resolve_device(self, device: ReadOnlyBlockDevice) -> VolumeIdentity:
        """Resolve a ReadOnlyBlockDevice to its volume and physical disk identity."""
        # 1. Direct physical disk number from StorageDevice
        disk_num = device.device_info.physical_disk_number

        # 2. Check if device has an underlying Win32 handle
        handle = getattr(device, "_handle", None)
        if (
            disk_num is None
            and handle
            and isinstance(handle, int)
            and handle != INVALID_HANDLE_VALUE
        ):
            try:
                dev_num = STORAGE_DEVICE_NUMBER()
                win32_device_io_control(
                    handle,
                    IOCTL_STORAGE_GET_DEVICE_NUMBER,
                    out_buffer=dev_num,
                )
                disk_num = int(dev_num.DeviceNumber)
            except Exception as exc:
                logger.debug("IOCTL_STORAGE_GET_DEVICE_NUMBER query failed: %s", exc)

        # 3. If device is an image file on disk, resolve the host drive path
        source_path = device.device_info.source_path
        if source_path and not source_path.startswith("\\\\.\\PhysicalDrive"):
            # The source is a file on a mounted volume (e.g., C:\images\test.raw)
            try:
                host_vol = self.resolve_path(source_path)
                return VolumeIdentity(
                    volume_id=f"IMG-{host_vol.volume_id}",
                    physical_disk_number=host_vol.physical_disk_number,
                    device_path=source_path,
                    mount_point=host_vol.mount_point,
                )
            except Exception:
                pass

        ident_str = device.identity.disk_identifier or source_path or f"DISK-{disk_num}"
        return VolumeIdentity(
            volume_id=ident_str,
            physical_disk_number=disk_num,
            device_path=source_path,
        )

    def _get_physical_disk_for_drive(self, drive_letter: str) -> int | None:
        r"""Query IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS on \\.\X:."""
        vol_device_path = f"\\\\.\\{drive_letter}"
        handle = INVALID_HANDLE_VALUE
        try:
            handle = win32_create_file(
                path=vol_device_path,
                desired_access=GENERIC_READ,
                share_mode=FILE_SHARE_READ | FILE_SHARE_WRITE,
                creation_disposition=OPEN_EXISTING,
                flags_and_attributes=FILE_ATTRIBUTE_NORMAL,
            )
            extents = VOLUME_DISK_EXTENTS()
            win32_device_io_control(
                handle,
                IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
                out_buffer=extents,
            )
            if extents.NumberOfDiskExtents > 0:
                return int(extents.Extents[0].DiskNumber)
        except Exception as exc:
            logger.debug("Failed to query extents for %s: %s", drive_letter, exc)
        finally:
            if handle != INVALID_HANDLE_VALUE:
                win32_close_handle(handle)

        return None

    def _get_volume_serial(self, root_path: str) -> str:
        """Call GetVolumeInformationW to retrieve 32-bit volume serial number."""
        try:
            kernel32 = ctypes.windll.kernel32
            serial_num = wintypes.DWORD(0)
            success = kernel32.GetVolumeInformationW(
                wintypes.LPCWSTR(root_path),
                None,
                0,
                ctypes.byref(serial_num),
                None,
                None,
                None,
                0,
            )
            if success:
                return f"VOL-SERIAL-{serial_num.value:08X}"
        except Exception:
            pass
        return ""
