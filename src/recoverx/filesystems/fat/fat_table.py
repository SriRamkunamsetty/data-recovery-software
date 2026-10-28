"""FAT table reader and allocation state evaluator for FAT12, FAT16, and FAT32."""

import struct

from recoverx.domain.enums import FileSystemType
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class FatTableReader:
    """Reads and decodes cluster allocation entries from the on-disk FAT table."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        fat_offset_bytes: int,
        fat_size_bytes: int,
        filesystem_type: FileSystemType,
        total_clusters: int,
    ) -> None:
        self.reader = reader
        self.fat_offset = fat_offset_bytes
        self.fat_size = fat_size_bytes
        self.fs_type = filesystem_type
        self.total_clusters = total_clusters

        # Cache FAT table in memory if it is small (<= 16 MiB)
        self._cached_fat: bytes | None = None
        if self.fat_size <= 16 * 1024 * 1024:
            try:
                self._cached_fat = self.reader.read_at(self.fat_offset, self.fat_size)
            except Exception:
                self._cached_fat = None

    def _read_fat_bytes(self, offset_in_fat: int, length: int) -> bytes:
        """Read bytes from the FAT table either from cache or disk."""
        if self._cached_fat is not None:
            return self._cached_fat[offset_in_fat : offset_in_fat + length]
        return self.reader.read_at(self.fat_offset + offset_in_fat, length)

    def get_cluster_value(self, cluster_num: int) -> int:
        """Retrieve the raw next-cluster pointer or status value for cluster_num.

        Returns 0 for free/unallocated clusters.
        """
        if cluster_num < 2 or cluster_num >= 2 + self.total_clusters:
            raise ValueError(
                f"Cluster {cluster_num} out of valid bounds [2, {2 + self.total_clusters - 1}]"
            )

        if self.fs_type == FileSystemType.FAT12:
            # 12 bits per entry: offset = (cluster * 3) // 2
            offset = (cluster_num * 3) // 2
            raw = self._read_fat_bytes(offset, 2)
            (word,) = struct.unpack("<H", raw)
            if cluster_num % 2 == 0:
                return int(word & 0x0FFF)
            else:
                return int((word >> 4) & 0x0FFF)

        elif self.fs_type == FileSystemType.FAT16:
            # 16 bits per entry: offset = cluster * 2
            offset = cluster_num * 2
            raw = self._read_fat_bytes(offset, 2)
            (word,) = struct.unpack("<H", raw)
            return int(word)

        elif self.fs_type == FileSystemType.FAT32:
            # 32 bits per entry: offset = cluster * 4; lower 28 bits used
            offset = cluster_num * 4
            raw = self._read_fat_bytes(offset, 4)
            (dword,) = struct.unpack("<I", raw)
            return int(dword & 0x0FFFFFFF)

        else:
            raise ValueError(f"Unsupported FAT filesystem type: {self.fs_type}")

    def is_cluster_free(self, cluster_num: int) -> bool:
        """Return True if cluster_num is unallocated (entry == 0)."""
        try:
            return self.get_cluster_value(cluster_num) == 0
        except ValueError:
            return False

    def is_end_of_chain(self, cluster_value: int) -> bool:
        """Return True if cluster_value represents an End-Of-Chain (EOC) marker."""
        if self.fs_type == FileSystemType.FAT12:
            return cluster_value >= 0x0FF8
        elif self.fs_type == FileSystemType.FAT16:
            return cluster_value >= 0xFFF8
        elif self.fs_type == FileSystemType.FAT32:
            return cluster_value >= 0x0FFFFFF8
        return False

    def is_bad_cluster(self, cluster_value: int) -> bool:
        """Return True if cluster_value represents a hardware bad-cluster marker."""
        if self.fs_type == FileSystemType.FAT12:
            return cluster_value == 0x0FF7
        elif self.fs_type == FileSystemType.FAT16:
            return cluster_value == 0xFFF7
        elif self.fs_type == FileSystemType.FAT32:
            return cluster_value == 0x0FFFFFF7
        return False

    def check_contiguous_chain(self, start_cluster: int, count: int) -> tuple[bool, list[int]]:
        """Verify the contiguous-cluster assumption for a deleted file.

        Args:
            start_cluster: First cluster of the deleted file.
            count: Number of clusters needed to store the file.

        Returns:
            Tuple of (all_free, allocated_or_bad_clusters).
            If all_free is True, every cluster in [start_cluster, start_cluster + count)
            is unallocated (0 in the FAT).
        """
        if count <= 0:
            return True, []

        allocated: list[int] = []
        for c in range(start_cluster, start_cluster + count):
            if c < 2 or c >= 2 + self.total_clusters:
                allocated.append(c)
                continue
            val = self.get_cluster_value(c)
            if val != 0:
                allocated.append(c)

        return (len(allocated) == 0, allocated)
