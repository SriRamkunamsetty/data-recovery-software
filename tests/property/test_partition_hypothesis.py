"""Hypothesis property-based tests for MBR and GPT partition parsers."""

from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import DeviceTriageStatus
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.partitions.gpt import GptHeader, GptParser
from recoverx.partitions.mbr import MbrParser


class MemoryBlockDevice(ReadOnlyBlockDevice):
    """In-memory block device for property testing."""

    def __init__(self, data: bytes, sector_size: int = 512) -> None:
        self._data = data
        self._sector_size = sector_size
        self._closed = False
        self._identity = DeviceIdentity(
            vendor="Test",
            product="MemoryDevice",
            serial="MEM001",
            capacity_bytes=len(data),
            logical_sector_size=sector_size,
            physical_sector_size=sector_size,
            disk_identifier="0x0",
            sector0_hash="",
        )
        self._device_info = StorageDevice(
            identity=self._identity,
            bus_type="Image",
            physical_disk_number=None,
            drive_letters=(),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
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
        return self._closed

    def read_at(self, offset: int, length: int) -> bytes:
        self.validate_bounds(offset, length)
        return self._data[offset : offset + length]

    def close(self) -> None:
        self._closed = True


@settings(max_examples=100)
@given(sector_bytes=st.binary(min_size=512, max_size=512))
def test_mbr_fuzz_never_crashes(sector_bytes: bytes) -> None:
    """MBR parser never crashes on arbitrary 512-byte sequences."""
    dev = MemoryBlockDevice(sector_bytes)
    res = MbrParser.parse(dev)
    # Result must be MbrTable or None, never an unhandled exception
    if res is not None:
        infos = res.to_partition_infos()
        assert isinstance(infos, list)


@settings(max_examples=100)
@given(header_bytes=st.binary(min_size=0, max_size=1024))
def test_gpt_header_parse_fuzz(header_bytes: bytes) -> None:
    """GPT header parse never crashes on arbitrary byte sequences."""
    hdr = GptHeader.parse(header_bytes)
    # Result is either GptHeader instance or None
    assert hdr is None or isinstance(hdr, GptHeader)


@settings(max_examples=50)
@given(
    disk_data=st.binary(min_size=2048, max_size=8192),
    sector_size=st.sampled_from([512, 1024, 2048, 4096]),
)
def test_gpt_parser_fuzz_never_crashes(disk_data: bytes, sector_size: int) -> None:
    """GptParser.parse never crashes or reads out of bounds on arbitrary disk bytes."""
    dev = MemoryBlockDevice(disk_data, sector_size=sector_size)
    res = GptParser.parse(dev)
    if res is not None:
        infos = res.to_partition_infos(sector_size=sector_size)
        assert isinstance(infos, list)
