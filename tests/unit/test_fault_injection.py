"""Unit tests for FaultInjectionReader."""

import time
from pathlib import Path

import pytest

from recoverx.infrastructure.storage.base import (
    DeviceDisconnectedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
)
from recoverx.infrastructure.storage.fault import (
    ByteRange,
    FaultConfig,
    FaultInjectionReader,
)
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader


@pytest.fixture
def base_reader(tmp_path: Path) -> DiskImageReader:
    builder = SyntheticImageBuilder(total_size_bytes=4096, fill_byte=b"\x00")
    builder.add_file("payload.dat", b"FAULT_INJECTION_TEST", offset=512)
    manifest = builder.build(tmp_path / "fault.img")
    return DiskImageReader(manifest.image_path)


def test_unreadable_ranges_raise(base_reader: DiskImageReader) -> None:
    config = FaultConfig(
        unreadable_ranges=[ByteRange(start=1024, end=1536)],  # Sector 2 is bad
    )
    with FaultInjectionReader(base_reader, config) as reader:
        # Readable sector 1
        data = reader.read_at(512, 20)
        assert data == b"FAULT_INJECTION_TEST"

        # Reading bad sector directly
        with pytest.raises(DeviceReadError, match="Simulated bad sector"):
            reader.read_at(1024, 512)

        # Partial overlap across bad sector boundary
        with pytest.raises(DeviceReadError, match="Simulated bad sector"):
            reader.read_at(1000, 50)


def test_short_reads_simulation(base_reader: DiskImageReader) -> None:
    config = FaultConfig(
        short_read_limits={
            ByteRange(start=512, end=1024): 5,  # Return at most 5 bytes
        }
    )
    with FaultInjectionReader(base_reader, config) as reader:
        data = reader.read_at(512, 20)
        assert len(data) == 5
        assert data == b"FAULT"


def test_delay_simulation(base_reader: DiskImageReader) -> None:
    config = FaultConfig(
        delayed_ranges={
            ByteRange(start=512, end=600): 0.05,  # 50ms delay
        }
    )
    with FaultInjectionReader(base_reader, config) as reader:
        start_time = time.perf_counter()
        _ = reader.read_at(512, 20)
        duration = time.perf_counter() - start_time
        assert duration >= 0.045  # Account for timer precision


def test_disconnect_after_bytes_simulation(base_reader: DiskImageReader) -> None:
    config = FaultConfig(
        disconnect_after_bytes=30,
    )
    with FaultInjectionReader(base_reader, config) as reader:
        # Read 20 bytes - below threshold
        _ = reader.read_at(0, 20)

        # Read 15 bytes - crosses 30 bytes threshold
        _ = reader.read_at(20, 15)
        assert reader.is_disconnected

        # Subsequent read must raise DeviceDisconnectedError
        with pytest.raises(DeviceDisconnectedError, match="disconnected"):
            reader.read_at(35, 10)


def test_disconnect_at_offset_simulation(base_reader: DiskImageReader) -> None:
    config = FaultConfig(
        disconnect_at_offset=2048,
    )
    with FaultInjectionReader(base_reader, config) as reader:
        # Before trigger
        _ = reader.read_at(0, 512)

        # Touching trigger offset
        with pytest.raises(DeviceDisconnectedError, match="accessing offset"):
            reader.read_at(2048, 512)

        assert reader.is_disconnected


def test_bounds_checked_before_fault_simulation(base_reader: DiskImageReader) -> None:
    """Verify that invalid offsets raise DeviceOutOfBoundsError before checking faults."""
    config = FaultConfig(
        disconnect_at_offset=2048,
        unreadable_ranges=[ByteRange(0, 512)],
    )
    with (
        FaultInjectionReader(base_reader, config) as reader,
        pytest.raises(DeviceOutOfBoundsError),
    ):
        reader.read_at(-1, 10)
