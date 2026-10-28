"""Storage device and device identity domain models."""

import re
from dataclasses import dataclass

from recoverx.domain.enums import DeviceTriageStatus

_HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


@dataclass(frozen=True)
class DeviceIdentity:
    """Forensic identity record for a physical block device or disk image.

    Section 5 of MASTER_PROMPT.md: Never identify a source by drive letter alone.
    Revalidated immediately before every scan, imaging, or read session.
    """

    vendor: str
    product: str
    serial: str
    capacity_bytes: int
    logical_sector_size: int
    physical_sector_size: int
    disk_identifier: str  # MBR disk signature (hex) or GPT disk GUID
    sector0_hash: str  # SHA-256 of sector 0, lowercase hex, or empty string
    is_serial_synthetic_or_generic: bool = False

    def __post_init__(self) -> None:
        if self.capacity_bytes < 0:
            raise ValueError(f"capacity_bytes cannot be negative: {self.capacity_bytes}")

        if not _is_power_of_two(self.logical_sector_size):
            raise ValueError(
                f"logical_sector_size must be a power of two: {self.logical_sector_size}"
            )

        if not _is_power_of_two(self.physical_sector_size):
            raise ValueError(
                f"physical_sector_size must be a power of two: {self.physical_sector_size}"
            )

        if self.physical_sector_size < self.logical_sector_size:
            raise ValueError(
                f"physical_sector_size ({self.physical_sector_size}) cannot be smaller "
                f"than logical_sector_size ({self.logical_sector_size})"
            )

        if self.sector0_hash and not _HEX_64_PATTERN.match(self.sector0_hash):
            raise ValueError(
                "sector0_hash must be a 64-character hexadecimal SHA-256 string or empty"
            )

    @property
    def total_sectors(self) -> int:
        """Total logical sectors on device."""
        if self.logical_sector_size == 0:
            return 0
        return self.capacity_bytes // self.logical_sector_size

    def matches(self, other: "DeviceIdentity") -> bool:
        """Strict re-validation comparison.

        Returns True only if critical physical properties and sector 0 hash match.
        """
        if self.capacity_bytes != other.capacity_bytes:
            return False
        if self.logical_sector_size != other.logical_sector_size:
            return False
        if (
            self.disk_identifier
            and other.disk_identifier
            and self.disk_identifier.lower() != other.disk_identifier.lower()
        ):
            return False
        return not (
            self.sector0_hash
            and other.sector0_hash
            and self.sector0_hash.lower() != other.sector0_hash.lower()
        )


@dataclass(frozen=True)
class StorageDevice:
    """Discovered storage device metadata and triage state."""

    identity: DeviceIdentity
    bus_type: str  # "USB", "SD", "SCSI", "NVMe", "Image"
    physical_disk_number: int | None
    drive_letters: tuple[str, ...]
    is_removable: bool
    is_read_only: bool
    triage_status: DeviceTriageStatus
    triage_notes: str = ""
    last_io_error: str | None = None
    source_path: str = ""

    def __post_init__(self) -> None:
        if self.physical_disk_number is not None and self.physical_disk_number < 0:
            raise ValueError(
                f"physical_disk_number must be non-negative: {self.physical_disk_number}"
            )
        if not self.bus_type.strip():
            raise ValueError("bus_type cannot be empty")
