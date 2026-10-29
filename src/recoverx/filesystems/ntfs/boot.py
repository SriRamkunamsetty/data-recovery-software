"""NTFS Volume Boot Record (boot sector) parser and validation."""

import struct
from dataclasses import dataclass

from recoverx.filesystems.base import CorruptedBootSectorError
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)

NTFS_OEM_ID = b"NTFS    "
BOOT_SIG = b"\x55\xaa"


@dataclass(frozen=True)
class NtfsBootSector:
    """Parsed NTFS Volume Boot Record parameters."""

    oem_id: bytes
    bytes_per_sector: int
    sectors_per_cluster: int
    total_sectors: int
    mft_start_lcn: int
    mft_mirr_start_lcn: int
    clusters_per_mft_record: int
    clusters_per_index_record: int
    volume_serial_number: int
    base_offset: int = 0
    is_backup: bool = False

    @property
    def cluster_size(self) -> int:
        """Size of one cluster in bytes."""
        return self.bytes_per_sector * self.sectors_per_cluster

    @property
    def total_clusters(self) -> int:
        """Total clusters in volume."""
        if self.cluster_size <= 0:
            return 0
        return self.volume_size_bytes // self.cluster_size

    @property
    def volume_size_bytes(self) -> int:
        """Total volume size in bytes."""
        return self.total_sectors * self.bytes_per_sector

    @property
    def mft_record_size(self) -> int:
        """Size of an MFT record in bytes (typically 1024 bytes)."""
        if self.clusters_per_mft_record > 0:
            return self.clusters_per_mft_record * self.cluster_size
        # Negative value indicates power of two: 2**(-clusters_per_mft_record)
        return 1 << (-self.clusters_per_mft_record)

    @property
    def index_record_size(self) -> int:
        """Size of an index allocation block in bytes (typically 4096 bytes)."""
        if self.clusters_per_index_record > 0:
            return self.clusters_per_index_record * self.cluster_size
        return 1 << (-self.clusters_per_index_record)

    @property
    def mft_byte_offset(self) -> int:
        """Absolute byte offset of the primary $MFT start."""
        return self.lcn_to_byte_offset(self.mft_start_lcn)

    @property
    def mft_mirr_byte_offset(self) -> int:
        """Absolute byte offset of the backup $MFTMirr start."""
        return self.lcn_to_byte_offset(self.mft_mirr_start_lcn)

    def lcn_to_byte_offset(self, lcn: int) -> int:
        """Translate a Logical Cluster Number (LCN) to an absolute byte offset."""
        return self.base_offset + (lcn * self.cluster_size)

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        base_offset: int = 0,
        is_backup: bool = False,
    ) -> "NtfsBootSector":
        """Parse and validate a 512-byte NTFS boot sector.

        Args:
            data: At least 512 bytes of raw sector data.
            base_offset: Byte offset where volume starts on the underlying device.
            is_backup: True if this boot sector was read from the backup location.

        Returns:
            Validated NtfsBootSector instance.

        Raises:
            CorruptedBootSectorError: If magic, sizes, or signatures are invalid.
        """
        if len(data) < 512:
            raise CorruptedBootSectorError(
                f"Boot sector data too short ({len(data)} bytes, expected 512)"
            )

        oem_id = data[3:11]
        if oem_id != NTFS_OEM_ID:
            raise CorruptedBootSectorError(f"Invalid NTFS OEM ID: {oem_id!r}")

        sig = data[510:512]
        if sig != BOOT_SIG:
            raise CorruptedBootSectorError(
                f"Invalid boot sector signature: {sig.hex()}, expected 55aa"
            )

        bytes_per_sec = struct.unpack_from("<H", data, 11)[0]
        if bytes_per_sec not in (512, 1024, 2048, 4096):
            raise CorruptedBootSectorError(
                f"Unsupported bytes per sector in NTFS boot sector: {bytes_per_sec}"
            )

        sec_per_cluster = data[13]
        if sec_per_cluster not in (1, 2, 4, 8, 16, 32, 64, 128):
            raise CorruptedBootSectorError(
                f"Invalid sectors per cluster in NTFS boot sector: {sec_per_cluster}"
            )

        total_sectors = struct.unpack_from("<Q", data, 40)[0]
        if total_sectors <= 0:
            raise CorruptedBootSectorError(
                f"Invalid total sectors in NTFS boot sector: {total_sectors}"
            )

        mft_start_lcn = struct.unpack_from("<Q", data, 48)[0]
        mft_mirr_start_lcn = struct.unpack_from("<Q", data, 56)[0]

        clusters_per_mft = struct.unpack_from("<b", data, 64)[0]
        clusters_per_idx = struct.unpack_from("<b", data, 68)[0]
        vol_serial = struct.unpack_from("<Q", data, 72)[0]

        return cls(
            oem_id=oem_id,
            bytes_per_sector=bytes_per_sec,
            sectors_per_cluster=sec_per_cluster,
            total_sectors=total_sectors,
            mft_start_lcn=mft_start_lcn,
            mft_mirr_start_lcn=mft_mirr_start_lcn,
            clusters_per_mft_record=clusters_per_mft,
            clusters_per_index_record=clusters_per_idx,
            volume_serial_number=vol_serial,
            base_offset=base_offset,
            is_backup=is_backup,
        )

    @classmethod
    def from_reader(
        cls,
        reader: ReadOnlyBlockDevice,
        base_offset: int = 0,
    ) -> "NtfsBootSector":
        """Read and parse NTFS boot sector with automatic backup fallback.

        In NTFS, the primary boot sector is at sector 0 of the volume. A backup
        copy is stored at the very last sector of the volume.

        Args:
            reader: Read-only block device.
            base_offset: Partition start offset in bytes.

        Returns:
            Validated NtfsBootSector instance.

        Raises:
            CorruptedBootSectorError: If neither primary nor backup boot sector is valid.
        """
        primary_err: Exception | None = None
        try:
            primary_data = reader.read_at(base_offset, 512)
            return cls.from_bytes(primary_data, base_offset=base_offset, is_backup=False)
        except (
            CorruptedBootSectorError,
            DeviceReadError,
            DeviceOutOfBoundsError,
            DeviceClosedError,
        ) as exc:
            primary_err = exc

        # Try backup boot sector at the end of the device/partition
        # Typically located at base_offset + reader.size_bytes - 512
        try:
            backup_offset = base_offset + reader.size_bytes - 512
            if backup_offset > base_offset:
                backup_data = reader.read_at(backup_offset, 512)
                return cls.from_bytes(backup_data, base_offset=base_offset, is_backup=True)
        except Exception:
            pass

        raise CorruptedBootSectorError(
            f"Failed to read valid NTFS boot sector at offset {base_offset}: {primary_err}"
        )
