"""FAT directory entry parsing, LFN reassembly, and checksum verification."""

import struct
from dataclasses import dataclass
from typing import Self


def fat_lfn_checksum(short_name_11_bytes: bytes) -> int:
    """Compute the 8-bit FAT checksum over an 11-byte short directory name.

    Algorithm from official Microsoft FAT specification: rotate right by 1 bit, then add byte.
    """
    if len(short_name_11_bytes) != 11:
        raise ValueError(f"Short name must be exactly 11 bytes, got {len(short_name_11_bytes)}")
    chksum = 0
    for b in short_name_11_bytes:
        chksum = (((chksum >> 1) | ((chksum & 1) << 7)) + b) & 0xFF
    return chksum


def verify_lfn_checksum_for_deleted_entry(raw_11_bytes: bytes, expected_chksum: int) -> int | None:
    """Find a candidate first byte for a deleted entry (0xE5) matching the LFN checksum.

    Returns:
        The original first byte (0-255) if a unique or valid match exists, else None.
    """
    if len(raw_11_bytes) != 11:
        return None
    for b in range(256):
        candidate = bytes([b]) + raw_11_bytes[1:11]
        if fat_lfn_checksum(candidate) == expected_chksum:
            return b
    return None


def parse_fat_datetime(fat_date: int, fat_time: int) -> str | None:
    """Convert MS-DOS 16-bit date and time to ISO 8601 string safely."""
    try:
        year = ((fat_date >> 9) & 0x7F) + 1980
        month = (fat_date >> 5) & 0x0F
        day = fat_date & 0x1F
        hour = (fat_time >> 11) & 0x1F
        minute = (fat_time >> 5) & 0x3F
        second = (fat_time & 0x1F) * 2

        if not (
            1 <= month <= 12
            and 1 <= day <= 31
            and 0 <= hour <= 23
            and 0 <= minute <= 59
            and 0 <= second <= 60
        ):
            return None
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
    except Exception:
        return None


@dataclass(slots=True)
class FatLfnPart:
    """A single 32-byte Long File Name (LFN) sub-entry."""

    sequence_number: int
    is_last: bool
    checksum: int
    name_chars: str


@dataclass(slots=True)
class FatDirEntry:
    """Parsed FAT directory entry (32 bytes)."""

    raw_name: bytes
    attr: int
    is_deleted: bool
    is_directory: bool
    is_volume_id: bool
    first_cluster: int
    file_size: int
    short_name: str
    lfn_name: str | None = None
    created_timestamp: str | None = None
    modified_timestamp: str | None = None

    @property
    def display_name(self) -> str:
        """Best available filename (LFN if verified, otherwise sanitized short name)."""
        if self.lfn_name and self.lfn_name.strip():
            return self.lfn_name
        return self.short_name

    @classmethod
    def parse_raw(
        cls,
        data: bytes,
        offset: int = 0,
        lfn_parts: list[FatLfnPart] | None = None,
    ) -> Self | None:
        """Parse a 32-byte directory entry.

        Args:
            data: Buffer containing directory sector data.
            offset: Offset within buffer (must have at least 32 bytes available).
            lfn_parts: Preceding LFN parts collected in order.

        Returns:
            FatDirEntry, or None if entry is unused/end of directory (0x00).
        """
        if offset + 32 > len(data):
            return None

        entry_bytes = data[offset : offset + 32]
        first_byte = entry_bytes[0]

        # 0x00 marks end of directory entries
        if first_byte == 0x00:
            return None

        attr = entry_bytes[11]

        # LFN entries have attr == 0x0F
        if (attr & 0x0F) == 0x0F:
            return None

        raw_name = bytearray(entry_bytes[0:11])
        is_deleted = first_byte == 0xE5

        # 0x05 in first byte indicates actual 0xE5 in character set (Shift-JIS)
        if first_byte == 0x05:
            raw_name[0] = 0xE5

        is_directory = bool(attr & 0x10)
        is_volume_id = bool(attr & 0x08) and not is_directory

        # Timestamps
        (crt_time, crt_date) = struct.unpack_from("<HH", entry_bytes, 14)
        (wrt_time, wrt_date) = struct.unpack_from("<HH", entry_bytes, 22)
        created_ts = parse_fat_datetime(crt_date, crt_time)
        modified_ts = parse_fat_datetime(wrt_date, wrt_time)

        # First cluster: DIR_FstClusHI (offset 20) and DIR_FstClusLO (offset 26)
        (fst_clus_hi,) = struct.unpack_from("<H", entry_bytes, 20)
        (fst_clus_lo,) = struct.unpack_from("<H", entry_bytes, 26)
        first_cluster = (fst_clus_hi << 16) | fst_clus_lo

        # File size (offset 28, uint32)
        (file_size,) = struct.unpack_from("<I", entry_bytes, 28)
        if is_directory:
            file_size = 0

        # Build short name
        name_part = raw_name[0:8].decode("latin-1", errors="replace").rstrip()
        ext_part = raw_name[8:11].decode("latin-1", errors="replace").rstrip()

        if is_deleted:
            # Replace lost first char with '_'
            short_name_str = f"_{name_part[1:]}" if len(name_part) > 1 else "_"
        else:
            short_name_str = name_part

        if ext_part:
            short_name_str = f"{short_name_str}.{ext_part}"

        # LFN Reassembly and Checksum Verification
        reconstructed_lfn: str | None = None
        if lfn_parts:
            # LFN parts are encountered in reverse order: N .. 1
            # Check if sequence is coherent (1 .. N)
            expected_chk = lfn_parts[0].checksum
            # Check that all parts share the same checksum
            if all(p.checksum == expected_chk for p in lfn_parts):
                chk_valid = False
                if not is_deleted:
                    chk_valid = fat_lfn_checksum(bytes(raw_name)) == expected_chk
                else:
                    # For deleted entry, check if any first byte produces this checksum
                    matched_b = verify_lfn_checksum_for_deleted_entry(bytes(raw_name), expected_chk)
                    chk_valid = matched_b is not None

                if chk_valid:
                    # If all parts have explicit sequence numbers (> 0), sort by sequence.
                    # Otherwise, since LFN parts appear on disk in reverse order (N down to 1),
                    # reversing the collected list restores the original 1..N order.
                    if all(p.sequence_number > 0 for p in lfn_parts):
                        sorted_parts = sorted(lfn_parts, key=lambda p: p.sequence_number)
                    else:
                        sorted_parts = list(reversed(lfn_parts))
                    reconstructed_lfn = "".join(p.name_chars for p in sorted_parts)

        return cls(
            raw_name=bytes(raw_name),
            attr=attr,
            is_deleted=is_deleted,
            is_directory=is_directory,
            is_volume_id=is_volume_id,
            first_cluster=first_cluster,
            file_size=file_size,
            short_name=short_name_str,
            lfn_name=reconstructed_lfn,
            created_timestamp=created_ts,
            modified_timestamp=modified_ts,
        )


def parse_lfn_entry(data: bytes, offset: int = 0) -> FatLfnPart | None:
    """Parse a single 32-byte LFN sub-entry if attr is 0x0F."""
    if offset + 32 > len(data):
        return None

    entry_bytes = data[offset : offset + 32]
    attr = entry_bytes[11]
    if (attr & 0x0F) != 0x0F:
        return None

    ord_byte = entry_bytes[0]
    # If deleted, ord_byte is 0xE5
    if ord_byte == 0xE5:
        # In a deleted LFN, sequence number can be inferred or set to 0
        seq = 0
        is_last = False
    else:
        seq = ord_byte & 0x1F
        is_last = bool(ord_byte & 0x40)

    chksum = entry_bytes[13]

    # Extract 13 UTF-16LE characters:
    # 5 chars from bytes 1-10
    # 6 chars from bytes 14-25
    # 2 chars from bytes 28-31
    name_bytes = entry_bytes[1:11] + entry_bytes[14:26] + entry_bytes[28:32]
    raw_chars = name_bytes.decode("utf-16-le", errors="replace")

    # Stop at null character '\x00' or padding '\uffff'
    chars: list[str] = []
    for c in raw_chars:
        if c in ("\x00", "\uffff"):
            break
        chars.append(c)

    return FatLfnPart(
        sequence_number=seq,
        is_last=is_last,
        checksum=chksum,
        name_chars="".join(chars),
    )
