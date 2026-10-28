"""Base interfaces and data structures for file format validators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of structural validation of a candidate file."""

    status: CandidateStatus
    size_bytes: int
    extension: str
    sha256: str | None = None
    notes: str = ""
    # Relative byte ranges within this file that are embedded sub-objects (e.g. EXIF thumbnails)
    inner_ranges_to_skip: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes cannot be negative: {self.size_bytes}")
        if not isinstance(self.status, CandidateStatus):
            raise TypeError(f"status must be a CandidateStatus enum, got {type(self.status)}")


class FormatValidator(ABC):
    """Abstract structural validator for a file format."""

    @property
    @abstractmethod
    def format_name(self) -> str:
        """Name of the format (e.g., 'JPEG', 'PNG', 'PDF', 'ZIP')."""

    @property
    @abstractmethod
    def default_extension(self) -> str:
        """Default file extension without dot (e.g., 'jpg', 'png')."""

    @property
    @abstractmethod
    def magic_bytes(self) -> bytes:
        """Initial signature bytes identifying candidate start."""

    @abstractmethod
    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 100 * 1024 * 1024,
    ) -> ValidationResult:
        """Walk the file structure on the block device starting at `header_offset`.

        Must never read beyond `device.size_bytes` or `header_offset + max_search_bytes`.
        Must handle truncated or malformed inputs safely without crashing or hanging.
        """
