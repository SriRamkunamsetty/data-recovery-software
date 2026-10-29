"""MFT reader, cluster run translation, and record iteration."""

import contextlib
from collections.abc import Iterator

from recoverx.carving.scanner import CancellationToken
from recoverx.filesystems.ntfs.attributes import DataRun, NtfsNonResidentAttribute
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.filesystems.ntfs.mft_record import MftRecord
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)


class MftReader:
    """Reads MFT records from an NTFS volume by resolving $MFT data runs."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        boot_sector: NtfsBootSector,
    ) -> None:
        self.reader = reader
        self.boot_sector = boot_sector
        self.record_size = boot_sector.mft_record_size
        self.cluster_size = boot_sector.cluster_size
        self.mft_data_runs: list[DataRun] = []
        self.total_records = 0

        self._initialize_mft_runs()

    def _initialize_mft_runs(self) -> None:
        """Read Record 0 ($MFT) to extract data runs for the entire Master File Table."""
        mft_offset = self.boot_sector.mft_byte_offset
        record_bytes: bytes | None = None

        with contextlib.suppress(DeviceReadError, DeviceOutOfBoundsError, DeviceClosedError):
            record_bytes = self.reader.read_at(mft_offset, self.record_size)

        # If primary $MFT failed, try $MFTMirr (located at mft_mirr_start_lcn)
        if record_bytes is None:
            try:
                mirr_offset = self.boot_sector.mft_mirr_byte_offset
                record_bytes = self.reader.read_at(mirr_offset, self.record_size)
            except Exception:
                pass

        if record_bytes is not None:
            try:
                rec0 = MftRecord.from_bytes(
                    record_bytes,
                    sector_size=self.boot_sector.bytes_per_sector,
                    record_number=0,
                    max_clusters=self.boot_sector.total_clusters,
                )
                data_attr = rec0.data_attribute
                if isinstance(data_attr, NtfsNonResidentAttribute) and data_attr.data_runs:
                    self.mft_data_runs = list(data_attr.data_runs)
                    if data_attr.real_size > 0:
                        self.total_records = data_attr.real_size // self.record_size
            except Exception:
                pass

        # Fallback if Record 0 had no non-resident runs: assume contiguous run at MFT start
        if not self.mft_data_runs:
            fallback_clusters = max(1, 1024 * self.record_size // self.cluster_size)
            self.mft_data_runs = [
                DataRun(
                    cluster_count=fallback_clusters,
                    lcn=self.boot_sector.mft_start_lcn,
                    is_sparse=False,
                )
            ]
            self.total_records = 1024

    def record_to_byte_offset(self, record_index: int) -> int | None:
        """Translate an MFT record index to an absolute byte offset on the storage device."""
        target_byte = record_index * self.record_size
        curr_stream_byte = 0

        for run in self.mft_data_runs:
            run_bytes = run.cluster_count * self.cluster_size
            if curr_stream_byte <= target_byte < curr_stream_byte + run_bytes:
                if run.is_sparse:
                    return None
                offset_in_run = target_byte - curr_stream_byte
                cluster_in_run = offset_in_run // self.cluster_size
                byte_in_cluster = offset_in_run % self.cluster_size
                lcn = run.lcn + cluster_in_run
                return self.boot_sector.lcn_to_byte_offset(lcn) + byte_in_cluster
            curr_stream_byte += run_bytes

        return None

    def read_record(self, record_index: int) -> MftRecord | None:
        """Read and parse an individual MFT record by index."""
        offset = self.record_to_byte_offset(record_index)
        if offset is None:
            return None

        if offset + self.record_size > self.reader.size_bytes:
            return None

        try:
            raw_bytes = self.reader.read_at(offset, self.record_size)
            return MftRecord.from_bytes(
                raw_bytes,
                sector_size=self.boot_sector.bytes_per_sector,
                record_number=record_index,
                max_clusters=self.boot_sector.total_clusters,
            )
        except Exception:
            return None

    def iter_records(
        self,
        max_records: int | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> Iterator[MftRecord]:
        """Iterate all valid MFT records across the volume."""
        count_limit = (
            self.total_records if max_records is None else min(self.total_records, max_records)
        )
        count_limit = max(1, min(count_limit, 5_000_000))

        for rec_idx in range(count_limit):
            if cancellation_token and cancellation_token.is_cancelled:
                break

            record = self.read_record(rec_idx)
            if record is not None:
                yield record
