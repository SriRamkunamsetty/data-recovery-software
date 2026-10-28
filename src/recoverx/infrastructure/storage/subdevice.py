"""In-memory sub-device reader for partitions and lost volumes."""

import hashlib

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    ReadOnlyBlockDevice,
)


class SubDeviceReader(ReadOnlyBlockDevice):
    """In-memory read-only block device representing a partition or volume slice.

    Translates offsets strictly in memory without ever writing to the underlying
    source device (Rule 1 of CLAUDE.md).
    """

    def __init__(
        self,
        parent: ReadOnlyBlockDevice,
        base_offset: int,
        size_bytes: int,
        name: str = "",
        close_parent: bool = False,
    ) -> None:
        if base_offset < 0:
            raise ValueError(f"base_offset cannot be negative: {base_offset}")
        if size_bytes < 0:
            raise ValueError(f"size_bytes cannot be negative: {size_bytes}")
        if base_offset > parent.size_bytes:
            raise ValueError(
                f"base_offset ({base_offset}) exceeds parent device capacity ({parent.size_bytes})"
            )
        if base_offset > parent.size_bytes - size_bytes:
            raise ValueError(
                f"Range [{base_offset}, {base_offset + size_bytes}) exceeds "
                f"parent device capacity ({parent.size_bytes})"
            )

        self._parent = parent
        self._base_offset = base_offset
        self._size_bytes = size_bytes
        self._name = name or f"partition@{base_offset}"
        self._close_parent = close_parent
        self._closed = False

        # Sector 0 fingerprint of this sub-volume
        sector_size = parent.logical_sector_size
        if size_bytes >= sector_size and not parent.is_closed:
            first_sector = parent.read_at(base_offset, sector_size)
            sector_0_sha256 = hashlib.sha256(first_sector).hexdigest()
        else:
            sector_0_sha256 = hashlib.sha256(b"").hexdigest()

        self._identity = DeviceIdentity(
            vendor=parent.identity.vendor,
            product=f"{parent.identity.product} ({self._name})",
            serial=parent.identity.serial,
            capacity_bytes=size_bytes,
            logical_sector_size=sector_size,
            physical_sector_size=parent.identity.physical_sector_size,
            disk_identifier=f"{parent.identity.disk_identifier}#{self._name}",
            sector0_hash=sector_0_sha256,
        )

        parent_info = parent.device_info
        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type=parent_info.bus_type,
            physical_disk_number=parent_info.physical_disk_number,
            drive_letters=(),
            is_removable=parent_info.is_removable,
            is_read_only=True,
            triage_status=parent_info.triage_status,
            triage_notes=f"SubDevice slice at offset {base_offset} (size {size_bytes}B)",
            source_path=f"{parent_info.source_path}#{self._name}",
        )

    @property
    def parent(self) -> ReadOnlyBlockDevice:
        """Underlying parent block device."""
        return self._parent

    @property
    def base_offset(self) -> int:
        """Starting byte offset of this sub-device on the parent."""
        return self._base_offset

    @property
    def name(self) -> str:
        """Name or label of this sub-device slice."""
        return self._name

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
        return self._parent.logical_sector_size

    @property
    def is_closed(self) -> bool:
        return self._closed or self._parent.is_closed

    def read_at(self, offset: int, length: int) -> bytes:
        if self._closed:
            raise DeviceClosedError("Cannot read from a closed SubDeviceReader.")
        self.validate_bounds(offset, length)
        if length == 0:
            return b""
        return self._parent.read_at(self._base_offset + offset, length)

    def close(self) -> None:
        self._closed = True
        if self._close_parent and not self._parent.is_closed:
            self._parent.close()
