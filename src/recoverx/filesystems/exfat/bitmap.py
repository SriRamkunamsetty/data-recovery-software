"""exFAT Allocation Bitmap reader and cluster allocation status evaluator."""

from recoverx.filesystems.exfat.vbr import ExFatVbr
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class ExFatAllocationBitmap:
    """Reads and evaluates cluster allocation bits from the exFAT Allocation Bitmap."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        vbr: ExFatVbr,
        bitmap_first_cluster: int,
        bitmap_length_bytes: int,
    ) -> None:
        self.reader = reader
        self.vbr = vbr
        self.first_cluster = bitmap_first_cluster
        self.length_bytes = bitmap_length_bytes

        # Read the entire bitmap if <= 16 MiB
        self._bitmap_bytes: bytes = b""
        if self.length_bytes <= 16 * 1024 * 1024 and self.vbr.is_valid_cluster_num(
            self.first_cluster
        ):
            try:
                bitmap_offset = self.vbr.cluster_to_byte_offset(self.first_cluster)
                self._bitmap_bytes = self.reader.read_at(bitmap_offset, self.length_bytes)
            except Exception:
                self._bitmap_bytes = b""

    def is_cluster_allocated(self, cluster_num: int) -> bool:
        """Return True if cluster_num is allocated (bit == 1), False if free (bit == 0)."""
        if not self.vbr.is_valid_cluster_num(cluster_num):
            return True  # Out-of-bounds clusters are treated as allocated/unavailable

        bit_index = cluster_num - 2
        byte_index = bit_index // 8
        bit_offset = bit_index % 8

        if byte_index >= len(self._bitmap_bytes):
            # If bitmap was not cached, read the specific byte from disk
            try:
                clus_offset = self.vbr.cluster_to_byte_offset(self.first_cluster)
                byte_val = self.reader.read_at(clus_offset + byte_index, 1)[0]
                return bool((byte_val >> bit_offset) & 1)
            except Exception:
                return True

        return bool((self._bitmap_bytes[byte_index] >> bit_offset) & 1)

    def is_cluster_free(self, cluster_num: int) -> bool:
        """Return True if cluster_num is unallocated/free (bit == 0)."""
        return not self.is_cluster_allocated(cluster_num)

    def check_contiguous_chain(self, first_cluster: int, count: int) -> tuple[bool, list[int]]:
        """Verify that every cluster in [first_cluster, first_cluster + count) is unallocated.

        Returns:
            Tuple of (all_free, allocated_clusters).
        """
        if count <= 0:
            return True, []

        allocated: list[int] = []
        for c in range(first_cluster, first_cluster + count):
            if not self.vbr.is_valid_cluster_num(c) or self.is_cluster_allocated(c):
                allocated.append(c)

        return (len(allocated) == 0, allocated)
