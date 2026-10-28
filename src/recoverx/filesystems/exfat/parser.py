"""High-level exFAT metadata recovery parser and candidate extractor."""

import hashlib
from pathlib import Path

from recoverx.carving.registry import SignatureRegistry
from recoverx.carving.scanner import CancellationToken
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, FileSystemType, RecoverySourceMethod
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.filesystems.base import CorruptedBootSectorError, FileSystemParser
from recoverx.filesystems.exfat.bitmap import ExFatAllocationBitmap
from recoverx.filesystems.exfat.directory import ExFatDirectoryWalker
from recoverx.filesystems.exfat.vbr import ExFatVbr
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class ExFatFileSystem(FileSystemParser):
    """Read-only exFAT metadata recovery parser."""

    def __init__(self, registry: SignatureRegistry | None = None) -> None:
        self.registry = registry or SignatureRegistry.default_registry()

    def detect(self, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> bool:
        """Probe if a valid exFAT filesystem exists at base_offset."""
        try:
            ExFatVbr.from_reader(reader, base_offset=base_offset)
            return True
        except (CorruptedBootSectorError, Exception):
            return False

    def get_fs_info(
        self, reader: ReadOnlyBlockDevice, base_offset: int = 0
    ) -> FileSystemInfo | None:
        """Extract exFAT geometry and volume metadata."""
        try:
            vbr = ExFatVbr.from_reader(reader, base_offset=base_offset)
        except CorruptedBootSectorError:
            return None

        # Do a quick scan of root directory to extract volume label
        walker = ExFatDirectoryWalker(reader=reader, vbr=vbr, max_entries=50)
        # Consume first few entries to discover special root records
        for _ in walker.walk_all_entries():
            if walker.special_root.volume_label:
                break

        return FileSystemInfo(
            fs_type=FileSystemType.EXFAT,
            volume_label=walker.special_root.volume_label,
            total_clusters=vbr.cluster_count,
            cluster_size_bytes=vbr.cluster_size_bytes,
            free_clusters=0,
            root_directory_offset_bytes=vbr.cluster_to_byte_offset(vbr.root_cluster),
            is_damaged=False,
        )

    def recover_candidates(
        self,
        reader: ReadOnlyBlockDevice,
        base_offset: int = 0,
        include_active: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[RecoveryCandidate]:
        """Parse entry sets, verify checksums, and evaluate NoFatChain/Allocation Bitmap."""
        vbr = ExFatVbr.from_reader(reader, base_offset=base_offset)
        walker = ExFatDirectoryWalker(reader=reader, vbr=vbr)

        # Collect all located entry sets
        located_entries = list(walker.walk_all_entries(cancellation_token=cancellation_token))

        # Initialize Allocation Bitmap from root directory special structures
        bitmap = ExFatAllocationBitmap(
            reader=reader,
            vbr=vbr,
            bitmap_first_cluster=walker.special_root.bitmap_first_cluster,
            bitmap_length_bytes=walker.special_root.bitmap_length_bytes,
        )

        candidates: list[RecoveryCandidate] = []
        cand_idx = 0

        for located in located_entries:
            if cancellation_token and cancellation_token.is_cancelled:
                break

            entry_set = located.entry_set

            # Skip directory containers
            if entry_set.is_directory:
                continue

            # Skip active files if only deleted requested
            if not include_active and not entry_set.is_deleted:
                continue

            cand_idx += 1
            filename = entry_set.filename
            rel_path = located.full_path
            ext = Path(filename).suffix.lstrip(".").lower()
            file_size = entry_set.file_size
            first_cluster = entry_set.first_cluster

            status: CandidateStatus
            sha256_hash: str | None = None
            source_offset: int

            # 1. Entry-set checksum failure indicates damaged/corrupted metadata
            if not entry_set.is_checksum_valid:
                status = CandidateStatus.CORRUPTED
                source_offset = (
                    vbr.cluster_to_byte_offset(first_cluster)
                    if vbr.is_valid_cluster_num(first_cluster)
                    else vbr.cluster_heap_byte_offset
                )

            elif file_size == 0:
                # 0-byte file
                status = (
                    CandidateStatus.UNALLOCATED
                    if entry_set.is_deleted
                    else CandidateStatus.ALLOCATED
                )
                source_offset = (
                    vbr.cluster_to_byte_offset(first_cluster)
                    if vbr.is_valid_cluster_num(first_cluster)
                    else vbr.cluster_heap_byte_offset
                )
                sha256_hash = hashlib.sha256(b"").hexdigest()

            elif not vbr.is_valid_cluster_num(first_cluster):
                status = CandidateStatus.CORRUPTED
                source_offset = vbr.cluster_heap_byte_offset

            else:
                source_offset = vbr.cluster_to_byte_offset(first_cluster)
                clusters_needed = (file_size + vbr.cluster_size_bytes - 1) // vbr.cluster_size_bytes

                if (first_cluster + clusters_needed - 1) >= (2 + vbr.cluster_count):
                    status = CandidateStatus.CORRUPTED
                elif entry_set.is_deleted:
                    # Check Allocation Bitmap for overwritten clusters
                    all_free, _ = bitmap.check_contiguous_chain(first_cluster, clusters_needed)
                    if not all_free:
                        # Reallocated / overwritten cluster detected!
                        status = CandidateStatus.OVERWRITTEN
                    else:
                        # Clusters are unallocated: attempt read and validate
                        try:
                            content = reader.read_at(source_offset, file_size)
                            validator = self.registry.get_validator_for_extension(ext)
                            if validator is not None:
                                val_result = validator.validate(
                                    reader,
                                    header_offset=source_offset,
                                    max_search_bytes=max(file_size, 4096),
                                )
                                if val_result.status == CandidateStatus.PREVIEW_VALIDATED:
                                    status = CandidateStatus.PREVIEW_VALIDATED
                                    sha256_hash = hashlib.sha256(content).hexdigest()
                                elif val_result.status == CandidateStatus.TRUNCATED:
                                    status = CandidateStatus.TRUNCATED
                                    sha256_hash = hashlib.sha256(content).hexdigest()
                                else:
                                    status = CandidateStatus.CORRUPTED
                            else:
                                status = CandidateStatus.METADATA_RECOVERED
                                sha256_hash = hashlib.sha256(content).hexdigest()
                        except DeviceReadError:
                            status = CandidateStatus.PARTIALLY_READABLE
                        except Exception:
                            status = CandidateStatus.CORRUPTED
                else:
                    # Active file
                    status = CandidateStatus.ALLOCATED
                    try:
                        content = reader.read_at(source_offset, file_size)
                        sha256_hash = hashlib.sha256(content).hexdigest()
                    except Exception:
                        sha256_hash = None

            cand = RecoveryCandidate(
                candidate_id=f"exfat-{vbr.base_offset}-{first_cluster}-{cand_idx:04d}",
                filename=filename,
                relative_path=rel_path,
                extension=ext,
                size_bytes=file_size,
                source_offset=source_offset,
                source_method=RecoverySourceMethod.METADATA,
                status=status,
                sha256_hash=sha256_hash,
            )
            candidates.append(cand)

        return candidates
