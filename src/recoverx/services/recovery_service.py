"""Orchestration service for safe, validated file extraction."""

from collections.abc import Callable
from pathlib import Path

from recoverx.config import CollisionPolicy
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.recovery import RecoveryResult
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import VolumeIdentityResolver
from recoverx.services.destination_validator import (
    resolve_collision,
    sanitize_relative_path,
    validate_destination_directory,
)
from recoverx.services.destination_writer import RecoveryDestinationWriter

RecoveryProgressCallback = Callable[[int, int, RecoveryCandidate, RecoveryResult], None]


class RecoveryService:
    """Service orchestrating extraction of recovered files to a validated separate destination."""

    def __init__(
        self,
        resolver: VolumeIdentityResolver,
        writer: RecoveryDestinationWriter | None = None,
    ) -> None:
        self.resolver = resolver
        self.writer = writer or RecoveryDestinationWriter()

    def recover_candidates(
        self,
        device: ReadOnlyBlockDevice,
        destination_directory: Path | str,
        candidates: list[RecoveryCandidate],
        collision_policy: CollisionPolicy = CollisionPolicy.RENAME,
        work_directory: Path | str | None = None,
        progress_callback: RecoveryProgressCallback | None = None,
    ) -> list[RecoveryResult]:
        """Extract candidates to destination directory with strict safety guarantees.

        1. Pre-validates destination separation from source device.
        2. Sanitizes filenames and paths against traversal and reserved names.
        3. Enforces collision policy (never overwrite by default).
        4. Atomically writes and verifies SHA-256 for each candidate.
        """
        # Step 1: Pre-validate destination directory separation and write permissions
        validated_dest = validate_destination_directory(
            destination=destination_directory,
            source_device=device,
            resolver=self.resolver,
            work_directory=work_directory,
        )

        results: list[RecoveryResult] = []
        total_candidates = len(candidates)

        for index, cand in enumerate(candidates):
            # Step 2: Sanitize destination path
            safe_rel_path = sanitize_relative_path(cand.relative_path, cand.filename)
            target_path = validated_dest / safe_rel_path

            # Step 3: Handle file collision
            try:
                resolved_path = resolve_collision(target_path, collision_policy)
            except FileExistsError as e:
                res = RecoveryResult(
                    candidate_id=cand.candidate_id,
                    destination_path=str(target_path),
                    bytes_written=0,
                    status="failed",
                    hash_verified=False,
                    error_message=str(e),
                )
                results.append(res)
                if progress_callback is not None:
                    progress_callback(index + 1, total_candidates, cand, res)
                continue

            if resolved_path is None:
                # Skipped due to collision policy
                res = RecoveryResult(
                    candidate_id=cand.candidate_id,
                    destination_path=str(target_path),
                    bytes_written=0,
                    status="skipped",
                    hash_verified=False,
                    error_message="Skipped because destination file already exists",
                )
                results.append(res)
                if progress_callback is not None:
                    progress_callback(index + 1, total_candidates, cand, res)
                continue

            # Step 4: Re-validate separation immediately before writing
            self.resolver.verify_separation(device, resolved_path, role="destination file")

            # Step 5: Perform atomic write and verification
            res = self.writer.write_candidate(
                candidate=cand,
                final_destination_path=resolved_path,
                read_chunk_fn=device.read_at,
            )

            # Mark collision_renamed status if path was renamed
            if res.is_successful and resolved_path != target_path:
                res = RecoveryResult(
                    candidate_id=res.candidate_id,
                    destination_path=res.destination_path,
                    bytes_written=res.bytes_written,
                    status="collision_renamed",
                    hash_verified=res.hash_verified,
                    expected_sha256=res.expected_sha256,
                    actual_sha256=res.actual_sha256,
                )

            results.append(res)

            if progress_callback is not None:
                progress_callback(index + 1, total_candidates, cand, res)

        return results
