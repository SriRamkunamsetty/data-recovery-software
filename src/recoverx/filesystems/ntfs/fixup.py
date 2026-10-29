"""NTFS update sequence (fixup array) verification and application."""

import struct

from recoverx.filesystems.base import FileSystemError


class NtfsFixupError(FileSystemError):
    """Raised when an MFT record has an invalid signature or fixup USN mismatch."""


def apply_fixups(record_bytes: bytes, sector_size: int = 512) -> bytes:
    """Verify and apply the NTFS update sequence (fixup array) to an MFT record.

    In NTFS, the last two bytes of each sector in an MFT record are replaced with an
    Update Sequence Number (USN) when written to disk to detect torn writes. The
    original bytes are stored in the update sequence array in the record header.
    Before parsing attributes, the USN at the end of each sector must be verified
    and replaced with its original bytes.

    Args:
        record_bytes: Raw bytes of the MFT record (typically 1024 bytes).
        sector_size: Physical sector size in bytes (typically 512).

    Returns:
        Fixed-up record bytes ready for attribute parsing.

    Raises:
        NtfsFixupError: If magic is not 'FILE', record is 'BAAD', or fixup USN mismatches.
    """
    if len(record_bytes) < 48:
        raise NtfsFixupError(f"MFT record too short for header ({len(record_bytes)} bytes)")

    magic = record_bytes[:4]
    if magic == b"BAAD":
        raise NtfsFixupError("MFT record marked BAAD (damaged record on disk)")
    if magic != b"FILE":
        raise NtfsFixupError(f"Invalid MFT record signature: {magic!r}")

    update_seq_offset, update_seq_count = struct.unpack_from("<HH", record_bytes, 4)

    # Validate update sequence array bounds
    seq_bytes_needed = update_seq_count * 2
    if update_seq_offset + seq_bytes_needed > len(record_bytes):
        raise NtfsFixupError(
            f"Update sequence array extends beyond record size "
            f"(offset {update_seq_offset} + {seq_bytes_needed} > {len(record_bytes)})"
        )

    if update_seq_count == 0:
        return record_bytes

    expected_usn = record_bytes[update_seq_offset : update_seq_offset + 2]
    buf = bytearray(record_bytes)

    # For each sector in the record (1-based index into update sequence array)
    for i in range(1, update_seq_count):
        sec_end = (i * sector_size) - 2
        if sec_end + 2 > len(record_bytes):
            break

        actual_usn = record_bytes[sec_end : sec_end + 2]
        if actual_usn != expected_usn:
            raise NtfsFixupError(
                f"Fixup USN mismatch in sector {i}: expected {expected_usn.hex()}, "
                f"got {actual_usn.hex()}"
            )

        replacement = record_bytes[update_seq_offset + (i * 2) : update_seq_offset + (i * 2) + 2]
        buf[sec_end : sec_end + 2] = replacement

    return bytes(buf)
