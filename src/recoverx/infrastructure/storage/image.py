"""Read-only disk image block device implementation."""

import hashlib
import os
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)


class DiskImageReader(ReadOnlyBlockDevice):
    """Memory-safe, bounds-checked reader for disk images.

    Opens raw disk images (.img, .raw, .dd, .bin) strictly in read-only binary mode.
    Exposes no write, truncate, or flush APIs.
    """

    def __init__(
        self,
        image_path: str | Path,
        logical_sector_size: int = 512,
        physical_sector_size: int = 512,
        vendor: str = "Virtual",
        product: str = "DiskImage",
        serial: str = "",
        custom_metadata: Mapping[str, str] | None = None,
    ) -> None:
        self._path = Path(image_path).resolve()
        if not self._path.exists():
            raise FileNotFoundError(f"Disk image file not found: {self._path}")
        if not self._path.is_file():
            raise ValueError(f"Path is not a regular file: {self._path}")

        # Open strictly in read-only binary mode
        self._handle: BinaryIO | None = open(self._path, "rb")  # noqa: SIM115

        # Explicit safety assertion: ensure handle is strictly not writable
        if self._handle.writable():
            self._handle.close()
            raise PermissionError("Disk image handle must be read-only.")

        self._size_bytes = os.path.getsize(self._path)
        self._logical_sector_size = logical_sector_size
        self._physical_sector_size = physical_sector_size
        self._is_closed = False

        # Read sector 0 for fingerprint hash
        sector0_hash = ""
        if self._size_bytes >= self._logical_sector_size:
            self._handle.seek(0)
            sector0 = self._handle.read(self._logical_sector_size)
            if len(sector0) == self._logical_sector_size:
                sector0_hash = hashlib.sha256(sector0).hexdigest()

        # Derive serial or disk identifier from path/hash if empty
        disk_id = f"IMG-{hashlib.sha256(str(self._path).encode()).hexdigest()[:8].upper()}"
        device_serial = serial or disk_id

        self._identity = DeviceIdentity(
            vendor=vendor,
            product=product,
            serial=device_serial,
            capacity_bytes=self._size_bytes,
            logical_sector_size=self._logical_sector_size,
            physical_sector_size=self._physical_sector_size,
            disk_identifier=disk_id,
            sector0_hash=sector0_hash,
            is_serial_synthetic_or_generic=serial == "",
        )

        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="VirtualImage",
            physical_disk_number=None,
            drive_letters=(),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            triage_notes=f"Disk image: {self._path.name}",
            last_io_error=None,
            source_path=str(self._path),
        )

    @property
    def path(self) -> Path:
        """Absolute canonical path to the disk image."""
        return self._path

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
        return self._logical_sector_size

    @property
    def is_closed(self) -> bool:
        return self._is_closed or self._handle is None or self._handle.closed

    def read_at(self, offset: int, length: int) -> bytes:
        """Perform a bounds-checked, read-only read from the disk image."""
        self.validate_bounds(offset, length)

        if self.is_closed or self._handle is None:
            raise DeviceClosedError("Disk image reader is closed.")

        if length == 0:
            return b""

        try:
            self._handle.seek(offset)
            data = self._handle.read(length)
        except OSError as e:
            raise DeviceReadError(f"I/O error reading at offset {offset}: {e}") from e

        if len(data) != length:
            raise DeviceReadError(
                f"Short read at offset {offset}: requested {length} bytes, got {len(data)}"
            )

        return data

    def close(self) -> None:
        """Close the underlying file handle cleanly and idempotently."""
        if not self._is_closed and self._handle is not None:
            self._handle.close()
            self._is_closed = True
            self._handle = None
