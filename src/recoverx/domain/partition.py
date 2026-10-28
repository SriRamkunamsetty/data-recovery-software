"""Partition metadata domain models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PartitionInfo:
    """Information regarding a recognized or candidate partition."""

    partition_number: int
    start_sector: int
    sector_count: int
    sector_size: int = 512
    partition_type_or_guid: str = ""
    name: str = ""
    is_bootable: bool = False

    def __post_init__(self) -> None:
        if self.partition_number < 0:
            raise ValueError(f"partition_number must be non-negative: {self.partition_number}")
        if self.start_sector < 0:
            raise ValueError(f"start_sector must be non-negative: {self.start_sector}")
        if self.sector_count < 0:
            raise ValueError(f"sector_count must be non-negative: {self.sector_count}")
        if self.sector_size <= 0 or (self.sector_size & (self.sector_size - 1)) != 0:
            raise ValueError(f"sector_size must be a power of two: {self.sector_size}")

    @property
    def start_offset_bytes(self) -> int:
        """Starting byte offset of the partition on the physical block device."""
        return self.start_sector * self.sector_size

    @property
    def size_bytes(self) -> int:
        """Total size of the partition in bytes."""
        return self.sector_count * self.sector_size

    @property
    def end_sector(self) -> int:
        """Last inclusive sector number of this partition."""
        if self.sector_count == 0:
            return self.start_sector
        return self.start_sector + self.sector_count - 1
