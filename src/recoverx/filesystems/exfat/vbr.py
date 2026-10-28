"""Volume Boot Record (VBR) parser, geometry validator, and checksum verification for exFAT."""

import struct
from dataclasses import dataclass

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice

EXFAT_OEM_NAME = b"EXFAT   "
BOOT_SIGNATURE = b"\x55\xaa"


def calculate_exfat_vbr_checksum(vbr_bytes: bytes, bytes_per_sector: int) -> int:
    """Calculate 32-bit checksum across the first 11 sectors of an exFAT boot region."""
    checksum = 0
    total_len = 11 * bytes_per_sector
    if len(vbr_bytes) < total_len:
        raise ValueError(f"VBR data too short ({len(vbr_bytes)} < {total_len})")

    for i in range(total_len):
        # In sector 0, skip VolumeFlags (bytes 106-107) and PercentInUse (byte 112)
        if i in (106, 107, 112):
            continue
        checksum = (((checksum << 31) & 0xFFFFFFFF) | (checksum >> 1)) + vbr_bytes[i]
        checksum &= 0xFFFFFFFF
    return checksum


@dataclass(frozen=True, slots=True)
class ExFatVbr:
    """Parsed and validated exFAT Volume Boot Record geometry."""

    bytes_per_sector: int
    sectors_per_cluster: int
    cluster_size_bytes: int
    partition_offset_sectors: int
    volume_length_sectors: int
    fat_offset_sectors: int
    fat_length_sectors: int
    cluster_heap_offset_sectors: int
    cluster_count: int
    root_cluster: int
    volume_serial_number: int
    fs_revision: int
    volume_flags: int
    num_fats: int
    base_offset: int
    is_backup: bool = False

    @property
    def total_size_bytes(self) -> int:
        """Total volume capacity in bytes."""
        return self.volume_length_sectors * self.bytes_per_sector

    @property
    def fat_byte_offset(self) -> int:
        """Byte offset where the FAT table begins."""
        return self.base_offset + (self.fat_offset_sectors * self.bytes_per_sector)

    @property
    def cluster_heap_byte_offset(self) -> int:
        """Byte offset where data cluster 2 begins."""
        return self.base_offset + (self.cluster_heap_offset_sectors * self.bytes_per_sector)

    def is_valid_cluster_num(self, cluster_num: int) -> bool:
        """Check if cluster_num falls within the valid cluster heap [2 .. 2 + cluster_count - 1]."""
        return 2 <= cluster_num < (2 + self.cluster_count)

    def cluster_to_byte_offset(self, cluster_num: int) -> int:
        """Convert a cluster number (>= 2) to its absolute byte offset on the device."""
        if not self.is_valid_cluster_num(cluster_num):
            raise ValueError(
                f"Cluster {cluster_num} outside exFAT heap [2, {2 + self.cluster_count - 1}]"
            )
        return self.cluster_heap_byte_offset + ((cluster_num - 2) * self.cluster_size_bytes)

    @classmethod
    def from_bytes(
        cls,
        boot_sector: bytes,
        base_offset: int = 0,
        device_size_bytes: int | None = None,
        is_backup: bool = False,
    ) -> "ExFatVbr":
        """Parse and validate exFAT parameters from sector 0."""
        if len(boot_sector) < 512:
            raise CorruptedBootSectorError(
                f"Boot sector data too short ({len(boot_sector)} bytes, expected 512)"
            )

        if boot_sector[510:512] != BOOT_SIGNATURE:
            raise CorruptedBootSectorError(
                f"Invalid boot signature: {boot_sector[510:512].hex()} (expected 55aa)"
            )

        if boot_sector[3:11] != EXFAT_OEM_NAME:
            raise CorruptedBootSectorError(
                f"Invalid exFAT OEM name: {boot_sector[3:11]!r} (expected {EXFAT_OEM_NAME!r})"
            )

        # Bytes 64..71: Partition offset (uint64)
        (part_offset,) = struct.unpack_from("<Q", boot_sector, 64)
        # Bytes 72..79: Volume length (uint64)
        (vol_length,) = struct.unpack_from("<Q", boot_sector, 72)
        if vol_length <= 0:
            raise CorruptedBootSectorError(f"Invalid exFAT volume length: {vol_length}")

        # Bytes 80..83: FAT offset (uint32)
        (fat_offset,) = struct.unpack_from("<I", boot_sector, 80)
        # Bytes 84..87: FAT length (uint32)
        (fat_length,) = struct.unpack_from("<I", boot_sector, 84)

        # Bytes 88..91: Cluster heap offset (uint32)
        (heap_offset,) = struct.unpack_from("<I", boot_sector, 88)
        # Bytes 92..95: Cluster count (uint32)
        (cluster_count,) = struct.unpack_from("<I", boot_sector, 92)
        if cluster_count <= 0:
            raise CorruptedBootSectorError(f"Invalid exFAT cluster count: {cluster_count}")

        # Bytes 96..99: Root directory starting cluster (uint32)
        (root_cluster,) = struct.unpack_from("<I", boot_sector, 96)
        if root_cluster < 2:
            raise CorruptedBootSectorError(
                f"Invalid exFAT root cluster: {root_cluster} (must be >= 2)"
            )

        # Bytes 100..103: Volume serial number
        (serial_num,) = struct.unpack_from("<I", boot_sector, 100)
        # Bytes 104..105: FS revision
        (fs_rev,) = struct.unpack_from("<H", boot_sector, 104)
        # Bytes 106..107: Volume flags
        (vol_flags,) = struct.unpack_from("<H", boot_sector, 106)

        # Byte 108: Bytes per sector shift (power of 2)
        sec_shift = boot_sector[108]
        if sec_shift not in (9, 10, 11, 12):
            raise CorruptedBootSectorError(
                f"Invalid BytesPerSectorShift: {sec_shift} (must be 9..12 for 512B..4096B)"
            )
        bytes_per_sec = 1 << sec_shift

        # Byte 109: Sectors per cluster shift (power of 2)
        clus_shift = boot_sector[109]
        if sec_shift + clus_shift > 25:
            raise CorruptedBootSectorError(
                f"Cluster size shift ({sec_shift + clus_shift}) exceeds 25 (32 MiB limit)"
            )
        sec_per_clus = 1 << clus_shift
        cluster_size = bytes_per_sec * sec_per_clus

        # Byte 110: Number of FATs
        num_fats = boot_sector[110]
        if num_fats not in (1, 2):
            raise CorruptedBootSectorError(
                f"Invalid NumberOfFats in exFAT: {num_fats} (must be 1 or 2)"
            )

        if heap_offset < fat_offset + (num_fats * fat_length):
            raise CorruptedBootSectorError(
                f"Cluster heap offset ({heap_offset}) overlaps FAT table region"
            )

        if (
            device_size_bytes is not None
            and base_offset + (vol_length * bytes_per_sec) > device_size_bytes
        ):
            raise CorruptedBootSectorError(
                f"exFAT volume exceeds device capacity: "
                f"{base_offset + vol_length * bytes_per_sec} > {device_size_bytes}"
            )

        return cls(
            bytes_per_sector=bytes_per_sec,
            sectors_per_cluster=sec_per_clus,
            cluster_size_bytes=cluster_size,
            partition_offset_sectors=part_offset,
            volume_length_sectors=vol_length,
            fat_offset_sectors=fat_offset,
            fat_length_sectors=fat_length,
            cluster_heap_offset_sectors=heap_offset,
            cluster_count=cluster_count,
            root_cluster=root_cluster,
            volume_serial_number=serial_num,
            fs_revision=fs_rev,
            volume_flags=vol_flags,
            num_fats=num_fats,
            base_offset=base_offset,
            is_backup=is_backup,
        )

    @classmethod
    def from_reader(cls, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> "ExFatVbr":
        """Read and validate the exFAT VBR, falling back to backup boot region if corrupted.

        1. Attempts to read Main Boot Region (sectors 0..11).
        2. Validates sector 0 parameters and verifies sector 11 checksum.
        3. If primary is damaged, attempts Backup Boot Region (sectors 12..23).
        """
        primary_error: Exception | None = None

        # 1. Probe primary boot sector
        try:
            sector_0 = reader.read_at(base_offset, 512)
            vbr = cls.from_bytes(
                sector_0,
                base_offset=base_offset,
                device_size_bytes=reader.size_bytes,
                is_backup=False,
            )

            # Check sector 11 checksum if whole boot region fits on device
            region_len = 12 * vbr.bytes_per_sector
            if base_offset + region_len <= reader.size_bytes:
                vbr_region = reader.read_at(base_offset, region_len)
                expected_chk = calculate_exfat_vbr_checksum(vbr_region, vbr.bytes_per_sector)
                sec11_offset = 11 * vbr.bytes_per_sector
                (actual_chk,) = struct.unpack_from("<I", vbr_region, sec11_offset)
                if expected_chk == actual_chk:
                    return vbr
                else:
                    primary_error = CorruptedBootSectorError(
                        f"Boot checksum mismatch: exp 0x{expected_chk:08X}, got 0x{actual_chk:08X}"
                    )
            else:
                return vbr
        except CorruptedBootSectorError as e:
            primary_error = e

        # 2. Try Backup Boot Region (sectors 12..23)
        # We need sector size; try common 512 and 4096
        for bps in (512, 4096):
            backup_offset = base_offset + (12 * bps)
            if backup_offset + 512 <= reader.size_bytes:
                try:
                    sec_12 = reader.read_at(backup_offset, 512)
                    backup_vbr = cls.from_bytes(
                        sec_12,
                        base_offset=base_offset,
                        device_size_bytes=reader.size_bytes,
                        is_backup=True,
                    )
                    return backup_vbr
                except CorruptedBootSectorError:
                    continue

        if primary_error:
            raise primary_error
        raise CorruptedBootSectorError("No valid exFAT boot record located")
