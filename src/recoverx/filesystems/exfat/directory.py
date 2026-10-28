"""Safe exFAT directory traversal with cycle detection, depth limits, and entry-set reassembly."""

import logging
import struct
from collections.abc import Iterator
from dataclasses import dataclass

from recoverx.carving.scanner import CancellationToken
from recoverx.filesystems.exfat.entry import ExFatFileEntrySet
from recoverx.filesystems.exfat.vbr import ExFatVbr
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocatedExFatEntry:
    """An exFAT file entry set associated with its parent directory path."""

    entry_set: ExFatFileEntrySet
    parent_path: str

    @property
    def full_path(self) -> str:
        """Full relative path of the file or directory."""
        if not self.parent_path:
            return self.entry_set.filename
        return f"{self.parent_path}/{self.entry_set.filename}"


@dataclass(slots=True)
class ExFatSpecialRootEntries:
    """Special system structures discovered in the root directory."""

    volume_label: str = ""
    bitmap_first_cluster: int = 0
    bitmap_length_bytes: int = 0
    upcase_first_cluster: int = 0
    upcase_length_bytes: int = 0


class ExFatDirectoryWalker:
    """Traverses exFAT directory hierarchies safely with cycle detection and depth limits."""

    def __init__(
        self,
        reader: ReadOnlyBlockDevice,
        vbr: ExFatVbr,
        max_depth: int = 64,
        max_entries: int = 100_000,
    ) -> None:
        self.reader = reader
        self.vbr = vbr
        self.max_depth = max_depth
        self.max_entries = max_entries
        self.visited_clusters: set[int] = set()
        self.special_root = ExFatSpecialRootEntries()
        self.total_entries_yielded = 0

    def walk_all_entries(
        self, cancellation_token: CancellationToken | None = None
    ) -> Iterator[LocatedExFatEntry]:
        """Walk root and subdirectories starting from vbr.root_cluster."""
        self.visited_clusters.clear()
        self.total_entries_yielded = 0

        yield from self._walk_directory_cluster_chain(
            start_cluster=self.vbr.root_cluster,
            parent_path="",
            depth=0,
            is_root=True,
            cancellation_token=cancellation_token,
        )

    def _walk_directory_cluster_chain(
        self,
        start_cluster: int,
        parent_path: str,
        depth: int,
        is_root: bool,
        cancellation_token: CancellationToken | None,
    ) -> Iterator[LocatedExFatEntry]:
        """Traverse a directory represented as a cluster chain."""
        if depth > self.max_depth:
            logger.warning(
                "exFAT directory recursion exceeded max depth %d at %s", self.max_depth, parent_path
            )
            return

        curr_cluster = start_cluster
        subdirs_to_recurse: list[tuple[int, str]] = []

        while self.vbr.is_valid_cluster_num(curr_cluster):
            if cancellation_token and cancellation_token.is_cancelled:
                return

            if curr_cluster in self.visited_clusters:
                logger.warning(
                    "Cycle detected in exFAT directory cluster chain at cluster %d",
                    curr_cluster,
                )
                break
            self.visited_clusters.add(curr_cluster)

            cluster_offset = self.vbr.cluster_to_byte_offset(curr_cluster)
            try:
                cluster_bytes = self.reader.read_at(cluster_offset, self.vbr.cluster_size_bytes)
            except Exception as e:
                logger.warning("Error reading exFAT directory cluster %d: %s", curr_cluster, e)
                break

            offset = 0
            buf_len = len(cluster_bytes)

            while offset + 32 <= buf_len:
                if cancellation_token and cancellation_token.is_cancelled:
                    return
                if self.total_entries_yielded >= self.max_entries:
                    return

                entry_chunk = cluster_bytes[offset : offset + 32]
                entry_type = entry_chunk[0]

                # 0x00 marks end of directory entries
                if entry_type == 0x00:
                    break

                # 1. Allocation Bitmap Entry (0x81)
                if entry_type == 0x81 and is_root:
                    (first_c,) = struct.unpack_from("<I", entry_chunk, 20)
                    (d_len,) = struct.unpack_from("<Q", entry_chunk, 24)
                    self.special_root.bitmap_first_cluster = first_c
                    self.special_root.bitmap_length_bytes = d_len
                    offset += 32
                    continue

                # 2. Up-case Table Entry (0x82)
                if entry_type == 0x82 and is_root:
                    (first_c,) = struct.unpack_from("<I", entry_chunk, 20)
                    (d_len,) = struct.unpack_from("<Q", entry_chunk, 24)
                    self.special_root.upcase_first_cluster = first_c
                    self.special_root.upcase_length_bytes = d_len
                    offset += 32
                    continue

                # 3. Volume Label Entry (0x83)
                if entry_type == 0x83 and is_root:
                    char_count = entry_chunk[1]
                    if char_count > 0:
                        raw_label = entry_chunk[2 : 2 + (char_count * 2)]
                        self.special_root.volume_label = raw_label.decode(
                            "utf-16-le", errors="replace"
                        )
                    offset += 32
                    continue

                # 4. File Entry Set (0x85 active or 0x05 deleted)
                if entry_type in (0x85, 0x05):
                    secondary_count = entry_chunk[1]
                    total_set_entries = 1 + secondary_count
                    set_bytes_len = total_set_entries * 32

                    # Check if entry set fits in current cluster buffer
                    if offset + set_bytes_len <= buf_len:
                        set_entries = [
                            cluster_bytes[offset + (i * 32) : offset + ((i + 1) * 32)]
                            for i in range(total_set_entries)
                        ]
                        parsed_set = ExFatFileEntrySet.parse_from_entries(set_entries)
                        if parsed_set is not None:
                            located = LocatedExFatEntry(
                                entry_set=parsed_set, parent_path=parent_path
                            )
                            self.total_entries_yielded += 1
                            yield located

                            if (
                                parsed_set.is_directory
                                and not parsed_set.is_deleted
                                and self.vbr.is_valid_cluster_num(parsed_set.first_cluster)
                            ):
                                subdirs_to_recurse.append(
                                    (parsed_set.first_cluster, located.full_path)
                                )

                        offset += set_bytes_len
                        continue
                    else:
                        offset += 32
                        continue

                # Skip unhandled entry
                offset += 32

            # In exFAT, read FAT table for next cluster pointer
            try:
                fat_entry_off = self.vbr.fat_byte_offset + (curr_cluster * 4)
                raw_next = self.reader.read_at(fat_entry_off, 4)
                (next_cluster,) = struct.unpack("<I", raw_next)
            except Exception:
                break

            if next_cluster >= 0xFFFFFFF8 or next_cluster < 2:
                break
            curr_cluster = next_cluster

        # Recurse into discovered subdirectories
        for sub_cluster, sub_path in subdirs_to_recurse:
            if cancellation_token and cancellation_token.is_cancelled:
                return
            yield from self._walk_directory_cluster_chain(
                start_cluster=sub_cluster,
                parent_path=sub_path,
                depth=depth + 1,
                is_root=False,
                cancellation_token=cancellation_token,
            )
