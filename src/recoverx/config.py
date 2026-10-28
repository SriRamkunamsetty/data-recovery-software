"""Configuration module for RecoverX."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CollisionPolicy(StrEnum):
    """File collision policies for recovery destination."""

    RENAME = "rename"
    SKIP = "skip"
    OVERWRITE_NEVER = "never_overwrite"


@dataclass(frozen=True)
class AppConfig:
    """Immutable application settings with safe defaults."""

    # Scanning & Carving limits
    scan_chunk_size_bytes: int = 1024 * 1024  # 1 MiB chunk size
    scan_overlap_bytes: int = 64 * 1024  # 64 KiB chunk overlap
    max_scan_memory_bytes: int = 256 * 1024 * 1024  # 256 MiB memory ceiling

    # Preview limits (untrusted recovered files)
    max_preview_file_size_bytes: int = 20 * 1024 * 1024  # 20 MiB max preview file
    max_preview_image_dimension: int = 4096  # 4096 x 4096 max dimensions
    preview_timeout_seconds: float = 5.0  # Kill preview subprocess after 5 seconds

    # Imaging settings
    default_imaging_block_size_bytes: int = 64 * 1024  # 64 KiB
    max_retries_per_bad_sector: int = 1  # Conservative retry for failing flash
    retry_delay_seconds: float = 0.05

    # Destination policy
    collision_policy: CollisionPolicy = CollisionPolicy.RENAME

    # Base application directory (for sessions, logs)
    work_directory: Path = Path.home() / ".recoverx"

    def __post_init__(self) -> None:
        if self.scan_chunk_size_bytes <= 0:
            raise ValueError("scan_chunk_size_bytes must be positive")
        if self.scan_overlap_bytes < 0:
            raise ValueError("scan_overlap_bytes must be non-negative")
        if self.scan_overlap_bytes >= self.scan_chunk_size_bytes:
            raise ValueError("scan_overlap_bytes must be smaller than scan_chunk_size_bytes")
        if self.max_preview_file_size_bytes <= 0:
            raise ValueError("max_preview_file_size_bytes must be positive")
        if self.preview_timeout_seconds <= 0:
            raise ValueError("preview_timeout_seconds must be positive")
