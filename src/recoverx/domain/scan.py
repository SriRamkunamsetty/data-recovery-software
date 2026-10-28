"""Scan, progress, job, and sector status domain models."""

from dataclasses import dataclass

from recoverx.domain.enums import JobStatus


@dataclass(frozen=True)
class BadSectorRange:
    """Represents a contiguous range of sectors with read failures or unverified status."""

    start_sector: int
    sector_count: int
    status: str = "bad"  # "bad", "untrimmed", "unscraped", "error"
    error_message: str = ""
    first_detected_timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.start_sector < 0:
            raise ValueError(f"start_sector must be non-negative: {self.start_sector}")
        if self.sector_count <= 0:
            raise ValueError(f"sector_count must be positive: {self.sector_count}")

    @property
    def end_sector(self) -> int:
        """Inclusive end sector index."""
        return self.start_sector + self.sector_count - 1


@dataclass(frozen=True)
class SectorReadResult:
    """Outcome of reading from a block device at a specific offset."""

    offset: int
    requested_length: int
    data: bytes
    is_bad: bool
    error_message: str | None = None

    def __post_init__(self) -> None:
        if self.offset < 0:
            raise ValueError(f"offset cannot be negative: {self.offset}")
        if self.requested_length < 0:
            raise ValueError(f"requested_length cannot be negative: {self.requested_length}")
        if len(self.data) > self.requested_length:
            raise ValueError(
                f"data length ({len(self.data)}) cannot exceed requested_length "
                f"({self.requested_length})"
            )


@dataclass(frozen=True)
class ScanProgress:
    """Atomic snapshot of scan progress for UI updates and logging."""

    phase: str
    bytes_scanned: int
    total_bytes: int
    elapsed_seconds: float
    candidates_found: int
    bad_sectors_found: int
    current_sector: int
    estimated_remaining_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.bytes_scanned < 0:
            raise ValueError(f"bytes_scanned cannot be negative: {self.bytes_scanned}")
        if self.total_bytes < 0:
            raise ValueError(f"total_bytes cannot be negative: {self.total_bytes}")
        if self.elapsed_seconds < 0.0:
            raise ValueError(f"elapsed_seconds cannot be negative: {self.elapsed_seconds}")
        if self.candidates_found < 0:
            raise ValueError(f"candidates_found cannot be negative: {self.candidates_found}")
        if self.bad_sectors_found < 0:
            raise ValueError(f"bad_sectors_found cannot be negative: {self.bad_sectors_found}")
        if self.current_sector < 0:
            raise ValueError(f"current_sector cannot be negative: {self.current_sector}")

    @property
    def progress_fraction(self) -> float:
        """Normalized progress between 0.0 and 1.0."""
        if self.total_bytes == 0:
            return 0.0
        return min(1.0, max(0.0, self.bytes_scanned / self.total_bytes))

    @property
    def progress_percent(self) -> float:
        """Progress percentage between 0.0% and 100.0%."""
        return self.progress_fraction * 100.0


@dataclass(frozen=True)
class ScanJob:
    """Lifecycle tracking of a scan, imaging, or recovery job."""

    job_id: str
    session_id: str
    source_identifier: str
    scan_type: str  # "quick", "deep", "partition", "imaging"
    created_timestamp: float
    started_timestamp: float | None = None
    completed_timestamp: float | None = None
    status: JobStatus = JobStatus.PENDING
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id cannot be empty")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if self.created_timestamp < 0:
            raise ValueError("created_timestamp cannot be negative")
