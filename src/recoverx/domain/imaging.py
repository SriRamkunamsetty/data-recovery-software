"""Domain models and specifications for disk acquisition and multi-pass imaging."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class SectorStatus(StrEnum):
    """Sector acquisition status in range map (compatible with forensic ddrescue concepts)."""

    NON_TRIED = "?"
    NON_TRIMMED = "*"
    NON_SCRAPED = "/"
    BAD = "-"
    FINISHED = "+"

    @property
    def human_name(self) -> str:
        return {
            SectorStatus.NON_TRIED: "Not tried",
            SectorStatus.NON_TRIMMED: "Untrimmed",
            SectorStatus.NON_SCRAPED: "Unscraped",
            SectorStatus.BAD: "Bad sector",
            SectorStatus.FINISHED: "Finished",
        }[self]


@dataclass(frozen=True)
class BlockRange:
    """Contiguous sector interval with an associated acquisition status."""

    start_sector: int
    sector_count: int
    status: SectorStatus = SectorStatus.NON_TRIED
    error_message: str = ""

    def __post_init__(self) -> None:
        if self.start_sector < 0:
            raise ValueError(f"start_sector must be non-negative: {self.start_sector}")
        if self.sector_count <= 0:
            raise ValueError(f"sector_count must be positive: {self.sector_count}")

    @property
    def end_sector(self) -> int:
        """Inclusive end sector index."""
        return self.start_sector + self.sector_count - 1

    def start_offset(self, sector_size: int = 512) -> int:
        return self.start_sector * sector_size

    def size_bytes(self, sector_size: int = 512) -> int:
        return self.sector_count * sector_size


@dataclass(frozen=True)
class ImagingConfig:
    """Operational parameters for multi-pass disk imaging."""

    block_size_bytes: int = 64 * 1024  # 64 KiB
    initial_skip_sectors: int = 128  # 64 KiB at 512 bytes/sector
    max_skip_sectors: int = 2048  # 1 MiB at 512 bytes/sector
    max_retries: int = 0  # Conservative 0 retries default for failing flash media
    retry_delay_seconds: float = 0.0
    checkpoint_interval_seconds: float = 2.0
    checkpoint_every_bytes: int = 10 * 1024 * 1024  # 10 MiB
    enable_trim_pass: bool = True
    enable_scrape_pass: bool = True
    compute_sha256: bool = True

    def __post_init__(self) -> None:
        if self.block_size_bytes <= 0:
            raise ValueError(f"block_size_bytes must be positive: {self.block_size_bytes}")
        if self.initial_skip_sectors <= 0:
            raise ValueError(f"initial_skip_sectors must be positive: {self.initial_skip_sectors}")
        if self.max_skip_sectors < self.initial_skip_sectors:
            raise ValueError("max_skip_sectors cannot be less than initial_skip_sectors")
        if self.max_retries < 0:
            raise ValueError(f"max_retries cannot be negative: {self.max_retries}")
        if self.retry_delay_seconds < 0.0:
            raise ValueError(f"retry_delay_seconds cannot be negative: {self.retry_delay_seconds}")


@dataclass(frozen=True)
class ImagingProgress:
    """Live progress snapshot emitted during disk imaging passes."""

    phase: str  # "copy", "trim", "scrape", "checkpoint", "completed", "cancelled"
    bytes_finished: int
    total_bytes: int
    bad_bytes: int
    current_sector: int
    pass_number: int
    elapsed_seconds: float

    @property
    def progress_fraction(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, max(0.0, self.bytes_finished / self.total_bytes))

    @property
    def progress_percent(self) -> float:
        return self.progress_fraction * 100.0


@dataclass(frozen=True)
class ImagingResult:
    """Final outcome of disk acquisition."""

    image_path: Path
    metadata_path: Path
    map_path: Path
    total_sectors: int
    finished_sectors: int
    bad_sectors: int
    is_complete: bool
    sha256_hash: str | None
    elapsed_seconds: float
    notes: list[str] = field(default_factory=list)
