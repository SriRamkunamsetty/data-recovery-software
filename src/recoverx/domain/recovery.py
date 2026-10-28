"""File extraction and recovery outcome models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryResult:
    """Outcome of attempting to extract and write a recovered candidate to destination."""

    candidate_id: str
    destination_path: str
    bytes_written: int
    status: str  # "success", "failed", "skipped", "collision_renamed"
    hash_verified: bool
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id cannot be empty")
        if not self.destination_path.strip():
            raise ValueError("destination_path cannot be empty")
        if self.bytes_written < 0:
            raise ValueError(f"bytes_written cannot be negative: {self.bytes_written}")

    @property
    def is_successful(self) -> bool:
        """Whether the recovery operation succeeded."""
        return self.status in ("success", "collision_renamed")
