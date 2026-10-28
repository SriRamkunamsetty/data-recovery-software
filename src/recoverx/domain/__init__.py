"""RecoverX domain models and enumerations."""

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import (
    CandidateStatus,
    DeviceTriageStatus,
    FileSystemType,
    JobStatus,
    RecoverySourceMethod,
)
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.report import RecoveryReport
from recoverx.domain.scan import BadSectorRange, ScanJob, ScanProgress, SectorReadResult

__all__ = [
    "BadSectorRange",
    "CandidateStatus",
    "DeviceIdentity",
    "DeviceTriageStatus",
    "FileSystemInfo",
    "FileSystemType",
    "JobStatus",
    "PartitionInfo",
    "RecoveryCandidate",
    "RecoveryReport",
    "RecoveryResult",
    "RecoverySourceMethod",
    "ScanJob",
    "ScanProgress",
    "SectorReadResult",
    "StorageDevice",
]
