"""GUID Partition Table (GPT) parser with primary and backup CRC validation."""

import logging
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Self

from recoverx.domain.partition import PartitionInfo
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)
from recoverx.partitions.models import GptHeaderHealth

logger = logging.getLogger(__name__)

GPT_SIGNATURE = b"EFI PART"
MIN_GPT_HEADER_SIZE = 92
DEFAULT_ENTRY_SIZE = 128
DEFAULT_NUM_ENTRIES = 128

# Standard GPT Partition Type GUIDs (Formatted strings)
GPT_TYPE_UNUSED = "00000000-0000-0000-0000-000000000000"
GPT_TYPE_WINDOWS_BASIC_DATA = "ebd0a0a2-b9e5-4433-87c0-68b6b72699c7"
GPT_TYPE_MICROSOFT_RESERVED = "e3c9e310-0b5c-4db8-817d-f92df00215ae"
GPT_TYPE_EFI_SYSTEM = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
GPT_TYPE_LINUX_DATA = "0fc63daf-8483-4772-8e79-3d69d8477de4"

KNOWN_GUID_NAMES: dict[str, str] = {
    GPT_TYPE_WINDOWS_BASIC_DATA: "Basic Data Partition",
    GPT_TYPE_MICROSOFT_RESERVED: "Microsoft Reserved Partition (MSR)",
    GPT_TYPE_EFI_SYSTEM: "EFI System Partition",
    GPT_TYPE_LINUX_DATA: "Linux Filesystem Data",
}


def bytes_to_guid(raw: bytes) -> str:
    """Convert mixed-endian UEFI binary GUID (16 bytes) to standard UUID string."""
    if len(raw) != 16:
        return GPT_TYPE_UNUSED
    # UEFI stores Data1 (uint32), Data2 (uint16), Data3 (uint16) as little-endian
    time_low = int.from_bytes(raw[0:4], "little")
    time_mid = int.from_bytes(raw[4:6], "little")
    time_hi = int.from_bytes(raw[6:8], "little")
    clock_seq_and_node = raw[8:16]
    constructed = (
        time_low.to_bytes(4, "big")
        + time_mid.to_bytes(2, "big")
        + time_hi.to_bytes(2, "big")
        + clock_seq_and_node
    )
    return str(uuid.UUID(bytes=constructed))


def guid_to_bytes(guid_str: str) -> bytes:
    """Convert standard UUID string to mixed-endian UEFI binary GUID (16 bytes)."""
    u = uuid.UUID(guid_str)
    raw = u.bytes
    time_low = int.from_bytes(raw[0:4], "big")
    time_mid = int.from_bytes(raw[4:6], "big")
    time_hi = int.from_bytes(raw[6:8], "big")
    clock_seq_and_node = raw[8:16]
    return (
        time_low.to_bytes(4, "little")
        + time_mid.to_bytes(2, "little")
        + time_hi.to_bytes(2, "little")
        + clock_seq_and_node
    )


@dataclass(frozen=True)
class GptHeader:
    """Raw parsed GPT header structure."""

    revision: int
    header_size: int
    header_crc32: int
    current_lba: int
    backup_lba: int
    first_usable_lba: int
    last_usable_lba: int
    disk_guid: str
    partition_entries_lba: int
    num_partition_entries: int
    partition_entry_size: int
    partition_array_crc32: int
    is_crc_valid: bool
    is_array_crc_valid: bool

    @classmethod
    def parse(
        cls,
        header_bytes: bytes,
        partition_array_bytes: bytes | None = None,
    ) -> Self | None:
        """Parse and validate a GPT header and its partition entry array."""
        if len(header_bytes) < MIN_GPT_HEADER_SIZE:
            return None

        if header_bytes[0:8] != GPT_SIGNATURE:
            return None

        revision = int.from_bytes(header_bytes[8:12], "little")
        header_size = int.from_bytes(header_bytes[12:16], "little")
        if header_size < MIN_GPT_HEADER_SIZE or header_size > len(header_bytes):
            return None

        stored_header_crc = int.from_bytes(header_bytes[16:20], "little")
        current_lba = int.from_bytes(header_bytes[24:32], "little")
        backup_lba = int.from_bytes(header_bytes[32:40], "little")
        first_usable_lba = int.from_bytes(header_bytes[40:48], "little")
        last_usable_lba = int.from_bytes(header_bytes[48:56], "little")
        disk_guid = bytes_to_guid(header_bytes[56:72])
        part_entries_lba = int.from_bytes(header_bytes[72:80], "little")
        num_entries = int.from_bytes(header_bytes[80:84], "little")
        entry_size = int.from_bytes(header_bytes[84:88], "little")
        stored_array_crc = int.from_bytes(header_bytes[88:92], "little")

        # Validate header CRC32: zero out CRC field (bytes 16..20)
        zeroed_header = bytearray(header_bytes[:header_size])
        zeroed_header[16:20] = b"\x00\x00\x00\x00"
        calc_header_crc = zlib.crc32(zeroed_header) & 0xFFFFFFFF
        is_crc_valid = calc_header_crc == stored_header_crc

        # Validate partition entry array CRC32
        is_array_crc_valid = False
        if partition_array_bytes is not None and entry_size > 0 and num_entries > 0:
            expected_total_bytes = num_entries * entry_size
            if len(partition_array_bytes) >= expected_total_bytes:
                calc_array_crc = (
                    zlib.crc32(partition_array_bytes[:expected_total_bytes]) & 0xFFFFFFFF
                )
                is_array_crc_valid = calc_array_crc == stored_array_crc

        return cls(
            revision=revision,
            header_size=header_size,
            header_crc32=stored_header_crc,
            current_lba=current_lba,
            backup_lba=backup_lba,
            first_usable_lba=first_usable_lba,
            last_usable_lba=last_usable_lba,
            disk_guid=disk_guid,
            partition_entries_lba=part_entries_lba,
            num_partition_entries=num_entries,
            partition_entry_size=entry_size,
            partition_array_crc32=stored_array_crc,
            is_crc_valid=is_crc_valid,
            is_array_crc_valid=is_array_crc_valid,
        )


@dataclass(frozen=True)
class GptPartitionEntry:
    """Parsed single GPT partition entry."""

    slot: int
    type_guid: str
    unique_guid: str
    starting_lba: int
    ending_lba: int
    attributes: int
    name: str

    @property
    def is_empty(self) -> bool:
        return self.type_guid == GPT_TYPE_UNUSED or self.ending_lba < self.starting_lba

    @property
    def sector_count(self) -> int:
        if self.is_empty:
            return 0
        return self.ending_lba - self.starting_lba + 1

    @property
    def type_name(self) -> str:
        return KNOWN_GUID_NAMES.get(self.type_guid, f"GUID {self.type_guid}")


@dataclass(frozen=True)
class GptTable:
    """Result of full GPT analysis, including health status and partition entries."""

    health: GptHeaderHealth
    disk_guid: str
    entries: list[GptPartitionEntry]
    primary_header: GptHeader | None = None
    backup_header: GptHeader | None = None
    recovered_from_backup: bool = False
    notes: list[str] = field(default_factory=list)

    def to_partition_infos(self, sector_size: int = 512) -> list[PartitionInfo]:
        """Convert non-empty data partition entries to domain PartitionInfo objects."""
        infos: list[PartitionInfo] = []
        part_num = 1
        for entry in self.entries:
            if entry.is_empty or entry.sector_count == 0:
                continue

            name = entry.name or entry.type_name
            info = PartitionInfo(
                partition_number=part_num,
                start_sector=entry.starting_lba,
                sector_count=entry.sector_count,
                sector_size=sector_size,
                partition_type_or_guid=entry.type_guid,
                name=name,
                is_bootable=(entry.type_guid == GPT_TYPE_EFI_SYSTEM),
            )
            infos.append(info)
            part_num += 1
        return infos


class GptParser:
    """Read-only parser and validator for GUID Partition Tables."""

    @classmethod
    def parse(cls, reader: ReadOnlyBlockDevice) -> GptTable | None:
        """Parse Primary and Backup GPT headers and compare their integrity."""
        sector_size = reader.logical_sector_size
        total_sectors = reader.total_sectors

        if total_sectors < 3 or reader.size_bytes < 3 * sector_size:
            return None

        # 1. Read and parse Primary GPT at LBA 1
        primary_header, primary_entries, primary_valid = cls._read_gpt_at_lba(
            reader=reader,
            header_lba=1,
            sector_size=sector_size,
        )

        # 2. Determine Backup GPT LBA
        backup_lba = total_sectors - 1
        if primary_header is not None and 0 < primary_header.backup_lba < total_sectors:
            backup_lba = primary_header.backup_lba

        # Read and parse Backup GPT
        backup_header, backup_entries, backup_valid = cls._read_gpt_at_lba(
            reader=reader,
            header_lba=backup_lba,
            sector_size=sector_size,
            is_backup=True,
        )

        # 3. Assess GPT Header Health
        if primary_header is None and backup_header is None:
            return None

        notes: list[str] = []
        health: GptHeaderHealth
        recovered_from_backup = False
        active_entries: list[GptPartitionEntry] = []
        disk_guid = ""

        if primary_valid and backup_valid:
            health = GptHeaderHealth.BOTH_VALID
            active_entries = primary_entries
            disk_guid = primary_header.disk_guid if primary_header else ""
            notes.append("Both primary (LBA 1) and backup GPT headers and arrays are valid.")
        elif primary_valid and not backup_valid:
            health = GptHeaderHealth.PRIMARY_VALID_BACKUP_CORRUPT
            active_entries = primary_entries
            disk_guid = primary_header.disk_guid if primary_header else ""
            notes.append("Primary GPT header is valid; backup GPT header is invalid or corrupted.")
        elif not primary_valid and backup_valid:
            health = GptHeaderHealth.BACKUP_VALID_PRIMARY_CORRUPT
            active_entries = backup_entries
            disk_guid = backup_header.disk_guid if backup_header else ""
            recovered_from_backup = True
            notes.append(
                f"Primary GPT header is corrupted or invalid; recovered partition table "
                f"from intact Backup GPT at LBA {backup_lba}."
            )
        else:
            health = GptHeaderHealth.BOTH_CORRUPT
            disk_guid = (primary_header.disk_guid if primary_header else "") or (
                backup_header.disk_guid if backup_header else ""
            )
            # Try whichever entries had some data
            active_entries = primary_entries or backup_entries
            notes.append(
                "Both primary and backup GPT headers failed CRC validation (corrupted GPT)."
            )

        return GptTable(
            health=health,
            disk_guid=disk_guid,
            entries=active_entries,
            primary_header=primary_header,
            backup_header=backup_header,
            recovered_from_backup=recovered_from_backup,
            notes=notes,
        )

    @classmethod
    def _read_gpt_at_lba(
        cls,
        reader: ReadOnlyBlockDevice,
        header_lba: int,
        sector_size: int,
        is_backup: bool = False,
    ) -> tuple[GptHeader | None, list[GptPartitionEntry], bool]:
        """Read a GPT header and its partition entries from the specified LBA."""
        header_offset = header_lba * sector_size
        if header_offset + sector_size > reader.size_bytes:
            return None, [], False

        try:
            header_bytes = reader.read_at(header_offset, sector_size)
        except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
            return None, [], False

        if header_bytes[:8] != GPT_SIGNATURE:
            return None, [], False

        # Preliminary parse without partition array to discover partition_entry_lba
        prelim = GptHeader.parse(header_bytes)
        if prelim is None:
            return None, [], False

        # Read partition array bytes
        part_array_lba = prelim.partition_entries_lba
        num_entries = prelim.num_partition_entries
        entry_size = prelim.partition_entry_size

        if num_entries <= 0 or entry_size < DEFAULT_ENTRY_SIZE:
            return prelim, [], False

        total_array_bytes = num_entries * entry_size
        array_offset = part_array_lba * sector_size

        if array_offset + total_array_bytes > reader.size_bytes:
            # Out of bounds
            return prelim, [], False

        try:
            array_bytes = reader.read_at(array_offset, total_array_bytes)
        except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
            return prelim, [], False

        # Full parse with array bytes for CRC32 check
        header = GptHeader.parse(header_bytes, array_bytes)
        if header is None:
            return None, [], False

        is_valid = header.is_crc_valid and header.is_array_crc_valid

        # Parse individual partition entries
        entries: list[GptPartitionEntry] = []
        for i in range(num_entries):
            offset = i * entry_size
            entry_raw = array_bytes[offset : offset + entry_size]
            type_guid = bytes_to_guid(entry_raw[0:16])
            if type_guid == GPT_TYPE_UNUSED:
                continue

            unique_guid = bytes_to_guid(entry_raw[16:32])
            starting_lba = int.from_bytes(entry_raw[32:40], "little")
            ending_lba = int.from_bytes(entry_raw[40:48], "little")
            attributes = int.from_bytes(entry_raw[48:56], "little")

            # Name is up to 36 UTF-16LE characters (72 bytes)
            name_raw = entry_raw[56:128]
            name = name_raw.decode("utf-16le", errors="replace").rstrip("\x00")

            entries.append(
                GptPartitionEntry(
                    slot=i + 1,
                    type_guid=type_guid,
                    unique_guid=unique_guid,
                    starting_lba=starting_lba,
                    ending_lba=ending_lba,
                    attributes=attributes,
                    name=name,
                )
            )

        return header, entries, is_valid
