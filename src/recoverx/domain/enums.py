"""Core domain enumerations for RecoverX."""

from enum import StrEnum


class CandidateStatus(StrEnum):
    """Factual candidate statuses.

    Rule 7 of CLAUDE.md: No percentage 'recovery probability'.
    Use factual statuses only.
    """

    METADATA_RECOVERED = "Metadata recovered"
    SIGNATURE_MATCHED = "Signature matched"
    PREVIEW_VALIDATED = "Preview validated"
    PARTIALLY_READABLE = "Partially readable"
    TRUNCATED = "Truncated"
    UNVERIFIED = "Unverified"
    RECOVERY_FAILED = "Recovery failed"


class DeviceTriageStatus(StrEnum):
    """Device health classification from preliminary inspection."""

    NOT_DETECTED = "Not detected by Windows"
    CONTROLLER_FAILURE = (
        "Detected, no media / 0 bytes / implausible capacity (likely controller failure)"
    )
    READABLE_WITH_ERRORS = "Readable with I/O errors (imaging recommended)"
    DAMAGED_PARTITION_TABLE = "Readable, partition table damaged or missing"
    UNRECOGNIZED_FILESYSTEM = "Readable, filesystem unrecognized or damaged"
    SUPPORTED_FILESYSTEM = "Readable, supported filesystem present"
    ENCRYPTED_VOLUME = "Encrypted volume detected"


class RecoverySourceMethod(StrEnum):
    """Method by which a candidate file was located."""

    METADATA = "Metadata"
    CARVED = "Carved"
    LOST_VOLUME = "Lost volume"


class JobStatus(StrEnum):
    """Lifecycle status of a scan or imaging job."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class FileSystemType(StrEnum):
    """Supported and recognized filesystem types."""

    FAT12 = "FAT12"
    FAT16 = "FAT16"
    FAT32 = "FAT32"
    EXFAT = "exFAT"
    NTFS = "NTFS"
    UNKNOWN = "Unknown"
