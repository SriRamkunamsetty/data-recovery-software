"""In-memory read-only block device backed by an immutable byte buffer."""

import hashlib

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    ReadOnlyBlockDevice,
)


class MemoryBlockDevice(ReadOnlyBlockDevice):
    """In-memory read-only block device for testing, synthetic buffers, and memory images."""

    def __init__(
        self,
        data: bytes,
        sector_size: int = 512,
        device_id: str = "memory://device",
    ) -> None:
        if sector_size <= 0:
            raise ValueError(f"sector_size must be positive: {sector_size}")

        self._data = bytes(data)
        self._sector_size = sector_size
        self._device_id = device_id
        self._is_closed = False

        sec0 = self._data[:sector_size] if len(self._data) >= sector_size else self._data
        sec0_hash = hashlib.sha256(sec0).hexdigest()

        self._identity = DeviceIdentity(
            vendor="Virtual",
            product="MemoryDevice",
            serial="MEM001",
            capacity_bytes=len(self._data),
            logical_sector_size=sector_size,
            physical_sector_size=sector_size,
            disk_identifier=device_id,
            sector0_hash=sec0_hash,
        )
        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="Virtual",
            physical_disk_number=None,
            drive_letters=(),
            is_removable=False,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=device_id,
        )

    @property
    def identity(self) -> DeviceIdentity:
        return self._identity

    @property
    def device_info(self) -> StorageDevice:
        return self._device_info

    @property
    def size_bytes(self) -> int:
        return len(self._data)

    @property
    def logical_sector_size(self) -> int:
        return self._sector_size

    @property
    def is_closed(self) -> bool:
        return self._is_closed

    def read_at(self, offset: int, length: int) -> bytes:
        if self._is_closed:
            raise DeviceClosedError("Cannot read from closed MemoryBlockDevice")
        if offset < 0 or length < 0 or offset + length > len(self._data):
            raise DeviceOutOfBoundsError(
                f"Read out of bounds: offset={offset}, length={length}, size={len(self._data)}"
            )
        return self._data[offset : offset + length]

    def close(self) -> None:
        self._is_closed = True
