"""Filesystem metadata domain models."""

from dataclasses import dataclass

from recoverx.domain.enums import FileSystemType


@dataclass(frozen=True)
class FileSystemInfo:
    """Information regarding a recognized filesystem on a partition or device."""

    fs_type: FileSystemType
    volume_label: str = ""
    cluster_size_bytes: int = 0
    total_clusters: int = 0
    free_clusters: int = 0
    serial_number: str = ""
    is_damaged: bool = False
    damage_notes: str = ""
    root_directory_offset_bytes: int = 0

    def __post_init__(self) -> None:
        if self.cluster_size_bytes < 0:
            raise ValueError(f"cluster_size_bytes cannot be negative: {self.cluster_size_bytes}")
        if self.total_clusters < 0:
            raise ValueError(f"total_clusters cannot be negative: {self.total_clusters}")
        if self.free_clusters < 0:
            raise ValueError(f"free_clusters cannot be negative: {self.free_clusters}")
        if self.free_clusters > self.total_clusters:
            raise ValueError(
                f"free_clusters ({self.free_clusters}) cannot exceed "
                f"total_clusters ({self.total_clusters})"
            )
        if self.root_directory_offset_bytes < 0:
            raise ValueError(
                "root_directory_offset_bytes cannot be negative: "
                f"{self.root_directory_offset_bytes}"
            )
