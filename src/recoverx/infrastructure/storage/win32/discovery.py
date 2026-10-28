"""Windows storage device and volume discovery using pure ctypes without shell-outs."""

import ctypes
import logging
import sys
from ctypes import wintypes
from dataclasses import dataclass, field

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.win32.api import (
    win32_close_handle,
    win32_create_file,
    win32_device_io_control,
)
from recoverx.infrastructure.storage.win32.constants import (
    BUS_TYPE_NAMES,
    DISK_GEOMETRY_EX,
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GET_LENGTH_INFORMATION,
    INVALID_HANDLE_VALUE,
    IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
    IOCTL_DISK_GET_LENGTH_INFO,
    IOCTL_STORAGE_QUERY_PROPERTY,
    IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS,
    OPEN_EXISTING,
    STORAGE_DEVICE_DESCRIPTOR,
    STORAGE_PROPERTY_QUERY,
    VOLUME_DISK_EXTENTS,
    PropertyStandardQuery,
    StorageDeviceProperty,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredWindowsDevice:
    """Discovered physical drive and associated volume partitions."""

    physical_disk_number: int
    device_path: str
    vendor: str
    product: str
    serial: str
    bus_type: str
    capacity_bytes: int
    sector_size: int
    is_removable: bool
    drive_letters: list[str] = field(default_factory=list)
    filesystem_types: list[str] = field(default_factory=list)
    can_open_direct: bool = True
    requires_elevation: bool = False

    def to_storage_device(self) -> StorageDevice:
        """Convert to domain StorageDevice model."""
        friendly_name = (
            f"{self.vendor} {self.product}".strip() or f"Physical Drive {self.physical_disk_number}"
        )
        ident = DeviceIdentity(
            vendor=self.vendor,
            product=self.product or friendly_name,
            serial=self.serial,
            capacity_bytes=self.capacity_bytes,
            logical_sector_size=self.sector_size,
            physical_sector_size=self.sector_size,
            disk_identifier=self.device_path,
            sector0_hash="",
        )
        return StorageDevice(
            identity=ident,
            bus_type=self.bus_type,
            physical_disk_number=self.physical_disk_number,
            drive_letters=tuple(self.drive_letters),
            is_removable=self.is_removable,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=self.device_path,
        )


class WindowsDeviceEnumerator:
    """Enumerates Windows physical disks and volume extents through audited ctypes APIs.

    Section 2 & 5 of MASTER_PROMPT.md:
    No shell-outs (PowerShell, diskpart, wmic) for device handling.
    Audited Win32 APIs through ctypes only.
    """

    def __init__(self, max_disks: int = 32) -> None:
        self.max_disks = max_disks

    def enumerate_devices(self) -> list[DiscoveredWindowsDevice]:
        """Scan system for physical drives and map associated drive letters."""
        if sys.platform != "win32":
            return []

        # 1. Map volume letters to physical disk numbers
        volume_map = self._map_volumes_to_disks()

        devices: list[DiscoveredWindowsDevice] = []
        for disk_num in range(self.max_disks):
            device_path = f"\\\\.\\PhysicalDrive{disk_num}"
            dev = self._inspect_physical_drive(disk_num, device_path, volume_map.get(disk_num, []))
            if dev is not None:
                devices.append(dev)

        return devices

    def _inspect_physical_drive(
        self,
        disk_num: int,
        device_path: str,
        associated_volumes: list[tuple[str, str]],
    ) -> DiscoveredWindowsDevice | None:
        """Inspect a single PhysicalDriveN device."""
        handle = INVALID_HANDLE_VALUE
        try:
            handle = win32_create_file(
                path=device_path,
                desired_access=GENERIC_READ,
                share_mode=FILE_SHARE_READ | FILE_SHARE_WRITE,
                creation_disposition=OPEN_EXISTING,
                flags_and_attributes=FILE_ATTRIBUTE_NORMAL,
            )
            requires_elevation = False
            can_open_direct = True
        except Exception as exc:
            err_str = str(exc)
            if "Access denied" in err_str:
                # Device exists but current process is unelevated
                requires_elevation = True
                can_open_direct = False
                drive_letters = [vol[0] for vol in associated_volumes]
                fs_types = [vol[1] for vol in associated_volumes if vol[1]]
                return DiscoveredWindowsDevice(
                    physical_disk_number=disk_num,
                    device_path=device_path,
                    vendor="Access Denied",
                    product=f"PhysicalDrive{disk_num} (Elevation Required)",
                    serial="",
                    bus_type="Unknown",
                    capacity_bytes=0,
                    sector_size=512,
                    is_removable=True,
                    drive_letters=drive_letters,
                    filesystem_types=fs_types,
                    can_open_direct=False,
                    requires_elevation=True,
                )
            # Disk does not exist or controller unavailable
            return None

        try:
            # Query capacity
            capacity = 0
            try:
                len_info = GET_LENGTH_INFORMATION()
                win32_device_io_control(handle, IOCTL_DISK_GET_LENGTH_INFO, out_buffer=len_info)
                capacity = int(len_info.Length)
            except Exception:
                pass

            # Query sector size & geometry
            sector_size = 512
            try:
                geom = DISK_GEOMETRY_EX()
                win32_device_io_control(handle, IOCTL_DISK_GET_DRIVE_GEOMETRY_EX, out_buffer=geom)
                if capacity == 0:
                    capacity = int(geom.DiskSize)
                if geom.Geometry.BytesPerSector > 0:
                    sector_size = int(geom.Geometry.BytesPerSector)
            except Exception:
                pass

            # Query storage descriptor (vendor, product, serial, bus type)
            vendor, product, serial, bus_type, removable = self._query_device_descriptor(handle)

            drive_letters = [vol[0] for vol in associated_volumes]
            fs_types = [vol[1] for vol in associated_volumes if vol[1]]

            return DiscoveredWindowsDevice(
                physical_disk_number=disk_num,
                device_path=device_path,
                vendor=vendor,
                product=product,
                serial=serial,
                bus_type=bus_type,
                capacity_bytes=capacity,
                sector_size=sector_size,
                is_removable=removable,
                drive_letters=drive_letters,
                filesystem_types=fs_types,
                can_open_direct=can_open_direct,
                requires_elevation=requires_elevation,
            )
        finally:
            if handle != INVALID_HANDLE_VALUE:
                win32_close_handle(handle)

    def _query_device_descriptor(self, handle: int) -> tuple[str, str, str, str, bool]:
        """Query STORAGE_DEVICE_DESCRIPTOR to extract bus type and device strings."""
        query = STORAGE_PROPERTY_QUERY()
        query.PropertyId = StorageDeviceProperty
        query.QueryType = PropertyStandardQuery

        # Buffer for descriptor (1024 bytes accommodates trailing strings)
        buf_size = 1024
        out_buf = (ctypes.c_ubyte * buf_size)()

        try:
            win32_device_io_control(
                handle,
                IOCTL_STORAGE_QUERY_PROPERTY,
                in_buffer=query,
                out_buffer=out_buf,
            )

            desc = STORAGE_DEVICE_DESCRIPTOR.from_buffer(out_buf)
            removable = bool(desc.RemovableMedia)
            bus_type_code = int(desc.BusType)
            bus_name = BUS_TYPE_NAMES.get(bus_type_code, "Unknown")

            # Extract null-terminated ASCII strings at designated offsets
            raw_bytes = bytes(out_buf)

            def get_string_at(offset: int) -> str:
                if 0 < offset < len(raw_bytes):
                    null_idx = raw_bytes.find(b"\x00", offset)
                    if null_idx != -1:
                        return raw_bytes[offset:null_idx].decode("ascii", errors="replace").strip()
                return ""

            vendor = get_string_at(int(desc.VendorIdOffset))
            product = get_string_at(int(desc.ProductIdOffset))
            serial = get_string_at(int(desc.SerialNumberOffset))

            return vendor, product, serial, bus_name, removable

        except Exception as exc:
            logger.debug("STORAGE_DEVICE_DESCRIPTOR query failed: %s", exc)
            return "Windows", "Generic Disk", "", "Direct", False

    def _map_volumes_to_disks(self) -> dict[int, list[tuple[str, str]]]:
        """Query all drive letters and determine their backing physical disk number."""
        disk_map: dict[int, list[tuple[str, str]]] = {}
        if sys.platform != "win32":
            return disk_map

        # Iterate drive letters A: through Z:
        for letter_code in range(ord("A"), ord("Z") + 1):
            letter = chr(letter_code)
            vol_path = f"\\\\.\\{letter}:"
            handle = INVALID_HANDLE_VALUE
            try:
                handle = win32_create_file(
                    path=vol_path,
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

                # Get filesystem name
                fs_name = self._get_volume_filesystem(f"{letter}:\\")

                for i in range(extents.NumberOfDiskExtents):
                    p_num = int(extents.Extents[i].DiskNumber)
                    disk_map.setdefault(p_num, []).append((f"{letter}:", fs_name))

            except Exception:
                pass
            finally:
                if handle != INVALID_HANDLE_VALUE:
                    win32_close_handle(handle)

        return disk_map

    def _get_volume_filesystem(self, root_path: str) -> str:
        """Call GetVolumeInformationW to retrieve filesystem type."""
        try:
            kernel32 = ctypes.windll.kernel32
            fs_buf = ctypes.create_unicode_buffer(260)
            success = kernel32.GetVolumeInformationW(
                wintypes.LPCWSTR(root_path),
                None,
                0,
                None,
                None,
                None,
                fs_buf,
                len(fs_buf),
            )
            if success:
                return fs_buf.value
        except Exception:
            pass
        return ""
