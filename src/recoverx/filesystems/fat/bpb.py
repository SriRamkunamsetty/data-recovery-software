"""BIOS Parameter Block (BPB) parser and validator for FAT12, FAT16, and FAT32."""

import struct
from dataclasses import dataclass

from recoverx.domain.enums import FileSystemType
from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice

BOOT_SIGNATURE = b"\x55\xaa"


@dataclass(frozen=True, slots=True)
class FatBpb:
    """Parsed and validated BIOS Parameter Block geometry and parameters."""

    bytes_per_sector: int
    sectors_per_cluster: int
    reserved_sectors: int
    num_fats: int
    root_entry_count: int
    total_sectors: int
    media_descriptor: int
    sectors_per_fat: int
    root_cluster: int
    backup_boot_sector: int
    fs_version: int
    volume_label: str
    filesystem_type: FileSystemType
    total_clusters: int
    cluster_size_bytes: int
    root_dir_sectors: int
    first_data_sector: int
    base_offset: int
    is_backup: bool = False

    @property
    def total_size_bytes(self) -> int:
        """Total capacity of the filesystem volume in bytes."""
        return self.total_sectors * self.bytes_per_sector

    def fat_offset_bytes(self, fat_index: int = 0) -> int:
        """Byte offset of the designated FAT copy (0-indexed)."""
        if fat_index < 0 or fat_index >= self.num_fats:
            raise ValueError(f"fat_index {fat_index} out of range (num_fats={self.num_fats})")
        sec = self.reserved_sectors + (fat_index * self.sectors_per_fat)
        return self.base_offset + (sec * self.bytes_per_sector)

    @property
    def root_dir_offset_bytes(self) -> int:
        """Byte offset of the root directory for FAT12/16."""
        if self.filesystem_type == FileSystemType.FAT32:
            return self.cluster_to_byte_offset(self.root_cluster)
        sec = self.reserved_sectors + (self.num_fats * self.sectors_per_fat)
        return self.base_offset + (sec * self.bytes_per_sector)

    @property
    def root_dir_size_bytes(self) -> int:
        """Byte size of the root directory region for FAT12/16."""
        return self.root_dir_sectors * self.bytes_per_sector

    @property
    def first_data_byte_offset(self) -> int:
        """Byte offset where data cluster 2 begins."""
        return self.base_offset + (self.first_data_sector * self.bytes_per_sector)

    def cluster_to_byte_offset(self, cluster_num: int) -> int:
        """Convert a cluster number (>= 2) to its absolute byte offset on the device."""
        if not self.is_valid_cluster_num(cluster_num):
            raise ValueError(
                f"Cluster {cluster_num} is out of valid bounds [2, {2 + self.total_clusters - 1}]"
            )
        return self.first_data_byte_offset + ((cluster_num - 2) * self.cluster_size_bytes)

    def is_valid_cluster_num(self, cluster_num: int) -> bool:
        """Check if cluster number falls within valid data region [2 .. total_clusters + 1]."""
        return 2 <= cluster_num < (2 + self.total_clusters)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        base_offset: int = 0,
        device_size_bytes: int | None = None,
        is_backup: bool = False,
    ) -> "FatBpb":
        """Parse and validate BPB from a 512-byte sector.

        Args:
            data: Raw sector bytes (minimum 512 bytes).
            base_offset: Base byte offset of the partition/volume on the block device.
            device_size_bytes: Optional total capacity of the block device to verify bounds.
            is_backup: True if parsed from a backup boot sector.

        Raises:
            CorruptedBootSectorError: If signature, bounds, or arithmetic validation fails.
        """
        if len(data) < 512:
            raise CorruptedBootSectorError(
                f"Boot sector data too short ({len(data)} bytes, expected 512)"
            )

        # Validate standard boot signature 0x55, 0xAA at offsets 510-511
        if data[510:512] != BOOT_SIGNATURE:
            raise CorruptedBootSectorError(
                f"Invalid boot sector signature: {data[510:512].hex()} (expected 55aa)"
            )

        # Bytes 11-12: Bytes per sector
        (byts_per_sec,) = struct.unpack_from("<H", data, 11)
        if byts_per_sec not in (512, 1024, 2048, 4096):
            raise CorruptedBootSectorError(
                f"Invalid bytes per sector: {byts_per_sec} (must be 512, 1024, 2048, or 4096)"
            )

        # Byte 13: Sectors per cluster (must be power of 2)
        sec_per_clus = data[13]
        if sec_per_clus not in (1, 2, 4, 8, 16, 32, 64, 128):
            raise CorruptedBootSectorError(
                f"Invalid sectors per cluster: {sec_per_clus} (must be power of 2 in 1..128)"
            )

        cluster_size = byts_per_sec * sec_per_clus
        if cluster_size > 64 * 1024:
            raise CorruptedBootSectorError(
                f"Implausible cluster size: {cluster_size} bytes (exceeds 64 KiB FAT limit)"
            )

        # Bytes 14-15: Reserved sector count
        (rsvd_sec_cnt,) = struct.unpack_from("<H", data, 14)
        if rsvd_sec_cnt < 1:
            raise CorruptedBootSectorError(f"Invalid reserved sector count: {rsvd_sec_cnt}")

        # Byte 16: Number of FATs
        num_fats = data[16]
        if num_fats < 1 or num_fats > 4:
            raise CorruptedBootSectorError(f"Invalid number of FAT tables: {num_fats}")

        # Bytes 17-18: Root entry count (FAT12/16 only; 0 on FAT32)
        (root_ent_cnt,) = struct.unpack_from("<H", data, 17)

        # Bytes 19-20: 16-bit total sectors
        (tot_sec_16,) = struct.unpack_from("<H", data, 19)

        # Byte 21: Media descriptor
        media = data[21]

        # Bytes 22-23: 16-bit sectors per FAT
        (fat_sz_16,) = struct.unpack_from("<H", data, 22)

        # Bytes 32-35: 32-bit total sectors
        (tot_sec_32,) = struct.unpack_from("<I", data, 32)

        total_sectors = tot_sec_16 if tot_sec_16 != 0 else tot_sec_32
        if total_sectors <= 0:
            raise CorruptedBootSectorError("Total sector count is zero")

        if (
            device_size_bytes is not None
            and base_offset + (total_sectors * byts_per_sec) > device_size_bytes
        ):
            raise CorruptedBootSectorError(
                f"Filesystem volume exceeds device capacity: "
                f"{base_offset + total_sectors * byts_per_sec} > {device_size_bytes}"
            )

        # Determine FAT geometry based on fat_sz_16
        root_cluster = 0
        backup_boot_sector = 0
        fs_version = 0
        vol_label = ""

        if fat_sz_16 != 0:
            # FAT12 or FAT16
            sectors_per_fat = fat_sz_16
            if root_ent_cnt == 0:
                raise CorruptedBootSectorError(
                    "Root directory entry count is 0 on FAT12/16 filesystem"
                )
            # Read volume label if boot signature is present at offset 38
            if data[38] in (0x28, 0x29):
                vol_label = data[43:54].decode("latin-1", errors="replace").strip()
        else:
            # FAT32
            if len(data) < 90:
                raise CorruptedBootSectorError("Sector truncated for FAT32 BPB")
            (fat_sz_32,) = struct.unpack_from("<I", data, 36)
            if fat_sz_32 == 0:
                raise CorruptedBootSectorError("FAT32 sectors per FAT is zero")
            sectors_per_fat = fat_sz_32

            (fs_version,) = struct.unpack_from("<H", data, 42)
            (root_cluster,) = struct.unpack_from("<I", data, 44)
            root_cluster &= 0x0FFFFFFF
            if root_cluster < 2:
                raise CorruptedBootSectorError(
                    f"Invalid FAT32 root cluster: {root_cluster} (must be >= 2)"
                )

            (backup_boot_sector,) = struct.unpack_from("<H", data, 50)

            if data[66] in (0x28, 0x29):
                vol_label = data[71:82].decode("latin-1", errors="replace").strip()

        # Calculate root directory sectors
        root_dir_sectors = ((root_ent_cnt * 32) + (byts_per_sec - 1)) // byts_per_sec

        # Calculate first data sector
        first_data_sector = rsvd_sec_cnt + (num_fats * sectors_per_fat) + root_dir_sectors
        if first_data_sector >= total_sectors:
            raise CorruptedBootSectorError(
                f"Data region start ({first_data_sector}) exceeds total sectors ({total_sectors})"
            )

        data_sectors = total_sectors - first_data_sector
        total_clusters = data_sectors // sec_per_clus

        if total_clusters <= 0:
            raise CorruptedBootSectorError(
                f"Total cluster count is non-positive ({total_clusters})"
            )

        # Official Microsoft FAT type determination based on total clusters
        if total_clusters < 4085:
            fs_type = FileSystemType.FAT12
        elif total_clusters < 65525:
            fs_type = FileSystemType.FAT16
        else:
            fs_type = FileSystemType.FAT32

        return cls(
            bytes_per_sector=byts_per_sec,
            sectors_per_cluster=sec_per_clus,
            reserved_sectors=rsvd_sec_cnt,
            num_fats=num_fats,
            root_entry_count=root_ent_cnt,
            total_sectors=total_sectors,
            media_descriptor=media,
            sectors_per_fat=sectors_per_fat,
            root_cluster=root_cluster,
            backup_boot_sector=backup_boot_sector,
            fs_version=fs_version,
            volume_label=vol_label,
            filesystem_type=fs_type,
            total_clusters=total_clusters,
            cluster_size_bytes=cluster_size,
            root_dir_sectors=root_dir_sectors,
            first_data_sector=first_data_sector,
            base_offset=base_offset,
            is_backup=is_backup,
        )

    @classmethod
    def from_reader(cls, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> "FatBpb":
        """Read sector 0 (and fallback to backup boot sector on FAT32) from block device.

        Args:
            reader: Read-only block device.
            base_offset: Starting byte offset of partition/volume.

        Returns:
            Validated FatBpb.

        Raises:
            CorruptedBootSectorError: If neither primary nor backup boot sectors are valid.
        """
        # 1. Try reading primary boot sector (sector 0)
        try:
            sector_0 = reader.read_at(base_offset, 512)
            return cls.from_bytes(
                sector_0,
                base_offset=base_offset,
                device_size_bytes=reader.size_bytes,
                is_backup=False,
            )
        except CorruptedBootSectorError as primary_err:
            # 2. If primary failed, attempt backup boot sector (sector 6 on FAT32)
            backup_offset = base_offset + (6 * 512)
            if backup_offset + 512 <= reader.size_bytes:
                try:
                    sector_backup = reader.read_at(backup_offset, 512)
                    return cls.from_bytes(
                        sector_backup,
                        base_offset=base_offset,
                        device_size_bytes=reader.size_bytes,
                        is_backup=True,
                    )
                except CorruptedBootSectorError:
                    pass
            # Re-raise primary error if backup also failed
            raise primary_err
