"""Safe FAT directory traverser with cycle detection, depth limits, and LFN assembly."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

from recoverx.carving.scanner import CancellationToken
from recoverx.domain.enums import FileSystemType
from recoverx.filesystems.fat.bpb import FatBpb
from recoverx.filesystems.fat.entry import FatDirEntry, FatLfnPart, parse_lfn_entry
from recoverx.filesystems.fat.fat_table import FatTableReader
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocatedFatEntry:
    """A FAT directory entry associated with its parent directory path."""

    entry: FatDirEntry
    parent_path: str

    @property
    def full_path(self) -> str:
        """Full relative path of the file or directory."""
        if not self.parent_path:
            return self.entry.display_name
        return f"{self.parent_path}/{self.entry.display_name}"


class FatDirectoryWalker:
    """Traverses FAT directory hierarchies with bounded memory and cycle detection."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        bpb: FatBpb,
        fat_table: FatTableReader,
        max_depth: int = 64,
        max_entries: int = 100_000,
    ) -> None:
        self.reader = reader
        self.bpb = bpb
        self.fat_table = fat_table
        self.max_depth = max_depth
        self.max_entries = max_entries
        self.visited_clusters: set[int] = set()
        self.total_entries_yielded = 0

    def walk_all_entries(
        self, cancellation_token: CancellationToken | None = None
    ) -> Iterator[LocatedFatEntry]:
        """Walk all directory entries (root and subdirectories) starting from the root."""
        self.visited_clusters.clear()
        self.total_entries_yielded = 0

        # 1. Walk Root Directory
        if self.bpb.filesystem_type == FileSystemType.FAT32:
            yield from self._walk_cluster_chain_directory(
                start_cluster=self.bpb.root_cluster,
                parent_path="",
                depth=0,
                cancellation_token=cancellation_token,
            )
        else:
            yield from self._walk_fat12_16_root_directory(
                parent_path="",
                depth=0,
                cancellation_token=cancellation_token,
            )

    def _walk_fat12_16_root_directory(
        self,
        parent_path: str,
        depth: int,
        cancellation_token: CancellationToken | None,
    ) -> Iterator[LocatedFatEntry]:
        """Traverse fixed root directory region for FAT12/FAT16."""
        root_offset = self.bpb.root_dir_offset_bytes
        root_size = self.bpb.root_dir_size_bytes

        try:
            root_bytes = self.reader.read_at(root_offset, root_size)
        except Exception as e:
            logger.warning("Failed to read FAT12/16 root directory: %s", e)
            return

        yield from self._parse_directory_buffer(
            buffer=root_bytes,
            parent_path=parent_path,
            depth=depth,
            cancellation_token=cancellation_token,
        )

    def _walk_cluster_chain_directory(
        self,
        start_cluster: int,
        parent_path: str,
        depth: int,
        cancellation_token: CancellationToken | None,
    ) -> Iterator[LocatedFatEntry]:
        """Traverse a directory represented as a cluster chain (FAT32 root or any subdirectory)."""
        if depth > self.max_depth:
            logger.warning(
                "Directory recursion exceeded max depth %d at %s", self.max_depth, parent_path
            )
            return

        curr_cluster = start_cluster
        subdirs_to_recurse: list[tuple[int, str]] = []

        while self.bpb.is_valid_cluster_num(curr_cluster):
            if cancellation_token and cancellation_token.is_cancelled:
                return

            if curr_cluster in self.visited_clusters:
                logger.warning(
                    "Cycle detected in directory cluster chain (cluster %d already visited)",
                    curr_cluster,
                )
                break
            self.visited_clusters.add(curr_cluster)

            cluster_offset = self.bpb.cluster_to_byte_offset(curr_cluster)
            try:
                cluster_bytes = self.reader.read_at(cluster_offset, self.bpb.cluster_size_bytes)
            except Exception as e:
                logger.warning("Error reading directory cluster %d: %s", curr_cluster, e)
                break

            for located in self._parse_directory_buffer(
                buffer=cluster_bytes,
                parent_path=parent_path,
                depth=depth,
                cancellation_token=cancellation_token,
            ):
                yield located
                if (
                    located.entry.is_directory
                    and not located.entry.is_deleted
                    and self.bpb.is_valid_cluster_num(located.entry.first_cluster)
                ):
                    subdirs_to_recurse.append((located.entry.first_cluster, located.full_path))

            # Move to next cluster in FAT chain
            try:
                next_val = self.fat_table.get_cluster_value(curr_cluster)
            except Exception:
                break

            if self.fat_table.is_end_of_chain(next_val) or next_val == 0:
                break
            curr_cluster = next_val

        # Recurse into discovered subdirectories
        for sub_cluster, sub_path in subdirs_to_recurse:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            yield from self._walk_cluster_chain_directory(
                start_cluster=sub_cluster,
                parent_path=sub_path,
                depth=depth + 1,
                cancellation_token=cancellation_token,
            )

    def _parse_directory_buffer(
        self,
        buffer: bytes,
        parent_path: str,
        depth: int,
        cancellation_token: CancellationToken | None,
    ) -> Iterator[LocatedFatEntry]:
        """Parse raw directory entries from a sector or cluster buffer."""
        lfn_parts: list[FatLfnPart] = []
        subdirs_to_recurse: list[tuple[int, str]] = []

        for offset in range(0, len(buffer), 32):
            if cancellation_token and cancellation_token.is_cancelled:
                return
            if self.total_entries_yielded >= self.max_entries:
                logger.warning("Reached max directory entries limit (%d)", self.max_entries)
                return

            chunk = buffer[offset : offset + 32]
            if len(chunk) < 32:
                break

            first_byte = chunk[0]
            if first_byte == 0x00:
                # 0x00 marks end of active directory entries in this directory
                lfn_parts.clear()
                break

            attr = chunk[11]

            # Check if this is an LFN sub-entry
            if (attr & 0x0F) == 0x0F:
                lfn = parse_lfn_entry(chunk, 0)
                if lfn is not None:
                    lfn_parts.append(lfn)
                continue

            # Standard 8.3 entry
            entry = FatDirEntry.parse_raw(chunk, 0, lfn_parts)
            lfn_parts.clear()

            if entry is None or entry.is_volume_id:
                continue

            # Ignore . and .. directory navigation entries
            clean_short = entry.short_name.strip()
            if clean_short in (".", ".."):
                continue

            located = LocatedFatEntry(entry=entry, parent_path=parent_path)
            self.total_entries_yielded += 1
            yield located

            # If it is a non-deleted subdirectory, schedule recursive walk (for FAT12/16 root)
            if (
                entry.is_directory
                and not entry.is_deleted
                and self.bpb.is_valid_cluster_num(entry.first_cluster)
                and depth == 0
                and self.bpb.filesystem_type != FileSystemType.FAT32
            ):
                subdirs_to_recurse.append((entry.first_cluster, located.full_path))

        # Recurse into FAT12/16 root subdirectories
        for sub_cluster, sub_path in subdirs_to_recurse:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            yield from self._walk_cluster_chain_directory(
                start_cluster=sub_cluster,
                parent_path=sub_path,
                depth=depth + 1,
                cancellation_token=cancellation_token,
            )
