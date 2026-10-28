"""Abstract base classes and common exceptions for filesystem metadata parsers."""

from abc import ABC, abstractmethod

from recoverx.carving.scanner import CancellationToken
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


class FileSystemError(Exception):
    """Base exception for filesystem parsing and metadata extraction errors."""


class CorruptedBootSectorError(FileSystemError):
    """Raised when a boot sector contains invalid signatures or corrupted BPB parameters."""


class CorruptedDirectoryError(FileSystemError):
    """Raised when a directory structure, table, or cluster chain is unparseable."""


class FileSystemParser(ABC):
    """Abstract interface for read-only filesystem metadata parsers."""

    @abstractmethod
    def detect(self, reader: ReadOnlyBlockDevice, base_offset: int = 0) -> bool:
        """Probe if this filesystem exists at the specified base offset.

        Args:
            reader: Read-only block device.
            base_offset: Starting byte offset of the partition/volume.

        Returns:
            True if valid boot parameters and signatures match this filesystem.
        """

    @abstractmethod
    def get_fs_info(
        self, reader: ReadOnlyBlockDevice, base_offset: int = 0
    ) -> FileSystemInfo | None:
        """Extract high-level filesystem geometry and metadata.

        Args:
            reader: Read-only block device.
            base_offset: Starting byte offset of the partition/volume.

        Returns:
            FileSystemInfo domain object or None if not recognized.
        """

    @abstractmethod
    def recover_candidates(
        self,
        reader: ReadOnlyBlockDevice,
        base_offset: int = 0,
        include_active: bool = False,
        cancellation_token: CancellationToken | None = None,
    ) -> list[RecoveryCandidate]:
        """Traverse directory metadata and return candidate files with factual statuses.

        Args:
            reader: Read-only block device.
            base_offset: Starting byte offset of the partition/volume.
            include_active: If True, include active (non-deleted) files in results.
            cancellation_token: Optional token for aborting directory walk.

        Returns:
            List of RecoveryCandidate objects located via filesystem metadata.
        """
