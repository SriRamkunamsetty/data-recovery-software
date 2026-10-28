"""Unit tests for exFAT directory entry set parsing, NoFatChain flag, and checksum verification."""

import struct

from recoverx.filesystems.exfat.entry import (
    ExFatFileEntrySet,
    exfat_entry_set_checksum,
    parse_exfat_timestamp,
)


def test_exfat_entry_set_checksum_calculation() -> None:
    """Verify 16-bit rotate right and add algorithm for entry sets."""
    # Build 3 dummy 32-byte entries (96 bytes total)
    raw = bytearray(96)
    raw[0] = 0x85  # File
    raw[1] = 2  # SecondaryCount
    struct.pack_into("<H", raw, 2, 0)  # Checksum field (skipped in calc)
    raw[32] = 0xC0  # Stream
    raw[64] = 0xC1  # Name

    chk = exfat_entry_set_checksum(bytes(raw))
    assert isinstance(chk, int)
    assert 0 <= chk <= 0xFFFF

    # Verify bytes 2 and 3 do not affect checksum
    raw[2] = 0xAA
    raw[3] = 0xBB
    assert exfat_entry_set_checksum(bytes(raw)) == chk


def test_exfat_entry_set_parsing_active_file() -> None:
    """Verify parsing an active file entry set with NoFatChain=True."""
    # 1. Primary entry (0x85)
    e0 = bytearray(32)
    e0[0] = 0x85
    e0[1] = 2
    struct.pack_into("<H", e0, 4, 0x0020)  # Archive

    # 2. Stream entry (0xC0)
    e1 = bytearray(32)
    e1[0] = 0xC0
    e1[1] = 0x03  # AllocationPossible (0x01) | NoFatChain (0x02)
    e1[3] = 8  # NameLength
    struct.pack_into("<I", e1, 20, 100)  # FirstCluster
    struct.pack_into("<Q", e1, 24, 8192)  # DataLength

    # 3. Name entry (0xC1)
    e2 = bytearray(32)
    e2[0] = 0xC1
    name_bytes = "Test.txt".encode("utf-16-le")
    e2[2 : 2 + len(name_bytes)] = name_bytes

    # Compute checksum
    full_buf = bytearray(e0 + e1 + e2)
    chk = exfat_entry_set_checksum(bytes(full_buf))
    struct.pack_into("<H", full_buf, 2, chk)

    entries = [bytes(full_buf[0:32]), bytes(full_buf[32:64]), bytes(full_buf[64:96])]
    entry_set = ExFatFileEntrySet.parse_from_entries(entries)

    assert entry_set is not None
    assert not entry_set.is_deleted
    assert entry_set.filename == "Test.txt"
    assert entry_set.file_size == 8192
    assert entry_set.first_cluster == 100
    assert entry_set.no_fat_chain is True
    assert entry_set.is_checksum_valid is True


def test_exfat_entry_set_parsing_deleted_file() -> None:
    """Verify parsing a deleted file entry set (0x05, 0x40, 0x41) with intact checksum."""
    e0 = bytearray(32)
    e0[0] = 0x05  # Deleted File
    e0[1] = 2

    e1 = bytearray(32)
    e1[0] = 0x40  # Deleted Stream
    e1[1] = 0x03  # NoFatChain
    e1[3] = 7
    struct.pack_into("<I", e1, 20, 50)
    struct.pack_into("<Q", e1, 24, 1024)

    e2 = bytearray(32)
    e2[0] = 0x41  # Deleted Name
    name_bytes = "doc.pdf".encode("utf-16-le")
    e2[2 : 2 + len(name_bytes)] = name_bytes

    # To calculate expected checksum, set bit 7 (active) on each entry
    active_buf = bytearray(e0 + e1 + e2)
    active_buf[0] |= 0x80
    active_buf[32] |= 0x80
    active_buf[64] |= 0x80
    chk = exfat_entry_set_checksum(bytes(active_buf))
    struct.pack_into("<H", e0, 2, chk)

    entries = [bytes(e0), bytes(e1), bytes(e2)]
    entry_set = ExFatFileEntrySet.parse_from_entries(entries)

    assert entry_set is not None
    assert entry_set.is_deleted is True
    assert entry_set.filename == "doc.pdf"
    assert entry_set.first_cluster == 50
    assert entry_set.no_fat_chain is True
    assert entry_set.is_checksum_valid is True


def test_exfat_timestamp_parsing() -> None:
    """Verify parsing 32-bit packed exFAT timestamps."""
    # Year: 46 (2026), Month: 10, Day: 28, Hour: 12, Min: 30, Sec: 15 (doubled: 30)
    ts_val = (46 << 25) | (10 << 21) | (28 << 16) | (12 << 11) | (30 << 5) | 15
    iso = parse_exfat_timestamp(ts_val)
    assert iso == "2026-10-28T12:30:30Z"
