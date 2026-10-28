"""High-level FAT12/16/32 filesystem metadata recovery parser."""

import hashlib
from pathlib import Path

from recoverx.carving.registry import SignatureRegistry
from recoverx.carving.scanner import CancellationToken
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.filesystems.base import CorruptedBootSectorError, FileSystemParser
from recoverx.filesystems.fat.bpb import FatBpb
from recoverx.filesystems.fat.directory import FatDirectoryWalker
from recoverx.filesystems.fat.fat_table import FatTableReader
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class FatFileSystem(FileSystemParser):
    """Read-only metadata parser and recovery engine for FAT12, FAT16, and FAT32 volumes."""

    def __init__(self, registry: SignatureRegistry | None = None) -> None:
        self.registry = registry or SignatureRegistry.default_registry()

    def detect(self, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> bool:
        """Probe if a valid FAT filesystem exists at base_offset."""
        try:
            FatBpb.from_reader(reader, base_offset=base_offset)
            return True
        except (CorruptedBootSectorError, Exception):
            return False

    def get_fs_info(
        self, reader: ReadOnlyBlockDevice, base_offset: int = 0
    ) -> FileSystemInfo | None:
        """Extract filesystem metadata and cluster parameters."""
        try:
            bpb = FatBpb.from_reader(reader, base_offset=base_offset)
        except CorruptedBootSectorError:
            return None

        return FileSystemInfo(
            fs_type=bpb.filesystem_type,
            volume_label=bpb.volume_label,
            total_clusters=bpb.total_clusters,
            cluster_size_bytes=bpb.cluster_size_bytes,
            free_clusters=0,
            root_directory_offset_bytes=bpb.root_dir_offset_bytes,
            is_damaged=False,
        )

    def recover_candidates(
        self,
        reader: ReadOnlyBlockDevice,
        base_offset: int = 0,
        include_active: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[RecoveryCandidate]:
        """Parse directory structures and recover files with factual status verification.

        For deleted files, evaluates the contiguous-cluster chain against the FAT allocation
        table. Overwritten clusters are detected and reported rather than recovered.
        """
        bpb = FatBpb.from_reader(reader, base_offset=base_offset)
        fat_offset = bpb.fat_offset_bytes(0)
        fat_size = bpb.sectors_per_fat * bpb.bytes_per_sector

        fat_table = FatTableReader(
            reader=reader,
            fat_offset_bytes=fat_offset,
            fat_size_bytes=fat_size,
            filesystem_type=bpb.filesystem_type,
            total_clusters=bpb.total_clusters,
        )

        walker = FatDirectoryWalker(
            reader=reader,
            bpb=bpb,
            fat_table=fat_table,
        )

        candidates: list[RecoveryCandidate] = []
        cand_idx = 0

        for located in walker.walk_all_entries(cancellation_token=cancellation_token):
            if cancellation_token and cancellation_token.is_cancelled:
                break

            entry = located.entry

            # Skip directory structures (directories are container hierarchies,
            # not carved payload files)
            if entry.is_directory:
                continue

            # Skip active files if only recovering deleted files
            if not include_active and not entry.is_deleted:
                continue

            cand_idx += 1
            filename = entry.display_name
            rel_path = located.full_path
            ext = Path(filename).suffix.lstrip(".").lower()
            file_size = entry.file_size
            first_cluster = entry.first_cluster

            # Default attributes
            status: CandidateStatus
            sha256_hash: str | None = None
            source_offset: int

            if file_size == 0:
                # 0-byte file
                status = (
                    CandidateStatus.UNALLOCATED if entry.is_deleted else CandidateStatus.ALLOCATED
                )
                source_offset = (
                    bpb.cluster_to_byte_offset(first_cluster)
                    if bpb.is_valid_cluster_num(first_cluster)
                    else bpb.first_data_byte_offset
                )
                sha256_hash = hashlib.sha256(b"").hexdigest()

            elif first_cluster < 2 or not bpb.is_valid_cluster_num(first_cluster):
                # Invalid first cluster for non-zero file
                status = CandidateStatus.CORRUPTED
                source_offset = bpb.first_data_byte_offset

            else:
                source_offset = bpb.cluster_to_byte_offset(first_cluster)
                clusters_needed = (file_size + bpb.cluster_size_bytes - 1) // bpb.cluster_size_bytes

                # Verify cluster range does not overflow total volume clusters
                if (first_cluster + clusters_needed - 1) >= (2 + bpb.total_clusters):
                    status = CandidateStatus.CORRUPTED
                elif entry.is_deleted:
                    # Contiguous chain allocation check
                    all_free, _ = fat_table.check_contiguous_chain(first_cluster, clusters_needed)
                    if not all_free:
                        # Overwritten clusters detected! Report rather than recovering
                        status = CandidateStatus.OVERWRITTEN
                    else:
                        # Clusters are unallocated: attempt read and structural validation
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
                                # No format validator exists for this file type
                                status = CandidateStatus.METADATA_RECOVERED
                                sha256_hash = hashlib.sha256(content).hexdigest()

                        except DeviceReadError:
                            status = CandidateStatus.PARTIALLY_READABLE
                        except Exception:
                            status = CandidateStatus.CORRUPTED
                else:
                    # Active allocated file
                    status = CandidateStatus.ALLOCATED
                    try:
                        content = reader.read_at(source_offset, file_size)
                        sha256_hash = hashlib.sha256(content).hexdigest()
                    except Exception:
                        sha256_hash = None

            cand = RecoveryCandidate(
                candidate_id=f"fat-{bpb.base_offset}-{first_cluster}-{cand_idx:04d}",
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
