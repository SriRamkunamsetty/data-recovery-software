"""NTFS directory path reconstruction and parent reference traversal."""

from recoverx.filesystems.ntfs.mft_record import MftRecord

ROOT_RECORD_INDEX = 5


class NtfsPathResolver:
    """Reconstructs folder hierarchy by resolving parent record references up to Root."""

    def __init__(self) -> None:
        # Maps record_number -> (parent_record_index, folder_name)
        self._dir_map: dict[int, tuple[int, str]] = {}
        self._dir_map[ROOT_RECORD_INDEX] = (ROOT_RECORD_INDEX, "")

    def register_record(self, record: MftRecord) -> None:
        """Register directory metadata for path reconstruction."""
        if not record.is_directory:
            return

        fn = record.best_file_name
        if fn is None:
            return

        name = fn.name
        # Skip self/parent dots
        if name in (".", "..", ""):
            return

        self._dir_map[record.record_number] = (fn.parent_record_index, name)

    def resolve_path(self, record: MftRecord) -> str:
        """Build the full hierarchical relative path for a file record.

        Args:
            record: Target MFT file record.

        Returns:
            Relative path string formatted with forward slashes (e.g. 'Photos/Vacation/pic.jpg').
        """
        fn = record.best_file_name
        filename = fn.name if fn is not None else f"file_{record.record_number}"

        if fn is None:
            return filename

        parts: list[str] = [filename]
        curr_parent = fn.parent_record_index
        visited: set[int] = {record.record_number}
        max_depth = 64

        while curr_parent != ROOT_RECORD_INDEX and len(parts) < max_depth:
            if curr_parent in visited:
                # Cycle detected
                parts.insert(0, f"[Cycle_{curr_parent}]")
                break

            visited.add(curr_parent)

            if curr_parent in self._dir_map:
                next_parent, folder_name = self._dir_map[curr_parent]
                if folder_name:
                    parts.insert(0, folder_name)
                curr_parent = next_parent
            else:
                # Parent directory record is unlinked or lost
                parts.insert(0, f"[LostDir_{curr_parent}]")
                break

        return "/".join(parts)
