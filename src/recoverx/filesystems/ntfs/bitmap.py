"""NTFS volume cluster allocation bitmap ($Bitmap, MFT record 6) parser."""

from recoverx.filesystems.ntfs.attributes import (
    DataRun,
    NtfsNonResidentAttribute,
    NtfsResidentAttribute,
)
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.filesystems.ntfs.mft import MftReader
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class NtfsBitmap:
    """Manages the NTFS cluster allocation bitmap to verify unallocated space."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        boot_sector: NtfsBootSector,
        mft_reader: MftReader,
    ) -> None:
        self.reader = reader
        self.boot_sector = boot_sector
        self.cluster_size = boot_sector.cluster_size
        self.total_clusters = boot_sector.total_clusters
        self.bitmap_bytes: bytearray = bytearray()

        self._load_bitmap(mft_reader)

    def _load_bitmap(self, mft_reader: MftReader) -> None:
        """Locate and read $Bitmap (MFT Record 6) contents."""
        rec6 = mft_reader.read_record(6)
        if rec6 is None:
            return

        data_attr = rec6.data_attribute
        if data_attr is None:
            return

        if isinstance(data_attr, NtfsResidentAttribute):
            self.bitmap_bytes = bytearray(data_attr.data)
            return

        if isinstance(data_attr, NtfsNonResidentAttribute):
            # Limit maximum cached bitmap size to 32 MiB (covers up to 1 TiB volume @ 4KB clusters)
            max_read = min(data_attr.real_size, 32 * 1024 * 1024)
            bytes_read = 0

            for run in data_attr.data_runs:
                if bytes_read >= max_read:
                    break
                if run.is_sparse:
                    sparse_len = min(run.cluster_count * self.cluster_size, max_read - bytes_read)
                    self.bitmap_bytes.extend(b"\x00" * sparse_len)
                    bytes_read += sparse_len
                else:
                    run_len = min(run.cluster_count * self.cluster_size, max_read - bytes_read)
                    abs_offset = self.boot_sector.lcn_to_byte_offset(run.lcn)
                    try:
                        chunk = self.reader.read_at(abs_offset, run_len)
                        self.bitmap_bytes.extend(chunk)
                        bytes_read += len(chunk)
                    except Exception:
                        break

    def is_cluster_allocated(self, cluster_lcn: int) -> bool:
        """Return True if the cluster is currently allocated (marked in use)."""
        if cluster_lcn < 0 or cluster_lcn >= self.total_clusters:
            return False

        byte_idx = cluster_lcn >> 3
        if byte_idx >= len(self.bitmap_bytes):
            # Outside cached bitmap: assume allocated for safety
            return True

        bit_mask = 1 << (cluster_lcn & 7)
        return bool(self.bitmap_bytes[byte_idx] & bit_mask)

    def check_runs_unallocated(self, runs: list[DataRun]) -> tuple[bool, int]:
        """Verify whether all clusters in the specified runs are unallocated.

        Args:
            runs: List of decoded data runs.

        Returns:
            Tuple of (all_unallocated: bool, first_allocated_lcn: int).
        """
        for run in runs:
            if run.is_sparse:
                continue

            for c in range(run.cluster_count):
                lcn = run.lcn + c
                if self.is_cluster_allocated(lcn):
                    return False, lcn

        return True, -1
