"""Unit tests for NTFS attribute headers, data-run decoding, and $FILE_NAME parsing."""

import struct

import pytest

from recoverx.filesystems.base import CorruptedDirectoryError
from recoverx.filesystems.ntfs.attributes import (
    DataRun,
    NtfsFileNameAttribute,
    NtfsNonResidentAttribute,
    NtfsResidentAttribute,
    parse_attribute,
    parse_data_runs,
)


def test_parse_data_runs_single_run() -> None:
    """Test decoding a single data run with 1-byte count and 2-byte LCN."""
    # Count: 4 clusters -> 0x04 (1 byte)
    # LCN: 500 (0x01F4) -> 2 bytes
    # Header byte: (2 << 4) | 1 = 0x21
    run_bytes = bytes([0x21, 0x04, 0xF4, 0x01, 0x00])
    runs = parse_data_runs(run_bytes)

    assert len(runs) == 1
    assert runs[0].cluster_count == 4
    assert runs[0].lcn == 500
    assert runs[0].is_sparse is False


def test_parse_data_runs_multiple_with_negative_delta() -> None:
    """Test decoding multiple runs with relative positive and negative cluster deltas."""
    # Run 1: length 8 clusters, LCN 1000 (0x03E8) -> hdr 0x21
    # Run 2: length 16 clusters, delta -200 (-0x00C8 = 0xFF38) -> hdr 0x21, LCN becomes 800
    # Run 3: length 4 clusters, delta +300 (0x012C) -> hdr 0x21, LCN becomes 1100
    run1 = bytes([0x21, 0x08]) + (1000).to_bytes(2, "little", signed=True)
    run2 = bytes([0x21, 0x10]) + (-200).to_bytes(2, "little", signed=True)
    run3 = bytes([0x21, 0x04]) + (300).to_bytes(2, "little", signed=True)
    stream = run1 + run2 + run3 + b"\x00"

    runs = parse_data_runs(stream)
    assert len(runs) == 3
    assert runs[0] == DataRun(cluster_count=8, lcn=1000, is_sparse=False)
    assert runs[1] == DataRun(cluster_count=16, lcn=800, is_sparse=False)
    assert runs[2] == DataRun(cluster_count=4, lcn=1100, is_sparse=False)


def test_parse_data_runs_sparse() -> None:
    """Test decoding a sparse run where offset length is zero."""
    # Count: 10 clusters (0x0A), offset length: 0
    # Header byte: (0 << 4) | 1 = 0x01
    run_bytes = bytes([0x01, 0x0A, 0x00])
    runs = parse_data_runs(run_bytes)

    assert len(runs) == 1
    assert runs[0].cluster_count == 10
    assert runs[0].lcn == 0
    assert runs[0].is_sparse is True


def test_parse_data_runs_malformed_buffer() -> None:
    """Test that truncated run bytes raise CorruptedDirectoryError."""
    # Header claims 4 bytes of count and 4 bytes of offset, but only 2 bytes follow
    truncated = bytes([0x44, 0x01, 0x02])
    with pytest.raises(CorruptedDirectoryError, match="Data run extends beyond buffer"):
        parse_data_runs(truncated)


def test_parse_resident_attribute() -> None:
    """Test parsing a resident $DATA (0x80) attribute."""
    payload = b"Hello NTFS resident file content!"
    hdr_len = 24
    total_len = (hdr_len + len(payload) + 7) & ~7
    buf = bytearray(total_len)

    struct.pack_into("<I", buf, 0, 0x80)  # Type 0x80
    struct.pack_into("<I", buf, 4, total_len)
    buf[8] = 0  # Resident
    buf[9] = 0  # Unnamed
    struct.pack_into("<I", buf, 16, len(payload))
    struct.pack_into("<H", buf, 20, hdr_len)
    buf[hdr_len : hdr_len + len(payload)] = payload

    attr, attr_len = parse_attribute(bytes(buf), offset=0)
    assert attr is not None
    assert attr_len == total_len
    assert isinstance(attr, NtfsResidentAttribute)
    assert attr.attr_type == 0x80
    assert attr.is_non_resident is False
    assert attr.data == payload
    assert attr.value_length == len(payload)


def test_parse_non_resident_attribute() -> None:
    """Test parsing a non-resident $DATA (0x80) attribute."""
    run_data = bytes([0x21, 0x04, 0xF4, 0x01, 0x00])  # 4 clusters at LCN 500
    hdr_len = 64
    total_len = (hdr_len + len(run_data) + 7) & ~7
    buf = bytearray(total_len)

    struct.pack_into("<I", buf, 0, 0x80)
    struct.pack_into("<I", buf, 4, total_len)
    buf[8] = 1  # Non-resident
    struct.pack_into("<Q", buf, 16, 0)  # Start VCN
    struct.pack_into("<Q", buf, 24, 3)  # End VCN
    struct.pack_into("<H", buf, 32, hdr_len)  # Run list offset
    struct.pack_into("<Q", buf, 40, 16384)  # Allocated size
    struct.pack_into("<Q", buf, 48, 12000)  # Real size
    struct.pack_into("<Q", buf, 56, 12000)  # Initialized size
    buf[hdr_len : hdr_len + len(run_data)] = run_data

    attr, attr_len = parse_attribute(bytes(buf), offset=0)
    assert attr is not None
    assert attr_len == total_len
    assert isinstance(attr, NtfsNonResidentAttribute)
    assert attr.is_non_resident is True
    assert attr.real_size == 12000
    assert len(attr.data_runs) == 1
    assert attr.data_runs[0].lcn == 500


def test_parse_file_name_attribute() -> None:
    """Test parsing a $FILE_NAME (0x30) attribute payload."""
    name_str = "Document.pdf"
    raw_name = name_str.encode("utf-16le")
    buf = bytearray(66 + len(raw_name))

    parent_mft_ref = 5  # Root directory
    struct.pack_into("<Q", buf, 0, parent_mft_ref)
    struct.pack_into("<Q", buf, 40, 8192)  # Allocated size
    struct.pack_into("<Q", buf, 48, 5432)  # Real size
    struct.pack_into("<I", buf, 56, 0x20)  # Archive flag
    buf[64] = len(name_str)
    buf[65] = 1  # Win32 namespace
    buf[66 : 66 + len(raw_name)] = raw_name

    fn = NtfsFileNameAttribute.from_bytes(bytes(buf))
    assert fn is not None
    assert fn.name == "Document.pdf"
    assert fn.parent_record_index == 5
    assert fn.real_size == 5432
    assert fn.namespace == 1
