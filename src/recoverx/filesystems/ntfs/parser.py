"""NTFS filesystem parser, MFT metadata extraction, and deleted file candidate recovery."""

import hashlib
from pathlib import Path
from typing import Any

from recoverx.carving.registry import SignatureRegistry
from recoverx.carving.scanner import CancellationToken
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, FileSystemType, RecoverySourceMethod
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.filesystems.base import CorruptedBootSectorError, FileSystemParser
from recoverx.filesystems.ntfs.attributes import (
    AttributeType,
    NtfsNonResidentAttribute,
    NtfsResidentAttribute,
)
from recoverx.filesystems.ntfs.bitmap import NtfsBitmap
from recoverx.filesystems.ntfs.boot import NtfsBootSector
from recoverx.filesystems.ntfs.data_recovery import NtfsDataStreamReader
from recoverx.filesystems.ntfs.directory import NtfsPathResolver
from recoverx.filesystems.ntfs.mft import MftReader
from recoverx.filesystems.ntfs.mft_record import MftRecord
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class NtfsFileSystem(FileSystemParser):
    """Read-only NTFS metadata parser and candidate recovery engine."""

    def __init__(self, registry: SignatureRegistry | None = None) -> None:
        self.registry = registry or SignatureRegistry.default_registry()

    def detect(self, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> bool:
        """Probe if a valid NTFS boot sector exists at the specified base offset."""
        try:
            boot = NtfsBootSector.from_reader(reader, base_offset=base_offset)
            return boot.oem_id == b"NTFS    "
        except (CorruptedBootSectorError, Exception):
            return False

    def get_fs_info(
        self, reader: ReadOnlyBlockDevice, base_offset: int = 0
    ) -> FileSystemInfo | None:
        """Extract high-level geometry and volume metadata from the NTFS boot sector."""
        try:
            boot = NtfsBootSector.from_reader(reader, base_offset=base_offset)
        except Exception:
            return None

        # Attempt to extract volume label from $Volume (MFT record 3)
        volume_label: str | None = None
        try:
            mft_reader = MftReader(reader, boot)
            rec3 = mft_reader.read_record(3)
            if rec3 is not None:
                for attr in rec3.attributes:
                    if (
                        attr.attr_type == AttributeType.VOLUME_NAME
                        and isinstance(attr, NtfsResidentAttribute)
                        and attr.data
                    ):
                        volume_label = attr.data.decode("utf-16le", errors="replace")
                        break
        except Exception:
            pass

        return FileSystemInfo(
            fs_type=FileSystemType.NTFS,
            volume_label=volume_label or "",
            total_clusters=boot.total_clusters,
            cluster_size_bytes=boot.cluster_size,
            free_clusters=0,
            root_directory_offset_bytes=boot.mft_byte_offset,
            is_damaged=boot.is_backup,
        )

    def recover_candidates(
        self,
        reader: ReadOnlyBlockDevice,
        base_offset: int = 0,
        include_active: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[RecoveryCandidate]:
        """Traverse MFT records and return candidate files with factual statuses.

        Args:
            reader: Read-only block device.
            base_offset: Partition start offset in bytes.
            include_active: If True, include allocated/active files in addition to deleted.
            cancellation_token: Optional cancellation token.

        Returns:
            List of RecoveryCandidate objects with honest factual statuses.
        """
        boot = NtfsBootSector.from_reader(reader, base_offset=base_offset)
        mft_reader = MftReader(reader, boot)
        bitmap = NtfsBitmap(reader, boot, mft_reader)
        path_resolver = NtfsPathResolver()
        stream_reader = NtfsDataStreamReader(reader, boot)

        # First pass: collect all records and register directory paths
        all_records: list[MftRecord] = []
        for record in mft_reader.iter_records(cancellation_token=cancellation_token):
            if cancellation_token and cancellation_token.is_cancelled:
                break
            all_records.append(record)
            if record.is_directory:
                path_resolver.register_record(record)

        candidates: list[RecoveryCandidate] = []
        cand_idx = 0

        for record in all_records:
            if cancellation_token and cancellation_token.is_cancelled:
                break

            # Skip directory containers
            if record.is_directory:
                continue

            # Skip active system files (records 0-15) unless explicitly asked
            if record.record_number < 16 and not include_active:
                continue

            # Filter active vs deleted
            if not include_active and not record.is_deleted:
                continue

            fn = record.best_file_name
            filename = fn.name if fn is not None else f"file_{record.record_number}"
            # Skip hidden system references with empty names
            if not filename or filename in (".", ".."):
                continue

            cand_idx += 1
            rel_path = path_resolver.resolve_path(record)
            ext = Path(filename).suffix.lstrip(".").lower()
            file_size = record.data_size

            status: CandidateStatus
            sha256_hash: str | None = None
            source_offset: int

            data_attr = record.data_attribute

            # 1. Zero-byte files
            if file_size == 0 or data_attr is None:
                status = (
                    CandidateStatus.UNALLOCATED if record.is_deleted else CandidateStatus.ALLOCATED
                )
                source_offset = boot.base_offset
                sha256_hash = hashlib.sha256(b"").hexdigest()

            # 2. Resident files: data is stored directly in the MFT record
            elif isinstance(data_attr, NtfsResidentAttribute):
                content, source_offset = stream_reader.read_stream_bytes(record)
                sha256_hash = hashlib.sha256(content).hexdigest()

                if record.is_deleted:
                    # In-MFT resident file deleted: content was preserved intact
                    validator = self.registry.get_validator_for_extension(ext)
                    if validator is not None:
                        # Validate with in-memory reader or synthetic buffer
                        val_res = self._validate_content_buffer(content, ext, validator)
                        status = val_res
                    else:
                        status = CandidateStatus.METADATA_RECOVERED
                else:
                    status = CandidateStatus.ALLOCATED

            # 3. Non-resident files: data is allocated across clusters
            elif isinstance(data_attr, NtfsNonResidentAttribute):
                if not data_attr.data_runs:
                    status = CandidateStatus.CORRUPTED
                    source_offset = boot.base_offset
                else:
                    first_run = data_attr.data_runs[0]
                    source_offset = (
                        boot.lcn_to_byte_offset(first_run.lcn)
                        if not first_run.is_sparse
                        else boot.base_offset
                    )

                    if record.is_deleted:
                        # Check $Bitmap: have these clusters been reallocated/overwritten?
                        all_unallocated, _ = bitmap.check_runs_unallocated(data_attr.data_runs)
                        if not all_unallocated:
                            status = CandidateStatus.OVERWRITTEN
                        else:
                            content, _ = stream_reader.read_stream_bytes(record)
                            sha256_hash = hashlib.sha256(content).hexdigest()

                            validator = self.registry.get_validator_for_extension(ext)
                            if validator is not None:
                                status = self._validate_content_buffer(content, ext, validator)
                            else:
                                status = CandidateStatus.METADATA_RECOVERED
                    else:
                        status = CandidateStatus.ALLOCATED
                        try:
                            content, _ = stream_reader.read_stream_bytes(record)
                            sha256_hash = hashlib.sha256(content).hexdigest()
                        except Exception:
                            sha256_hash = None
            else:
                status = CandidateStatus.CORRUPTED
                source_offset = boot.base_offset

            candidates.append(
                RecoveryCandidate(
                    candidate_id=f"ntfs_{record.record_number}_{cand_idx}",
                    filename=filename,
                    relative_path=rel_path,
                    extension=ext,
                    size_bytes=file_size,
                    source_offset=source_offset,
                    source_method=RecoverySourceMethod.METADATA,
                    status=status,
                    sha256_hash=sha256_hash,
                    notes=f"NTFS MFT record {record.record_number}",
                )
            )

        return candidates

    def _validate_content_buffer(
        self,
        content: bytes,
        extension: str,
        validator: Any,
    ) -> CandidateStatus:
        """Validate carved buffer using a temporary in-memory block device."""
        if not content:
            return CandidateStatus.METADATA_RECOVERED

        from recoverx.infrastructure.storage.memory import MemoryBlockDevice

        temp_dev = MemoryBlockDevice(data=content)
        try:
            val_res = validator.validate(temp_dev, header_offset=0, max_search_bytes=len(content))
            if val_res.status == CandidateStatus.PREVIEW_VALIDATED:
                return CandidateStatus.PREVIEW_VALIDATED
            if val_res.status == CandidateStatus.TRUNCATED:
                return CandidateStatus.TRUNCATED
            return CandidateStatus.CORRUPTED
        except Exception:
            return CandidateStatus.CORRUPTED
        finally:
            temp_dev.close()
