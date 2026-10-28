"""exFAT directory entry set parsing, checksum verification, and metadata extraction."""

import struct
from dataclasses import dataclass


def exfat_entry_set_checksum(entry_set_bytes: bytes) -> int:
    """Calculate the 16-bit checksum over an exFAT directory entry set.

    Algorithm from official Microsoft exFAT specification: 1-bit rotate right and add,
    skipping the SetChecksum field at bytes 2 and 3 of the primary entry.
    """
    checksum = 0
    for i in range(len(entry_set_bytes)):
        if i in (2, 3):
            continue
        checksum = (((checksum << 15) & 0xFFFF) | (checksum >> 1)) + entry_set_bytes[i]
        checksum &= 0xFFFF
    return checksum


def parse_exfat_timestamp(ts_32: int) -> str | None:
    """Parse a 32-bit exFAT packed date/time integer into an ISO 8601 string."""
    try:
        second = (ts_32 & 0x1F) * 2
        minute = (ts_32 >> 5) & 0x3F
        hour = (ts_32 >> 11) & 0x1F
        day = (ts_32 >> 16) & 0x1F
        month = (ts_32 >> 21) & 0x0F
        year = ((ts_32 >> 25) & 0x7F) + 1980

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
class ExFatFileEntrySet:
    """A complete exFAT file or directory entry set (File, Stream Extension, and Name entries)."""

    filename: str
    file_size: int
    first_cluster: int
    no_fat_chain: bool
    is_deleted: bool
    is_directory: bool
    is_checksum_valid: bool
    created_timestamp: str | None = None
    modified_timestamp: str | None = None

    @classmethod
    def parse_from_entries(cls, raw_entries: list[bytes]) -> "ExFatFileEntrySet | None":
        """Parse an entry set (minimum 3 entries: File, Stream Extension, and 1+ Name entries).

        Args:
            raw_entries: List of 32-byte directory entries comprising the set.

        Returns:
            ExFatFileEntrySet or None if malformed.
        """
        if len(raw_entries) < 3:
            return None

        primary = raw_entries[0]
        primary_type = primary[0]

        # Check primary entry type: 0x85 (active File) or 0x05 (deleted File)
        if primary_type not in (0x85, 0x05):
            return None

        is_deleted = primary_type == 0x05
        secondary_count = primary[1]
        if len(raw_entries) < 1 + secondary_count:
            return None

        (set_checksum,) = struct.unpack_from("<H", primary, 2)
        (file_attr,) = struct.unpack_from("<H", primary, 4)
        is_directory = bool(file_attr & 0x0010)

        # Timestamps
        (create_raw,) = struct.unpack_from("<I", primary, 8)
        (mod_raw,) = struct.unpack_from("<I", primary, 12)
        create_ts = parse_exfat_timestamp(create_raw)
        mod_ts = parse_exfat_timestamp(mod_raw)

        # Stream Extension Entry (Entry 1)
        stream = raw_entries[1]
        stream_type = stream[0]
        # Stream entry type: 0xC0 (active) or 0x40 (deleted)
        if stream_type not in (0xC0, 0x40):
            return None

        gen_flags = stream[1]
        no_fat_chain = bool(gen_flags & 0x02)
        name_length = stream[3]

        (first_cluster,) = struct.unpack_from("<I", stream, 20)
        (file_size,) = struct.unpack_from("<Q", stream, 24)
        if is_directory:
            file_size = 0

        # File Name Entries (Entries 2..N)
        name_chars: list[str] = []
        for i in range(2, 1 + secondary_count):
            name_entry = raw_entries[i]
            # Name entry type: 0xC1 (active) or 0x41 (deleted)
            if name_entry[0] not in (0xC1, 0x41):
                return None
            chars_raw = name_entry[2:32].decode("utf-16-le", errors="replace")
            name_chars.append(chars_raw)

        full_name = "".join(name_chars)[:name_length].rstrip("\x00")

        # Verify entry-set checksum
        concatenated = b"".join(raw_entries[: 1 + secondary_count])
        # If deleted, restore active bit (0x80) on type bytes to check if metadata was intact
        if is_deleted:
            test_buf = bytearray(concatenated)
            for idx in range(1 + secondary_count):
                test_buf[idx * 32] |= 0x80
            computed_chk = exfat_entry_set_checksum(bytes(test_buf))
        else:
            computed_chk = exfat_entry_set_checksum(concatenated)

        is_valid_chk = computed_chk == set_checksum

        return cls(
            filename=full_name,
            file_size=file_size,
            first_cluster=first_cluster,
            no_fat_chain=no_fat_chain,
            is_deleted=is_deleted,
            is_directory=is_directory,
            is_checksum_valid=is_valid_chk,
            created_timestamp=create_ts,
            modified_timestamp=mod_ts,
        )
