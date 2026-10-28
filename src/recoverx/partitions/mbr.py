"""Master Boot Record (MBR) and Extended Boot Record (EBR) parser."""

import logging
from dataclasses import dataclass, field

from recoverx.domain.partition import PartitionInfo
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)

logger = logging.getLogger(__name__)

MBR_SIGNATURE = b"\x55\xaa"
MBR_TABLE_OFFSET = 446
MBR_ENTRY_SIZE = 16
NUM_MBR_ENTRIES = 4

# Known MBR Partition Types
MBR_TYPE_EMPTY = 0x00
MBR_TYPE_FAT12 = 0x01
MBR_TYPE_FAT16_LESS_32MB = 0x04
MBR_TYPE_EXTENDED_CHS = 0x05
MBR_TYPE_FAT16 = 0x06
MBR_TYPE_NTFS_EXFAT = 0x07
MBR_TYPE_FAT32_CHS = 0x0B
MBR_TYPE_FAT32_LBA = 0x0C
MBR_TYPE_FAT16_LBA = 0x0E
MBR_TYPE_EXTENDED_LBA = 0x0F
MBR_TYPE_LINUX = 0x83
MBR_TYPE_PROTECTIVE_GPT = 0xEE
MBR_TYPE_EFI_SYSTEM = 0xEF

EXTENDED_PARTITION_TYPES = {MBR_TYPE_EXTENDED_CHS, MBR_TYPE_EXTENDED_LBA}

PARTITION_TYPE_NAMES: dict[int, str] = {
    MBR_TYPE_EMPTY: "Empty",
    MBR_TYPE_FAT12: "FAT12",
    MBR_TYPE_FAT16_LESS_32MB: "FAT16 (<32MB)",
    MBR_TYPE_EXTENDED_CHS: "Extended (CHS)",
    MBR_TYPE_FAT16: "FAT16",
    MBR_TYPE_NTFS_EXFAT: "NTFS / exFAT",
    MBR_TYPE_FAT32_CHS: "FAT32 (CHS)",
    MBR_TYPE_FAT32_LBA: "FAT32 (LBA)",
    MBR_TYPE_FAT16_LBA: "FAT16 (LBA)",
    MBR_TYPE_EXTENDED_LBA: "Extended (LBA)",
    MBR_TYPE_LINUX: "Linux Native",
    MBR_TYPE_PROTECTIVE_GPT: "GPT Protective MBR",
    MBR_TYPE_EFI_SYSTEM: "EFI System",
}


class MbrError(Exception):
    """Base exception for MBR parsing errors."""


class MbrInvalidSignatureError(MbrError):
    """Raised when sector 0 does not end with 0x55 0xAA."""


@dataclass(frozen=True)
class MbrPartitionEntry:
    """Raw parsed MBR or EBR partition record."""

    slot: int
    boot_indicator: int
    partition_type: int
    lba_start: int
    sector_count: int
    is_extended: bool = False
    is_logical: bool = False

    @property
    def is_bootable(self) -> bool:
        return self.boot_indicator == 0x80

    @property
    def is_empty(self) -> bool:
        return self.partition_type == MBR_TYPE_EMPTY and self.sector_count == 0

    @property
    def type_name(self) -> str:
        return PARTITION_TYPE_NAMES.get(
            self.partition_type, f"Unknown (0x{self.partition_type:02X})"
        )


@dataclass(frozen=True)
class MbrTable:
    """Parsed MBR table containing primary and logical partitions."""

    disk_signature: int
    is_protective: bool
    entries: list[MbrPartitionEntry]
    notes: list[str] = field(default_factory=list)

    def to_partition_infos(self, sector_size: int = 512) -> list[PartitionInfo]:
        """Convert valid non-empty data partitions to domain PartitionInfo objects."""
        infos: list[PartitionInfo] = []
        part_num = 1
        for entry in self.entries:
            if (
                entry.is_empty
                or entry.is_extended
                or entry.partition_type == MBR_TYPE_PROTECTIVE_GPT
            ):
                continue
            if entry.sector_count == 0:
                continue

            info = PartitionInfo(
                partition_number=part_num,
                start_sector=entry.lba_start,
                sector_count=entry.sector_count,
                sector_size=sector_size,
                partition_type_or_guid=f"0x{entry.partition_type:02X}",
                name=entry.type_name,
                is_bootable=entry.is_bootable,
            )
            infos.append(info)
            part_num += 1
        return infos


class MbrParser:
    """Read-only parser for MBR and EBR partition tables."""

    @classmethod
    def parse(cls, reader: ReadOnlyBlockDevice) -> MbrTable | None:
        """Parse MBR from sector 0 of the given reader.

        Returns None if sector 0 does not have the 0x55 0xAA boot signature.
        """
        if reader.size_bytes < 512:
            return None

        try:
            sector_0 = reader.read_at(0, 512)
        except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
            return None

        if sector_0[510:512] != MBR_SIGNATURE:
            return None

        disk_signature = int.from_bytes(sector_0[440:444], "little")
        notes: list[str] = []
        primary_entries: list[MbrPartitionEntry] = []
        is_protective = False
        device_total_sectors = reader.total_sectors

        # Parse 4 primary entries
        for slot in range(NUM_MBR_ENTRIES):
            offset = MBR_TABLE_OFFSET + (slot * MBR_ENTRY_SIZE)
            entry_raw = sector_0[offset : offset + MBR_ENTRY_SIZE]

            boot_indicator = entry_raw[0]
            ptype = entry_raw[4]
            lba_start = int.from_bytes(entry_raw[8:12], "little")
            count = int.from_bytes(entry_raw[12:16], "little")

            if boot_indicator not in (0x00, 0x80) and ptype != MBR_TYPE_EMPTY:
                notes.append(
                    f"Slot {slot + 1}: non-standard boot indicator "
                    f"0x{boot_indicator:02X} (corrupted entry flag?)"
                )

            if ptype == MBR_TYPE_PROTECTIVE_GPT:
                is_protective = True

            is_ext = ptype in EXTENDED_PARTITION_TYPES

            # Bounds check against device size
            if (
                count > 0
                and device_total_sectors > 0
                and (lba_start >= device_total_sectors or lba_start + count > device_total_sectors)
            ):
                notes.append(
                    f"Slot {slot + 1}: partition range [{lba_start}, {lba_start + count}) "
                    f"extends past disk capacity ({device_total_sectors} sectors)"
                )

            entry = MbrPartitionEntry(
                slot=slot + 1,
                boot_indicator=boot_indicator,
                partition_type=ptype,
                lba_start=lba_start,
                sector_count=count,
                is_extended=is_ext,
                is_logical=False,
            )
            primary_entries.append(entry)

        all_entries: list[MbrPartitionEntry] = list(primary_entries)

        # Parse Extended Boot Record (EBR) chains if present
        for entry in primary_entries:
            if entry.is_extended and entry.sector_count > 0:
                logical_entries = cls._parse_ebr_chain(reader, entry.lba_start, notes)
                all_entries.extend(logical_entries)

        return MbrTable(
            disk_signature=disk_signature,
            is_protective=is_protective,
            entries=all_entries,
            notes=notes,
        )

    @classmethod
    def _parse_ebr_chain(
        cls,
        reader: ReadOnlyBlockDevice,
        ext_base_lba: int,
        notes: list[str],
        max_logical_partitions: int = 64,
    ) -> list[MbrPartitionEntry]:
        """Safely traverse an EBR linked list with loop and bound protection."""
        logical_entries: list[MbrPartitionEntry] = []
        visited_sectors: set[int] = set()
        current_ebr_lba = ext_base_lba
        logical_slot = 5
        sector_size = reader.logical_sector_size
        device_total_sectors = reader.total_sectors

        while current_ebr_lba not in visited_sectors:
            visited_sectors.add(current_ebr_lba)
            if len(logical_entries) >= max_logical_partitions:
                notes.append(
                    f"EBR chain stopped: exceeded limit of {max_logical_partitions} partitions"
                )
                break

            ebr_offset = current_ebr_lba * sector_size
            if ebr_offset + 512 > reader.size_bytes:
                notes.append(f"EBR sector {current_ebr_lba} extends beyond device capacity")
                break

            try:
                ebr_bytes = reader.read_at(ebr_offset, 512)
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                notes.append(f"Failed to read EBR at sector {current_ebr_lba}")
                break

            if ebr_bytes[510:512] != MBR_SIGNATURE:
                notes.append(f"EBR at sector {current_ebr_lba} missing 0x55 0xAA signature")
                break

            # Entry 1: Logical partition record
            e1 = ebr_bytes[MBR_TABLE_OFFSET : MBR_TABLE_OFFSET + MBR_ENTRY_SIZE]
            boot_ind = e1[0]
            ptype = e1[4]
            rel_start = int.from_bytes(e1[8:12], "little")
            count = int.from_bytes(e1[12:16], "little")

            if ptype != MBR_TYPE_EMPTY and count > 0:
                abs_start = current_ebr_lba + rel_start
                if device_total_sectors > 0 and (abs_start + count > device_total_sectors):
                    notes.append(
                        f"Logical partition {logical_slot} [{abs_start}, {abs_start + count}) "
                        f"extends past device capacity"
                    )

                logical_entry = MbrPartitionEntry(
                    slot=logical_slot,
                    boot_indicator=boot_ind,
                    partition_type=ptype,
                    lba_start=abs_start,
                    sector_count=count,
                    is_extended=False,
                    is_logical=True,
                )
                logical_entries.append(logical_entry)
                logical_slot += 1

            # Entry 2: Pointer to next EBR in chain (relative to ext_base_lba!)
            e2_start = MBR_TABLE_OFFSET + MBR_ENTRY_SIZE
            e2 = ebr_bytes[e2_start : e2_start + MBR_ENTRY_SIZE]
            next_ptype = e2[4]
            next_rel_start = int.from_bytes(e2[8:12], "little")
            next_count = int.from_bytes(e2[12:16], "little")

            if next_count == 0 or next_ptype not in EXTENDED_PARTITION_TYPES:
                # End of chain
                break

            next_ebr_lba = ext_base_lba + next_rel_start
            if next_ebr_lba in visited_sectors:
                notes.append(f"EBR loop detected at sector {next_ebr_lba}")
                break

            current_ebr_lba = next_ebr_lba

        return logical_entries
