"""NTFS resident and non-resident data stream extractor."""

from recoverx.filesystems.ntfs.attributes import (
    NtfsNonResidentAttribute,
    NtfsResidentAttribute,
)
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.filesystems.ntfs.mft_record import MftRecord
from recoverx.infrastructure.storage.base import (
    DeviceClosedError,
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)


class NtfsDataStreamReader:
    """Reads file content from resident or non-resident NTFS $DATA attributes."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        boot_sector: NtfsBootSector,
    ) -> None:
        self.reader = reader
        self.boot_sector = boot_sector
        self.cluster_size = boot_sector.cluster_size

    def read_stream_bytes(
        self,
        record: MftRecord,
        max_bytes: int = 100 * 1024 * 1024,  # 100 MiB safety cap
    ) -> tuple[bytes, int]:
        """Extract bytes and starting disk offset for an MFT record's primary data stream.

        Args:
            record: Target MFT record.
            max_bytes: Safety cap to prevent memory exhaustion on enormous files.

        Returns:
            Tuple of (file_content_bytes: bytes, starting_disk_offset: int).
        """
        attr = record.data_attribute
        if attr is None:
            return b"", self.boot_sector.base_offset

        # 1. Resident Stream: data is stored directly in the MFT record
        if isinstance(attr, NtfsResidentAttribute):
            val_len = min(attr.value_length, len(attr.data), max_bytes)
            # Offset is the base offset of the volume
            return attr.data[:val_len], self.boot_sector.base_offset

        # 2. Non-Resident Stream: data is allocated across cluster runs
        if isinstance(attr, NtfsNonResidentAttribute):
            target_len = min(attr.real_size, max_bytes)
            if target_len <= 0 or not attr.data_runs:
                first_offset = self.boot_sector.base_offset
                if attr.data_runs and not attr.data_runs[0].is_sparse:
                    first_offset = self.boot_sector.lcn_to_byte_offset(attr.data_runs[0].lcn)
                return b"", first_offset

            first_run = attr.data_runs[0]
            first_offset = (
                self.boot_sector.lcn_to_byte_offset(first_run.lcn)
                if not first_run.is_sparse
                else self.boot_sector.base_offset
            )

            buf = bytearray()
            bytes_left = target_len

            for run in attr.data_runs:
                if bytes_left <= 0:
                    break

                run_total_bytes = run.cluster_count * self.cluster_size
                chunk_to_read = min(bytes_left, run_total_bytes)

                if run.is_sparse:
                    buf.extend(b"\x00" * chunk_to_read)
                    bytes_left -= chunk_to_read
                else:
                    lcn_offset = self.boot_sector.lcn_to_byte_offset(run.lcn)
                    try:
                        read_chunk = self.reader.read_at(lcn_offset, chunk_to_read)
                        buf.extend(read_chunk)
                        bytes_left -= len(read_chunk)
                    except (
                        DeviceReadError,
                        DeviceOutOfBoundsError,
                        DeviceClosedError,
                    ):
                        break

            return bytes(buf), first_offset

        return b"", self.boot_sector.base_offset
