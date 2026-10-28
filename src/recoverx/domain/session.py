"""Recovery session, triage, and job management domain models."""

import threading
import time
from dataclasses import dataclass, field

from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import DeviceTriageStatus, JobStatus


class RecoverXError(Exception):
    """Base exception for domain and service errors in RecoverX."""


class DuplicateSourceJobError(RecoverXError):
    """Raised when an operation is attempted on a source device already in use."""


class DestinationConflictError(RecoverXError):
    """Raised when a concurrent operation targets an already active destination path."""


class DatabaseCorruptionError(RecoverXError):
    """Raised when the session database fails integrity checks."""


class ScanCancelledError(RecoverXError):
    """Raised when an in-progress scan, imaging, or recovery job is cancelled."""


class CancellationToken:
    """Thread-safe cooperative cancellation token."""

    def __init__(self) -> None:
        self._is_cancelled = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation to all cooperating workers."""
        self._is_cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._is_cancelled.is_set()

    def check_cancelled(self) -> None:
        """Raise ScanCancelledError if cancellation has been signaled."""
        if self._is_cancelled.is_set():
            raise ScanCancelledError("Operation was cancelled by user.")


@dataclass(frozen=True)
class DeviceTriageResult:
    """Forensic triage classification result for a block storage device."""

    status: DeviceTriageStatus
    explanation: str
    recommended_action: str
    can_scan: bool
    recommend_imaging: bool
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RecoverySession:
    """Persistent user recovery session state."""

    session_id: str
    name: str
    created_at: float
    updated_at: float
    status: str  # "active", "completed", "cancelled", "failed"
    source_path: str
    source_identity: DeviceIdentity
    triage_status: DeviceTriageStatus
    triage_notes: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id cannot be empty")
        if not self.name.strip():
            raise ValueError("name cannot be empty")
        if self.created_at < 0:
            raise ValueError("created_at cannot be negative")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be earlier than created_at")


@dataclass(frozen=True)
class ScanJobRecord:
    """Persistent job record for tracking scan, imaging, or extraction tasks."""

    job_id: str
    session_id: str
    job_type: str  # "scan", "imaging", "recovery"
    status: JobStatus
    source_identifier: str
    destination_path: str | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    progress_fraction: float = 0.0
    error_message: str | None = None
