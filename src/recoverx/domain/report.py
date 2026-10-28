"""Forensic scan and recovery report domain model."""

from dataclasses import dataclass

from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import CandidateStatus


@dataclass(frozen=True)
class RecoveryReport:
    """Summary report of a scan and recovery session."""

    report_id: str
    session_id: str
    created_at: float
    device_identity: DeviceIdentity
    scan_duration_seconds: float
    total_candidates: int
    status_counts: dict[CandidateStatus, int]
    recovered_count: int
    failed_count: int
    total_bytes_recovered: int
    bad_sectors_total: int

    def __post_init__(self) -> None:
        if not self.report_id.strip():
            raise ValueError("report_id cannot be empty")
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if self.created_at < 0:
            raise ValueError("created_at cannot be negative")
        if self.scan_duration_seconds < 0.0:
            raise ValueError("scan_duration_seconds cannot be negative")
        if self.total_candidates < 0:
            raise ValueError("total_candidates cannot be negative")
        if self.recovered_count < 0:
            raise ValueError("recovered_count cannot be negative")
        if self.failed_count < 0:
            raise ValueError("failed_count cannot be negative")
        if self.total_bytes_recovered < 0:
            raise ValueError("total_bytes_recovered cannot be negative")
        if self.bad_sectors_total < 0:
            raise ValueError("bad_sectors_total cannot be negative")
