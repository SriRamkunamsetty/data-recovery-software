"""Base interfaces and exceptions for block storage devices."""

import math
from abc import ABC, abstractmethod
from typing import Any, Self

from recoverx.domain.device import DeviceIdentity, StorageDevice


class StorageError(Exception):
    """Base exception for all storage and block device errors."""


class DeviceClosedError(StorageError):
    """Raised when an operation is attempted on a closed block device."""


class DeviceOutOfBoundsError(StorageError, ValueError):
    """Raised when an offset or length is out of device bounds, negative, or overflowing."""


class DeviceReadError(StorageError):
    """Raised when an I/O error occurs while reading from a block device."""


class DeviceDisconnectedError(StorageError):
    """Raised when a block device is disconnected, removed, or unreachable."""


class DeviceRemovedError(DeviceDisconnectedError):
    """Raised when a removable block storage device is removed during operation."""


class DeviceAccessDeniedError(StorageError):
    """Raised when access to a physical disk or volume is denied (needs elevation)."""


class DeviceSharingViolationError(StorageError):
    """Raised when another process or volume lock prevents exclusive/shared read access."""


class DeviceAlignmentError(StorageError):
    """Raised when buffer or sector alignment requirements are violated."""


class DeviceHangError(StorageError):
    """Raised when an I/O read operation hangs or times out and is cancelled."""


class ReadOnlyBlockDevice(ABC):
    """Abstract interface for strictly read-only block devices and disk images.

    Rule 1 of CLAUDE.md:
    The source is read-only by construction. Exposes only metadata,
    size_bytes, logical_sector_size, read_at(offset, length), and close().
    Never add write, erase, format, repair, partition-edit or filesystem-modify operations.
    """

    @property
    @abstractmethod
    def identity(self) -> DeviceIdentity:
        """Forensic identity of the block device."""

    @property
    @abstractmethod
    def device_info(self) -> StorageDevice:
        """Storage device metadata including triage status and bus type."""

    @property
    @abstractmethod
    def size_bytes(self) -> int:
        """Total size of the device in bytes."""

    @property
    @abstractmethod
    def logical_sector_size(self) -> int:
        """Logical sector size in bytes (e.g., 512, 4096)."""

    @property
    @abstractmethod
    def is_closed(self) -> bool:
        """True if the device handle has been closed."""

    @abstractmethod
    def read_at(self, offset: int, length: int) -> bytes:
        """Read exactly `length` bytes starting at `offset`.

        Must perform bounds checking before any I/O.
        Raises:
            DeviceClosedError: If the device is closed.
            DeviceOutOfBoundsError: If offset or length is negative, overflowing,
                or extends past size_bytes.
            DeviceReadError: If a read failure or bad sector is encountered.
            DeviceDisconnectedError: If the device is detached or removed.
        """

    @abstractmethod
    def close(self) -> None:
        """Close the underlying storage handle."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def validate_bounds(self, offset: int, length: int) -> None:
        """Validate offset and length with overflow-safe arithmetic.

        Raises DeviceOutOfBoundsError if parameters are invalid.
        """
        if self.is_closed:
            raise DeviceClosedError("Cannot read from a closed block device.")

        if offset < 0:
            raise DeviceOutOfBoundsError(f"Offset cannot be negative: {offset}")

        if length < 0:
            raise DeviceOutOfBoundsError(f"Length cannot be negative: {length}")

        if offset > self.size_bytes:
            raise DeviceOutOfBoundsError(
                f"Offset {offset} exceeds device capacity ({self.size_bytes} bytes)."
            )

        if length == 0:
            return

        # Overflow-safe check: offset + length > size_bytes
        # Re-arranged as offset > size_bytes - length
        if offset > self.size_bytes - length:
            raise DeviceOutOfBoundsError(
                f"Requested range [{offset}, {offset + length}) exceeds "
                f"device capacity ({self.size_bytes} bytes)."
            )

    @property
    def total_sectors(self) -> int:
        """Total logical sectors on device."""
        if self.logical_sector_size <= 0:
            return 0
        return math.ceil(self.size_bytes / self.logical_sector_size)
