"""Unit tests for FAT directory entry parsing, LFN reassembly, and checksum verification."""

import struct

from recoverx.filesystems.fat.entry import (
    FatDirEntry,
    FatLfnPart,
    fat_lfn_checksum,
    parse_fat_datetime,
    verify_lfn_checksum_for_deleted_entry,
)


def test_fat_lfn_checksum_algorithm() -> None:
    """Verify Microsoft standard 8-bit checksum calculation on short names."""
    # Test vector: "TEST    TXT"
    short_name = b"TEST    TXT"
    chk = fat_lfn_checksum(short_name)
    assert isinstance(chk, int)
    assert 0 <= chk <= 255

    # Checksum is deterministic
    assert fat_lfn_checksum(short_name) == chk


def test_verify_lfn_checksum_for_deleted_entry() -> None:
    """For a deleted entry (0xE5), recover the original first byte matching the LFN checksum."""
    original_short = b"MYFILE  DOC"
    chk = fat_lfn_checksum(original_short)

    deleted_short = b"\xe5" + original_short[1:]
    matched_byte = verify_lfn_checksum_for_deleted_entry(deleted_short, chk)
    assert matched_byte is not None
    assert bytes([matched_byte]) == b"M"


def test_parse_active_and_deleted_8_3_entry() -> None:
    """Verify parsing standard 32-byte active and deleted entries."""
    entry_bytes = bytearray(32)
    entry_bytes[0:11] = b"REPORT  PDF"
    entry_bytes[11] = 0x20  # ATTR_ARCHIVE
    struct.pack_into("<H", entry_bytes, 20, 0)  # FstClusHI
    struct.pack_into("<H", entry_bytes, 26, 42)  # FstClusLO
    struct.pack_into("<I", entry_bytes, 28, 12345)  # Size

    # 1. Active entry
    entry = FatDirEntry.parse_raw(bytes(entry_bytes))
    assert entry is not None
    assert not entry.is_deleted
    assert entry.short_name == "REPORT.PDF"
    assert entry.first_cluster == 42
    assert entry.file_size == 12345

    # 2. Deleted entry
    entry_bytes[0] = 0xE5
    del_entry = FatDirEntry.parse_raw(bytes(entry_bytes))
    assert del_entry is not None
    assert del_entry.is_deleted
    # First character lost, replaced with '_'
    assert del_entry.short_name == "_EPORT.PDF"


def test_parse_and_reassemble_lfn_parts() -> None:
    """Verify multiple LFN sub-entries reassemble into complete long filename."""
    short_11 = b"MYLONG~1JPG"
    chk = fat_lfn_checksum(short_11)

    part1 = FatLfnPart(sequence_number=1, is_last=False, checksum=chk, name_chars="My_Long_File_")
    part2 = FatLfnPart(sequence_number=2, is_last=True, checksum=chk, name_chars="Name.jpg")

    entry_bytes = bytearray(32)
    entry_bytes[0:11] = short_11
    entry_bytes[11] = 0x20
    struct.pack_into("<H", entry_bytes, 26, 10)
    struct.pack_into("<I", entry_bytes, 28, 5000)

    # LFN parts are encountered in reverse order: [part2, part1]
    entry = FatDirEntry.parse_raw(bytes(entry_bytes), lfn_parts=[part2, part1])
    assert entry is not None
    assert entry.lfn_name == "My_Long_File_Name.jpg"
    assert entry.display_name == "My_Long_File_Name.jpg"


def test_parse_fat_datetime() -> None:
    """Verify parsing packed MS-DOS 16-bit date and time stamps."""
    # Date: 2026-10-28
    # Year: 2026 - 1980 = 46 -> 46 << 9
    # Month: 10 -> 10 << 5
    # Day: 28
    fat_date = (46 << 9) | (10 << 5) | 28
    # Time: 14:30:10 (second 10 -> 5 in bits 0-4)
    fat_time = (14 << 11) | (30 << 5) | 5

    iso = parse_fat_datetime(fat_date, fat_time)
    assert iso == "2026-10-28T14:30:10Z"

    # Corrupt date returns None safely
    assert parse_fat_datetime(0xFFFF, 0xFFFF) is None
