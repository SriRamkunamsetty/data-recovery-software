"""Unit tests for NTFS update sequence (fixup) verification and application."""

import struct

import pytest

from recoverx.filesystems.ntfs.fixup import NtfsFixupError, apply_fixups


def build_raw_mft_record(
    magic: bytes = b"FILE",
    usn: int = 0xABCD,
    sec1_orig: int = 0x1122,
    sec2_orig: int = 0x3344,
    sec1_actual: int | None = None,
    sec2_actual: int | None = None,
    seq_offset: int = 42,
    seq_count: int = 3,
) -> bytes:
    """Build a raw 1024-byte MFT record with fixup array."""
    rec = bytearray(1024)
    rec[0:4] = magic
    struct.pack_into("<HH", rec, 4, seq_offset, seq_count)

    if seq_offset + (seq_count * 2) <= 1024:
        struct.pack_into("<H", rec, seq_offset, usn)
        if seq_count > 1:
            struct.pack_into("<H", rec, seq_offset + 2, sec1_orig)
        if seq_count > 2:
            struct.pack_into("<H", rec, seq_offset + 4, sec2_orig)

    # Sector 1 ends at 510..512; Sector 2 ends at 1022..1024
    s1 = usn if sec1_actual is None else sec1_actual
    s2 = usn if sec2_actual is None else sec2_actual
    struct.pack_into("<H", rec, 510, s1)
    struct.pack_into("<H", rec, 1022, s2)

    return bytes(rec)


def test_apply_fixups_valid() -> None:
    """Test valid fixup replaces sector-end USNs with original bytes."""
    raw = build_raw_mft_record(
        usn=0xA1B2,
        sec1_orig=0x1234,
        sec2_orig=0x5678,
    )
    fixed = apply_fixups(raw, sector_size=512)

    assert fixed[:4] == b"FILE"
    # Check that sector 1 end was restored to sec1_orig
    assert struct.unpack_from("<H", fixed, 510)[0] == 0x1234
    # Check that sector 2 end was restored to sec2_orig
    assert struct.unpack_from("<H", fixed, 1022)[0] == 0x5678


def test_apply_fixups_mismatch_raises() -> None:
    """Test torn write where sector-end USN does not match header USN."""
    raw = build_raw_mft_record(
        usn=0xA1B2,
        sec1_actual=0x0000,  # Mismatch!
    )
    with pytest.raises(NtfsFixupError, match="Fixup USN mismatch in sector 1"):
        apply_fixups(raw, sector_size=512)


def test_apply_fixups_baad_record() -> None:
    """Test rejection when record is marked BAAD."""
    raw = build_raw_mft_record(magic=b"BAAD")
    with pytest.raises(NtfsFixupError, match="marked BAAD"):
        apply_fixups(raw)


def test_apply_fixups_invalid_magic() -> None:
    """Test rejection of non-MFT signatures."""
    raw = build_raw_mft_record(magic=b"DATA")
    with pytest.raises(NtfsFixupError, match="Invalid MFT record signature"):
        apply_fixups(raw)


def test_apply_fixups_buffer_too_short() -> None:
    """Test rejection when input buffer is under 48 bytes."""
    with pytest.raises(NtfsFixupError, match="MFT record too short"):
        apply_fixups(b"FILE" + b"\x00" * 10)


def test_apply_fixups_out_of_bounds_sequence() -> None:
    """Test rejection when sequence array offset exceeds record bounds."""
    raw = build_raw_mft_record(seq_offset=1020, seq_count=5)
    with pytest.raises(NtfsFixupError, match="Update sequence array extends beyond"):
        apply_fixups(raw)
