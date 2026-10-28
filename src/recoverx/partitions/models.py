"""Partition and lost volume domain models and enumerations."""

from dataclasses import dataclass, field
from enum import StrEnum

from recoverx.domain.enums import FileSystemType
from recoverx.domain.partition import PartitionInfo


class PartitionTableType(StrEnum):
    """Detected partition table scheme."""

    MBR = "MBR"
    GPT = "GPT"
    NONE = "None (Raw/Unpartitioned)"


class GptHeaderHealth(StrEnum):
    """Health comparison between Primary and Backup (Secondary) GPT headers."""

    BOTH_VALID = "Both primary and backup valid"
    PRIMARY_VALID_BACKUP_CORRUPT = "Primary valid, backup corrupt"
    BACKUP_VALID_PRIMARY_CORRUPT = "Backup valid, primary corrupt"
    BOTH_CORRUPT = "Both primary and backup corrupt"
    NOT_FOUND = "GPT header not found"


@dataclass(frozen=True)
class VolumeCandidate:
    """Candidate volume discovered via partition table or boot-sector signature sweep."""

    start_sector: int
    sector_count: int
    sector_size: int = 512
    filesystem_type: FileSystemType = FileSystemType.UNKNOWN
    detection_source: str = ""
    label: str = ""
    evidence: str = ""
    is_backup_structure: bool = False

    def __post_init__(self) -> None:
        if self.start_sector < 0:
            raise ValueError(f"start_sector must be non-negative: {self.start_sector}")
        if self.sector_count < 0:
            raise ValueError(f"sector_count must be non-negative: {self.sector_count}")
        if self.sector_size <= 0 or (self.sector_size & (self.sector_size - 1)) != 0:
            raise ValueError(f"sector_size must be a power of two: {self.sector_size}")

    @property
    def start_offset_bytes(self) -> int:
        """Starting byte offset on the physical block device."""
        return self.start_sector * self.sector_size

    @property
    def size_bytes(self) -> int:
        """Total size of the candidate volume in bytes."""
        return self.sector_count * self.sector_size

    @property
    def end_sector(self) -> int:
        """Last inclusive sector of this volume."""
        if self.sector_count == 0:
            return self.start_sector
        return self.start_sector + self.sector_count - 1


@dataclass(frozen=True)
class PartitionAnalysisResult:
    """Comprehensive analysis of partition tables and discovered candidate volumes."""

    table_type: PartitionTableType
    partitions: list[PartitionInfo] = field(default_factory=list)
    volume_candidates: list[VolumeCandidate] = field(default_factory=list)
    gpt_health: GptHeaderHealth | None = None
    disk_signature_or_guid: str = ""
    notes: list[str] = field(default_factory=list)
