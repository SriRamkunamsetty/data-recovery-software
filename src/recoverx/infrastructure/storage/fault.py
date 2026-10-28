"""Fault injection block device wrapper for robustness testing."""

import time
from dataclasses import dataclass, field
from typing import NamedTuple

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceDisconnectedError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)


class ByteRange(NamedTuple):
    """Contiguous byte interval [start, end)."""

    start: int
    end: int

    def overlaps(self, other_start: int, other_end: int) -> bool:
        """Check if [start, end) intersects [other_start, other_end)."""
        return max(self.start, other_start) < min(self.end, other_end)


@dataclass
class FaultConfig:
    """Configuration specification for fault injection reader."""

    # Offsets and lengths of unreadable ranges (raise DeviceReadError)
    unreadable_ranges: list[ByteRange] = field(default_factory=list)

    # Short read ranges: (start, end) -> max bytes to return
    short_read_limits: dict[ByteRange, int] = field(default_factory=dict)

    # Delay per read in seconds (simulating failing hardware latency)
    fixed_delay_seconds: float = 0.0

    # Specific ranges that incur latency
    delayed_ranges: dict[ByteRange, float] = field(default_factory=dict)

    # Disconnect simulation
    disconnect_after_bytes: int | None = None
    disconnect_at_offset: int | None = None


class FaultInjectionReader(ReadOnlyBlockDevice):
    """Wrapper around ReadOnlyBlockDevice simulating faulty hardware behaviors."""

    def __init__(
        self,
        target_device: ReadOnlyBlockDevice,
        config: FaultConfig | None = None,
    ) -> None:
        self._target = target_device
        self._config = config or FaultConfig()
        self._total_bytes_read = 0
        self._read_call_count = 0
        self._is_disconnected = False
        self._is_closed = False

    @property
    def identity(self) -> DeviceIdentity:
        return self._target.identity

    @property
    def device_info(self) -> StorageDevice:
        return self._target.device_info

    @property
    def size_bytes(self) -> int:
        return self._target.size_bytes

    @property
    def logical_sector_size(self) -> int:
        return self._target.logical_sector_size

    @property
    def is_closed(self) -> bool:
        return self._is_closed or self._target.is_closed

    @property
    def is_disconnected(self) -> bool:
        return self._is_disconnected

    @property
    def total_bytes_read(self) -> int:
        return self._total_bytes_read

    @property
    def read_call_count(self) -> int:
        return self._read_call_count

    def disconnect(self) -> None:
        """Manually trigger device disconnection."""
        self._is_disconnected = True

    def read_at(self, offset: int, length: int) -> bytes:
        """Perform a fault-injected read."""
        # 1. Bounds check must occur first before any fault simulation or I/O
        self.validate_bounds(offset, length)

        if self.is_closed:
            raise DeviceClosedError("Block device is closed.")

        if self._is_disconnected:
            raise DeviceDisconnectedError("Device was disconnected.")

        if length == 0:
            return b""

        self._read_call_count += 1

        # 2. Check offset-triggered disconnect
        if (
            self._config.disconnect_at_offset is not None
            and offset <= self._config.disconnect_at_offset < offset + length
        ):
            self._is_disconnected = True
            raise DeviceDisconnectedError(f"Device disconnected upon accessing offset {offset}")

        # 3. Check cumulative bytes disconnect
        if (
            self._config.disconnect_after_bytes is not None
            and self._total_bytes_read >= self._config.disconnect_after_bytes
        ):
            self._is_disconnected = True
            raise DeviceDisconnectedError("Device disconnected after reaching byte threshold.")

        # 4. Check for unreadable range intersection
        read_end = offset + length
        for bad_range in self._config.unreadable_ranges:
            if bad_range.overlaps(offset, read_end):
                raise DeviceReadError(
                    f"Simulated bad sector in range [{bad_range.start}, {bad_range.end}) "
                    f"overlapping requested [{offset}, {read_end})"
                )

        # 5. Check for delays
        if self._config.fixed_delay_seconds > 0:
            time.sleep(self._config.fixed_delay_seconds)
        for delayed_range, delay_sec in self._config.delayed_ranges.items():
            if delayed_range.overlaps(offset, read_end):
                time.sleep(delay_sec)

        # 6. Check for short read simulation
        effective_length = length
        for short_range, max_bytes in self._config.short_read_limits.items():
            if short_range.overlaps(offset, read_end):
                effective_length = min(effective_length, max_bytes)

        # 7. Delegate read to target
        data = self._target.read_at(offset, effective_length)
        self._total_bytes_read += len(data)

        # If byte limit threshold crossed during this read, trigger disconnect on subsequent reads
        if (
            self._config.disconnect_after_bytes is not None
            and self._total_bytes_read >= self._config.disconnect_after_bytes
        ):
            self._is_disconnected = True

        return data

    def close(self) -> None:
        """Close target device."""
        if not self._is_closed:
            self._target.close()
            self._is_closed = True
