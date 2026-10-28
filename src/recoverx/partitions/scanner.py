"""Boot-sector signature scanner for locating lost or damaged volumes."""

import logging
from collections.abc import Callable

from recoverx.domain.enums import FileSystemType
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)
from recoverx.partitions.models import VolumeCandidate

logger = logging.getLogger(__name__)

BOOT_SIG = b"\x55\xaa"
EXFAT_SIG = b"EXFAT   "
NTFS_SIG = b"NTFS    "
FAT32_SIG = b"FAT32   "
FAT16_SIG = b"FAT16   "
FAT12_SIG = b"FAT12   "

# Common partition start sectors on PC removable media and hard disks
COMMON_START_SECTORS = (
    0,  # Superfloppy / unpartitioned
    63,  # Legacy DOS / Windows XP MBR alignment
    128,  # 64KB alignment
    2048,  # 1MB alignment (Windows Vista/7/8/10/11, macOS, Linux modern standard)
    4096,  # 2MB alignment
    8192,  # 4MB alignment
    16384,  # 8MB alignment
    32768,  # 16MB alignment
    65536,  # 32MB alignment
)


class LostVolumeScanner:
    """Read-only scanner detecting filesystem boot sectors and backup boot structures."""

    @classmethod
    def scan(
        cls,
        reader: ReadOnlyBlockDevice,
        start_sector: int = 0,
        end_sector: int | None = None,
        step_sectors: int = 1,
        max_candidates: int = 100,
        priority_first: bool = True,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> list[VolumeCandidate]:
        """Scan block device for FAT12/16/32, exFAT, and NTFS volumes."""
        total_sectors = reader.total_sectors
        if total_sectors <= 0 or reader.size_bytes < 512:
            return []

        if end_sector is None or end_sector > total_sectors:
            end_sector = total_sectors

        sector_size = reader.logical_sector_size
        candidates_by_start: dict[int, VolumeCandidate] = {}

        def inspect_sector(sector: int) -> VolumeCandidate | None:
            """Inspect a single sector for primary or backup boot structures."""
            offset = sector * sector_size
            if offset + 512 > reader.size_bytes:
                return None

            try:
                data = reader.read_at(offset, 512)
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                return None

            if data[510:512] != BOOT_SIG:
                return None

            # 1. Check exFAT
            if data[3:11] == EXFAT_SIG:
                cand = cls._inspect_exfat_sector(reader, sector, data)
                if cand is not None:
                    return cand

            # 2. Check NTFS
            if data[3:11] == NTFS_SIG:
                cand = cls._inspect_ntfs_sector(reader, sector, data)
                if cand is not None:
                    return cand

            # 3. Check FAT12 / FAT16 / FAT32
            cand_fat = cls._inspect_fat_sector(reader, sector, data)
            if cand_fat is not None:
                return cand_fat

            return None

        # Pass 1: Check priority / high-probability sectors first
        if priority_first:
            for s in COMMON_START_SECTORS:
                if start_sector <= s < end_sector and s not in candidates_by_start:
                    candidate = inspect_sector(s)
                    if candidate:
                        candidates_by_start[candidate.start_sector] = candidate
                        if len(candidates_by_start) >= max_candidates:
                            return list(candidates_by_start.values())

        # Pass 2: Sequential sector sweep
        total_to_scan = max(1, (end_sector - start_sector) // max(1, step_sectors))

        for scanned, sector in enumerate(
            range(start_sector, end_sector, max(1, step_sectors)), start=1
        ):
            if len(candidates_by_start) >= max_candidates:
                break

            if sector not in candidates_by_start:
                cand = inspect_sector(sector)
                if cand and cand.start_sector not in candidates_by_start:
                    candidates_by_start[cand.start_sector] = cand

            if progress_callback and (scanned % 1000 == 0 or scanned == total_to_scan):
                progress_callback(scanned, total_to_scan)

        return sorted(candidates_by_start.values(), key=lambda c: c.start_sector)

    @classmethod
    def _inspect_exfat_sector(
        cls,
        reader: ReadOnlyBlockDevice,
        sector: int,
        data: bytes,
    ) -> VolumeCandidate | None:
        """Inspect sector matching EXFAT signature (primary or backup region)."""
        sector_size = reader.logical_sector_size
        bytes_per_sec_shift = data[108]
        if bytes_per_sec_shift < 9 or bytes_per_sec_shift > 12:
            return None

        vbr_sector_size = 1 << bytes_per_sec_shift
        vol_length_sectors = int.from_bytes(data[72:80], "little")
        if vol_length_sectors <= 0:
            return None

        # Check if sector + 12 has exFAT backup VBR -> this sector is PRIMARY
        has_backup_ahead = False
        backup_offset_ahead = (sector + 12) * sector_size
        if backup_offset_ahead + 512 <= reader.size_bytes:
            try:
                ahead_bytes = reader.read_at(backup_offset_ahead, 512)
                if ahead_bytes[3:11] == EXFAT_SIG and ahead_bytes[510:512] == BOOT_SIG:
                    has_backup_ahead = True
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                pass

        if has_backup_ahead:
            return VolumeCandidate(
                start_sector=sector,
                sector_count=vol_length_sectors,
                sector_size=vbr_sector_size,
                filesystem_type=FileSystemType.EXFAT,
                detection_source=f"Primary exFAT boot sector at sector {sector}",
                evidence=f"Valid exFAT primary VBR, volume length {vol_length_sectors} sectors",
                is_backup_structure=False,
            )

        # If not primary with backup ahead, could sector be backup of (sector - 12)?
        if sector >= 12:
            behind_offset = (sector - 12) * sector_size
            primary_behind_valid = False
            try:
                behind_bytes = reader.read_at(behind_offset, 512)
                if behind_bytes[3:11] == EXFAT_SIG and behind_bytes[510:512] == BOOT_SIG:
                    primary_behind_valid = True
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                pass

            if primary_behind_valid:
                # Primary already exists; do not return duplicate candidate for backup
                return None

            # Primary behind is wiped/damaged -> this is surviving backup!
            return VolumeCandidate(
                start_sector=sector - 12,
                sector_count=vol_length_sectors,
                sector_size=vbr_sector_size,
                filesystem_type=FileSystemType.EXFAT,
                detection_source=(
                    f"exFAT backup boot region at sector {sector} "
                    f"(reconstructed volume start at sector {sector - 12})"
                ),
                evidence=(
                    f"Valid exFAT backup VBR at sector {sector}; primary missing; "
                    f"volume length {vol_length_sectors} sectors"
                ),
                is_backup_structure=True,
            )

        # Primary VBR without backup
        return VolumeCandidate(
            start_sector=sector,
            sector_count=vol_length_sectors,
            sector_size=vbr_sector_size,
            filesystem_type=FileSystemType.EXFAT,
            detection_source=f"Primary exFAT boot sector at sector {sector}",
            evidence=f"Valid exFAT primary VBR, volume length {vol_length_sectors} sectors",
            is_backup_structure=False,
        )

    @classmethod
    def _inspect_ntfs_sector(
        cls,
        reader: ReadOnlyBlockDevice,
        sector: int,
        data: bytes,
    ) -> VolumeCandidate | None:
        """Inspect sector matching NTFS signature (primary or backup boot sector)."""
        sector_size = reader.logical_sector_size
        bytes_per_sec = int.from_bytes(data[11:13], "little")
        if bytes_per_sec not in (512, 1024, 2048, 4096):
            return None

        total_sectors = int.from_bytes(data[40:48], "little")
        if total_sectors <= 0:
            return None

        # Check if sector + total_sectors has NTFS backup -> this sector is PRIMARY
        has_backup_ahead = False
        backup_offset_ahead = (sector + total_sectors) * sector_size
        if backup_offset_ahead + 512 <= reader.size_bytes:
            try:
                ahead_bytes = reader.read_at(backup_offset_ahead, 512)
                if ahead_bytes[3:11] == NTFS_SIG and ahead_bytes[510:512] == BOOT_SIG:
                    has_backup_ahead = True
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                pass

        if has_backup_ahead:
            return VolumeCandidate(
                start_sector=sector,
                sector_count=total_sectors,
                sector_size=bytes_per_sec,
                filesystem_type=FileSystemType.NTFS,
                detection_source=f"Primary NTFS boot sector at sector {sector}",
                evidence=f"Valid NTFS primary boot sector, total sectors {total_sectors}",
                is_backup_structure=False,
            )

        # If not primary with backup ahead, could sector be backup of (sector - total_sectors)?
        if sector >= total_sectors:
            behind_offset = (sector - total_sectors) * sector_size
            primary_behind_valid = False
            try:
                behind_bytes = reader.read_at(behind_offset, 512)
                if behind_bytes[3:11] == NTFS_SIG and behind_bytes[510:512] == BOOT_SIG:
                    primary_behind_valid = True
            except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                pass

            if primary_behind_valid:
                # Primary already exists; do not return duplicate candidate
                return None

            # Primary behind is wiped/damaged -> this is surviving backup!
            return VolumeCandidate(
                start_sector=sector - total_sectors,
                sector_count=total_sectors,
                sector_size=bytes_per_sec,
                filesystem_type=FileSystemType.NTFS,
                detection_source=(
                    f"NTFS backup boot sector at sector {sector} "
                    f"(reconstructed volume start at sector {sector - total_sectors})"
                ),
                evidence=(
                    f"Valid NTFS backup boot sector at sector {sector}; primary missing; "
                    f"total sectors {total_sectors}"
                ),
                is_backup_structure=True,
            )

        # Primary NTFS boot sector
        return VolumeCandidate(
            start_sector=sector,
            sector_count=total_sectors,
            sector_size=bytes_per_sec,
            filesystem_type=FileSystemType.NTFS,
            detection_source=f"Primary NTFS boot sector at sector {sector}",
            evidence=f"Valid NTFS primary boot sector, total sectors {total_sectors}",
            is_backup_structure=False,
        )

    @classmethod
    def _inspect_fat_sector(
        cls,
        reader: ReadOnlyBlockDevice,
        sector: int,
        data: bytes,
    ) -> VolumeCandidate | None:
        """Inspect sector for FAT12, FAT16, or FAT32 primary or backup boot sector."""
        sector_size = reader.logical_sector_size

        # Validate basic BPB constraints
        bytes_per_sec = int.from_bytes(data[11:13], "little")
        if bytes_per_sec not in (512, 1024, 2048, 4096):
            return None

        sec_per_cluster = data[13]
        if sec_per_cluster not in (1, 2, 4, 8, 16, 32, 64, 128):
            return None

        reserved_sectors = int.from_bytes(data[14:16], "little")
        if reserved_sectors == 0:
            return None

        num_fats = data[16]
        if num_fats not in (1, 2):
            return None

        # Total sectors check
        total_sectors_16 = int.from_bytes(data[19:21], "little")
        total_sectors_32 = int.from_bytes(data[32:36], "little")
        total_sectors = total_sectors_16 or total_sectors_32
        if total_sectors == 0:
            return None

        # Check FAT32 specific backup sector
        is_fat32 = False
        bk_boot_sec = 0
        fat_type_str = ""

        if data[82:90] == FAT32_SIG:
            is_fat32 = True
            bk_boot_sec = int.from_bytes(data[50:52], "little")
            fat_type_str = "FAT32"
        elif data[54:62] == FAT16_SIG:
            fat_type_str = "FAT16"
        elif data[54:62] == FAT12_SIG:
            fat_type_str = "FAT12"
        else:
            # Check cluster count heuristic
            fat_size_16 = int.from_bytes(data[22:24], "little")
            fat_size_32 = int.from_bytes(data[36:40], "little")
            fat_size = fat_size_16 or fat_size_32
            root_dir_entries = int.from_bytes(data[17:19], "little")
            root_dir_sectors = ((root_dir_entries * 32) + (bytes_per_sec - 1)) // bytes_per_sec
            overhead = reserved_sectors + (num_fats * fat_size) + root_dir_sectors
            data_sectors = total_sectors - overhead
            count_of_clusters = data_sectors // sec_per_cluster if data_sectors > 0 else 0

            if count_of_clusters >= 65525:
                is_fat32 = True
                bk_boot_sec = int.from_bytes(data[50:52], "little")
                fat_type_str = "FAT32"
            elif count_of_clusters >= 4085:
                fat_type_str = "FAT16"
            elif count_of_clusters > 0:
                fat_type_str = "FAT12"
            else:
                return None

        fs_type = {
            "FAT32": FileSystemType.FAT32,
            "FAT16": FileSystemType.FAT16,
            "FAT12": FileSystemType.FAT12,
        }.get(fat_type_str, FileSystemType.UNKNOWN)

        # Check if sector + bk_boot_sec has FAT32 backup -> this sector is PRIMARY
        if is_fat32 and bk_boot_sec > 0:
            has_backup_ahead = False
            backup_offset_ahead = (sector + bk_boot_sec) * sector_size
            if backup_offset_ahead + 512 <= reader.size_bytes:
                try:
                    ahead_bytes = reader.read_at(backup_offset_ahead, 512)
                    if ahead_bytes[510:512] == BOOT_SIG and ahead_bytes[82:90] == FAT32_SIG:
                        has_backup_ahead = True
                except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                    pass

            if has_backup_ahead:
                return VolumeCandidate(
                    start_sector=sector,
                    sector_count=total_sectors,
                    sector_size=bytes_per_sec,
                    filesystem_type=fs_type,
                    detection_source=f"Primary {fat_type_str} boot sector at sector {sector}",
                    evidence=f"Valid {fat_type_str} primary BPB, total sectors {total_sectors}",
                    is_backup_structure=False,
                )

            # Check if this is a surviving backup of (sector - bk_boot_sec)
            if sector >= bk_boot_sec:
                behind_offset = (sector - bk_boot_sec) * sector_size
                primary_behind_valid = False
                try:
                    behind_bytes = reader.read_at(behind_offset, 512)
                    if behind_bytes[510:512] == BOOT_SIG and behind_bytes[82:90] == FAT32_SIG:
                        primary_behind_valid = True
                except (DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
                    pass

                if primary_behind_valid:
                    # Primary already exists; do not return duplicate candidate
                    return None

                # Primary behind is wiped/damaged -> this is surviving backup!
                return VolumeCandidate(
                    start_sector=sector - bk_boot_sec,
                    sector_count=total_sectors,
                    sector_size=bytes_per_sec,
                    filesystem_type=fs_type,
                    detection_source=(
                        f"FAT32 backup boot sector at sector {sector} "
                        f"(reconstructed volume start at sector {sector - bk_boot_sec})"
                    ),
                    evidence=(
                        f"Valid FAT32 backup BPB at sector {sector}; primary missing; "
                        f"cluster size {bytes_per_sec * sec_per_cluster}B"
                    ),
                    is_backup_structure=True,
                )

        # Primary FAT boot sector
        return VolumeCandidate(
            start_sector=sector,
            sector_count=total_sectors,
            sector_size=bytes_per_sec,
            filesystem_type=fs_type,
            detection_source=f"Primary {fat_type_str} boot sector at sector {sector}",
            evidence=f"Valid {fat_type_str} primary BPB, total sectors {total_sectors}",
            is_backup_structure=False,
        )
