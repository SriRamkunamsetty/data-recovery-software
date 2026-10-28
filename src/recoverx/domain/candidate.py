"""File recovery candidate domain model."""

import re
from dataclasses import dataclass

from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod

_HEX_64_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class RecoveryCandidate:
    """Represents a recoverable file candidate located via metadata or carving."""

    candidate_id: str
    filename: str
    relative_path: str
    extension: str
    size_bytes: int
    source_offset: int
    source_method: RecoverySourceMethod
    status: CandidateStatus
    sha256_hash: str | None = None
    created_at: float | None = None
    modified_at: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id cannot be empty")
        if not self.filename.strip():
            raise ValueError("filename cannot be empty")
        if self.size_bytes < 0:
            raise ValueError(f"size_bytes cannot be negative: {self.size_bytes}")
        if self.source_offset < 0:
            raise ValueError(f"source_offset cannot be negative: {self.source_offset}")
        if not isinstance(self.status, CandidateStatus):
            raise TypeError(
                f"status must be an instance of CandidateStatus, got {type(self.status)}"
            )
        if self.sha256_hash is not None and not _HEX_64_PATTERN.match(self.sha256_hash):
            raise ValueError(
                f"sha256_hash must be a 64-char hexadecimal string, got {self.sha256_hash}"
            )
        if self.created_at is not None and self.created_at < 0:
            raise ValueError(f"created_at cannot be negative: {self.created_at}")
        if self.modified_at is not None and self.modified_at < 0:
            raise ValueError(f"modified_at cannot be negative: {self.modified_at}")
