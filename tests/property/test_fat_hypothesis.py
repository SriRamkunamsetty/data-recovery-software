"""Hypothesis property-based tests for FAT boot sectors and directory parsers."""

import hypothesis.strategies as st
from hypothesis import given, settings

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.filesystems.fat.bpb import FatBpb
from recoverx.filesystems.fat.entry import (
    FatDirEntry,
    FatLfnPart,
    fat_lfn_checksum,
    parse_fat_datetime,
    parse_lfn_entry,
)


@settings(max_examples=200, deadline=None)
@given(st.binary(min_size=0, max_size=1024))
def test_fuzz_bpb_from_bytes(data: bytes) -> None:
    """Fuzzing arbitrary byte streams into FatBpb.from_bytes must never crash or panic."""
    try:
        bpb = FatBpb.from_bytes(data)
        assert bpb.bytes_per_sector in (512, 1024, 2048, 4096)
        assert bpb.sectors_per_cluster in (1, 2, 4, 8, 16, 32, 64, 128)
        assert bpb.total_sectors > 0
    except CorruptedBootSectorError:
        # Expected on malformed / random input
        pass


@settings(max_examples=200, deadline=None)
@given(st.binary(min_size=0, max_size=128))
def test_fuzz_directory_entry_parsing(data: bytes) -> None:
    """Fuzzing arbitrary 32-byte directory entries must never crash."""
    for offset in range(0, max(0, len(data) - 32), 32):
        entry = FatDirEntry.parse_raw(data, offset=offset)
        if entry is not None:
            assert isinstance(entry.display_name, str)
            assert isinstance(entry.first_cluster, int)
            assert isinstance(entry.file_size, int)


@settings(max_examples=200, deadline=None)
@given(st.binary(min_size=0, max_size=64))
def test_fuzz_lfn_entry_parsing(data: bytes) -> None:
    """Fuzzing LFN parsing must never crash."""
    lfn = parse_lfn_entry(data, offset=0)
    if lfn is not None:
        assert isinstance(lfn, FatLfnPart)
        assert isinstance(lfn.name_chars, str)


@settings(max_examples=200, deadline=None)
@given(st.binary(min_size=11, max_size=11))
def test_fuzz_lfn_checksum_invariants(short_11: bytes) -> None:
    """LFN checksum on any 11 bytes is deterministic and in [0, 255]."""
    chk = fat_lfn_checksum(short_11)
    assert 0 <= chk <= 255
    assert fat_lfn_checksum(short_11) == chk


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=0, max_value=0xFFFF), st.integers(min_value=0, max_value=0xFFFF))
def test_fuzz_fat_datetime(date_val: int, time_val: int) -> None:
    """DOS datetime parser returns either valid ISO string or None, never crashes."""
    res = parse_fat_datetime(date_val, time_val)
    if res is not None:
        assert "T" in res
        assert res.endswith("Z")
