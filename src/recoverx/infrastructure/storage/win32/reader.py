"""Windows physical disk and volume reader executing strictly read-only sector-aligned I/O."""

import hashlib
import logging
import math

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceDisconnectedError,
    ReadOnlyBlockDevice,
)
from recoverx.infrastructure.storage.win32.api import (
    win32_cancel_io,
    win32_close_handle,
    win32_create_file,
    win32_device_io_control,
    win32_read_file,
    win32_seek,
)
from recoverx.infrastructure.storage.win32.constants import (
    DISK_GEOMETRY_EX,
    FILE_ATTRIBUTE_NORMAL,
    FILE_FLAG_RANDOM_ACCESS,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GET_LENGTH_INFORMATION,
    INVALID_HANDLE_VALUE,
    IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
    IOCTL_DISK_GET_LENGTH_INFO,
    OPEN_EXISTING,
)

logger = logging.getLogger(__name__)


class WindowsRawDeviceReader(ReadOnlyBlockDevice):
    """Strictly read-only block device handle for Windows physical drives and volumes.

    Rule 1 of CLAUDE.md:
    The source is read-only by construction. Exposes only metadata,
    size_bytes, logical_sector_size, read_at(offset, length), and close().
    Never add write, erase, format, repair, partition-edit or filesystem-modify operations.
    """

    def __init__(
        self,
        device_path: str,
        physical_disk_number: int | None = None,
        force_sector_size: int | None = None,
    ) -> None:
        self.device_path = device_path
        self._disk_number = physical_disk_number
        self._handle = INVALID_HANDLE_VALUE
        self._is_closed = True

        # Open handle strictly in read-only mode (Rule 1 of CLAUDE.md)
        # Using FILE_SHARE_READ | FILE_SHARE_WRITE to avoid blocking other readers
        self._handle = win32_create_file(
            path=device_path,
            desired_access=GENERIC_READ,
            share_mode=FILE_SHARE_READ | FILE_SHARE_WRITE,
            creation_disposition=OPEN_EXISTING,
            flags_and_attributes=FILE_ATTRIBUTE_NORMAL | FILE_FLAG_RANDOM_ACCESS,
        )
        self._is_closed = False

        # Query disk geometry & length
        self._size_bytes, self._sector_size = self._query_geometry(force_sector_size)

        # Compute sector 0 fingerprint for forensic identity
        sector0_hash = self._compute_sector0_hash()

        self._identity = DeviceIdentity(
            vendor="Windows",
            product=f"Physical Disk {physical_disk_number}"
            if physical_disk_number is not None
            else device_path,
            serial="",
            capacity_bytes=self._size_bytes,
            logical_sector_size=self._sector_size,
            physical_sector_size=self._sector_size,
            disk_identifier=device_path,
            sector0_hash=sector0_hash,
        )

        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="USB" if "PhysicalDrive" in device_path else "Direct",
            physical_disk_number=self._disk_number,
            drive_letters=(),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=device_path,
        )

        logger.info(
            "Opened Windows raw device %s: size=%d bytes, sector=%d bytes",
            device_path,
            self._size_bytes,
            self._sector_size,
        )

    def _query_geometry(self, force_sector_size: int | None) -> tuple[int, int]:
        """Query disk capacity and logical sector size via IOCTLs."""
        size_bytes = 0
        sector_size = force_sector_size or 512

        # 1. IOCTL_DISK_GET_LENGTH_INFO
        try:
            length_info = GET_LENGTH_INFORMATION()
            win32_device_io_control(
                self._handle,
                IOCTL_DISK_GET_LENGTH_INFO,
                out_buffer=length_info,
            )
            size_bytes = int(length_info.Length)
        except Exception as exc:
            logger.debug("IOCTL_DISK_GET_LENGTH_INFO failed: %s", exc)

        # 2. IOCTL_DISK_GET_DRIVE_GEOMETRY_EX
        try:
            geom_ex = DISK_GEOMETRY_EX()
            win32_device_io_control(
                self._handle,
                IOCTL_DISK_GET_DRIVE_GEOMETRY_EX,
                out_buffer=geom_ex,
            )
            if size_bytes == 0:
                size_bytes = int(geom_ex.DiskSize)
            if force_sector_size is None and geom_ex.Geometry.BytesPerSector > 0:
                sector_size = int(geom_ex.Geometry.BytesPerSector)
        except Exception as exc:
            logger.debug("IOCTL_DISK_GET_DRIVE_GEOMETRY_EX failed: %s", exc)

        if size_bytes <= 0:
            logger.warning("Could not determine disk size for %s; default to 0", self.device_path)

        return size_bytes, sector_size

    def _compute_sector0_hash(self) -> str:
        """Compute SHA-256 fingerprint of sector 0 for forensic integrity."""
        try:
            if self._size_bytes >= self._sector_size:
                data = self.read_at(0, self._sector_size)
                return hashlib.sha256(data).hexdigest()
        except Exception as exc:
            logger.warning("Could not compute sector 0 hash for %s: %s", self.device_path, exc)
        return ""

    @property
    def identity(self) -> DeviceIdentity:
        return self._identity

    @property
    def device_info(self) -> StorageDevice:
        return self._device_info

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    @property
    def logical_sector_size(self) -> int:
        return self._sector_size

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def revalidate_identity(self) -> None:
        """Revalidate device identity to verify drive was not unplugged or replaced.

        Section 5 of MASTER_PROMPT.md:
        Revalidate immediately before every scan, imaging or read session.
        If identity changes or stays ambiguous, refuse.
        """
        if self._is_closed:
            raise DeviceClosedError(f"Cannot revalidate closed device {self.device_path}")

        current_hash = self._compute_sector0_hash()
        if self._identity.sector0_hash and current_hash != self._identity.sector0_hash:
            raise DeviceDisconnectedError(
                f"Device identity mismatch on {self.device_path}! Expected sector 0 hash "
                f"{self._identity.sector0_hash[:16]}..., got {current_hash[:16]}.... "
                "The storage medium may have been swapped or removed."
            )

    def cancel(self) -> bool:
        """Cancel any in-progress or hung I/O requests on this device handle."""
        if not self._is_closed and self._handle != INVALID_HANDLE_VALUE:
            return win32_cancel_io(self._handle)
        return False

    def read_at(self, offset: int, length: int) -> bytes:
        """Read exactly `length` bytes at `offset`, handling sector alignment transparently."""
        self.validate_bounds(offset, length)
        if length == 0:
            return b""

        # Sector alignment for raw physical block I/O
        sec_size = self._sector_size
        aligned_start = (offset // sec_size) * sec_size
        aligned_end = math.ceil((offset + length) / sec_size) * sec_size
        aligned_length = aligned_end - aligned_start

        # Seek to aligned sector start
        win32_seek(self._handle, aligned_start)

        # Read aligned block
        raw_data = win32_read_file(self._handle, aligned_length)
        if len(raw_data) < aligned_length:
            logger.warning(
                "Short read on %s at 0x%X: requested %d bytes, got %d bytes",
                self.device_path,
                aligned_start,
                aligned_length,
                len(raw_data),
            )

        # Extract exact requested slice
        slice_offset = offset - aligned_start
        slice_end = slice_offset + length
        result = raw_data[slice_offset:slice_end]

        return bytes(result)

    def close(self) -> None:
        """Close the underlying Win32 handle."""
        if not self._is_closed:
            self._is_closed = True
            if self._handle != INVALID_HANDLE_VALUE:
                win32_close_handle(self._handle)
                self._handle = INVALID_HANDLE_VALUE
                logger.info("Closed Windows raw device %s", self.device_path)
