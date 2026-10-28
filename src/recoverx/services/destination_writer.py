"""Atomic file writer with temp-file staging, hash verification, and no-partial-file guarantees."""

import contextlib
import hashlib
import os
import uuid
from collections.abc import Callable
from pathlib import Path

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.recovery import RecoveryResult


class RecoveryWriteError(Exception):
    """Raised when writing to the recovery destination fails."""


class RecoveryDestinationWriter:
    """Safely writes recovered files using atomic staging and verification.

    Guarantees:
    - Writes to a temporary staging file in the target directory first.
    - If write fails (disk full, permission denied, source disconnect), the temp file
      is immediately unlinked so NO partial file is left looking complete.
    - Computes and verifies SHA-256.
    - Finalizes atomically via os.replace.
    """

    def __init__(self, chunk_size_bytes: int = 64 * 1024) -> None:
        self.chunk_size = chunk_size_bytes

    def write_candidate(
        self,
        candidate: RecoveryCandidate,
        final_destination_path: Path,
        read_chunk_fn: Callable[[int, int], bytes],
    ) -> RecoveryResult:
        """Read data from source via `read_chunk_fn` and write to `final_destination_path`.

        Args:
            candidate: RecoveryCandidate with source offset, size, and expected hash.
            final_destination_path: Absolute validated target path.
            read_chunk_fn: Callback (offset, length) -> bytes from source device.

        Returns:
            RecoveryResult documenting outcome, bytes written, and hash match.
        """
        dest_dir = final_destination_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        temp_name = f".recoverx_tmp_{uuid.uuid4().hex[:8]}.part"
        temp_path = dest_dir / temp_name

        hasher = hashlib.sha256()
        bytes_written = 0
        total_to_read = candidate.size_bytes
        source_offset = candidate.source_offset

        try:
            with open(temp_path, "wb") as f:
                while bytes_written < total_to_read:
                    to_read = min(self.chunk_size, total_to_read - bytes_written)
                    data = read_chunk_fn(source_offset + bytes_written, to_read)
                    if not data:
                        raise RecoveryWriteError(
                            "Unexpected end of source data at offset "
                            f"{source_offset + bytes_written}"
                        )

                    f.write(data)
                    hasher.update(data)
                    bytes_written += len(data)

                f.flush()
                os.fsync(f.fileno())

        except Exception as e:
            # On any failure, unlink temp file so no partial file remains
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            return RecoveryResult(
                candidate_id=candidate.candidate_id,
                destination_path=str(final_destination_path),
                bytes_written=0,
                status="failed",
                hash_verified=False,
                error_message=f"Recovery failed during write: {e}",
            )

        actual_hash = hasher.hexdigest()

        # SHA-256 verification against candidate record
        hash_verified = True
        if candidate.sha256_hash and actual_hash.lower() != candidate.sha256_hash.lower():
            # Remove corrupt/mismatched output
            temp_path.unlink()
            return RecoveryResult(
                candidate_id=candidate.candidate_id,
                destination_path=str(final_destination_path),
                bytes_written=0,
                status="failed",
                hash_verified=False,
                expected_sha256=candidate.sha256_hash,
                actual_sha256=actual_hash,
                error_message=(
                    f"SHA-256 verification failed! Expected: {candidate.sha256_hash}, "
                    f"Actual: {actual_hash}"
                ),
            )

        # Atomic finalize
        try:
            os.replace(temp_path, final_destination_path)
        except OSError as e:
            if temp_path.exists():
                temp_path.unlink()
            return RecoveryResult(
                candidate_id=candidate.candidate_id,
                destination_path=str(final_destination_path),
                bytes_written=0,
                status="failed",
                hash_verified=False,
                error_message=f"Atomic rename to final destination failed: {e}",
            )

        return RecoveryResult(
            candidate_id=candidate.candidate_id,
            destination_path=str(final_destination_path),
            bytes_written=bytes_written,
            status="success",
            hash_verified=hash_verified,
            expected_sha256=candidate.sha256_hash,
            actual_sha256=actual_hash,
        )
