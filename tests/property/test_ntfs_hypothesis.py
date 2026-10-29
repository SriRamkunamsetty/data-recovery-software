"""Hypothesis property-based fuzz testing for NTFS binary parsers."""

import contextlib

from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.filesystems.base import CorruptedBootSectorError, CorruptedDirectoryError
from recoverx.filesystems.ntfs.attributes import parse_attribute, parse_data_runs
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.filesystems.ntfs.fixup import NtfsFixupError, apply_fixups
from recoverx.filesystems.ntfs.mft_record import MftRecord


@settings(max_examples=100)
@given(st.binary(min_size=0, max_size=2048))
def test_hypothesis_apply_fixups(data: bytes) -> None:
    """Ensure apply_fixups never crashes on arbitrary binary input."""
    with contextlib.suppress(NtfsFixupError):
        apply_fixups(data, sector_size=512)


@settings(max_examples=100)
@given(st.binary(min_size=0, max_size=1024))
def test_hypothesis_parse_data_runs(data: bytes) -> None:
    """Ensure data run decoder never crashes or hangs on arbitrary byte streams."""
    with contextlib.suppress(CorruptedDirectoryError):
        runs = parse_data_runs(data, max_clusters=1 << 32)
        assert isinstance(runs, list)


@settings(max_examples=100)
@given(st.binary(min_size=0, max_size=2048))
def test_hypothesis_mft_record_parser(data: bytes) -> None:
    """Ensure MftRecord parser handles arbitrary corrupted inputs safely."""
    with contextlib.suppress(NtfsFixupError, CorruptedDirectoryError):
        MftRecord.from_bytes(data, sector_size=512)


@settings(max_examples=100)
@given(st.binary(min_size=0, max_size=1024))
def test_hypothesis_ntfs_boot_sector(data: bytes) -> None:
    """Ensure NtfsBootSector parser rejects or parses arbitrary bytes safely."""
    try:
        boot = NtfsBootSector.from_bytes(data)
        assert boot.oem_id == b"NTFS    "
    except CorruptedBootSectorError:
        pass


@settings(max_examples=100)
@given(st.binary(min_size=0, max_size=1024), st.integers(min_value=0, max_value=512))
def test_hypothesis_parse_attribute(data: bytes, offset: int) -> None:
    """Ensure attribute parser handles arbitrary offsets and truncated data safely."""
    _attr, attr_len = parse_attribute(data, offset=offset)
    assert attr_len >= 0
