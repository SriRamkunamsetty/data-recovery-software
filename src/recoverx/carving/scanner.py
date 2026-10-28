"""Streaming file carving engine over ReadOnlyBlockDevice."""

import threading
import time
import uuid
from collections.abc import Callable

from recoverx.carving.registry import SignatureRegistry
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.domain.scan import ScanProgress
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class OperationCancelledError(Exception):
    """Raised when an active scan or recovery job is cancelled."""


class CancellationToken:
    """Thread-safe cancellation token for interruptible background operations."""

    def __init__(self) -> None:
        self._is_cancelled = threading.Event()

    def cancel(self) -> None:
        """Signal cancellation."""
        self._is_cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        """True if cancellation was requested."""
        return self._is_cancelled.is_set()

    def check_cancelled(self) -> None:
        """Raise OperationCancelledError if cancellation was requested."""
        if self.is_cancelled:
            raise OperationCancelledError("Carving scan operation was cancelled.")


ProgressCallback = Callable[[ScanProgress], None]


class CarvingScanner:
    """Memory-safe, streaming file carver over ReadOnlyBlockDevice."""

    def __init__(
        self,
        registry: SignatureRegistry | None = None,
        chunk_size_bytes: int = 1024 * 1024,  # 1 MiB chunks
        overlap_bytes: int | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        if chunk_size_bytes <= 0:
            raise ValueError(f"chunk_size_bytes must be positive: {chunk_size_bytes}")

        effective_overlap = (
            overlap_bytes
            if overlap_bytes is not None
            else min(64 * 1024, max(4096, chunk_size_bytes // 4))
        )

        if effective_overlap < 0 or effective_overlap >= chunk_size_bytes:
            raise ValueError(
                f"overlap_bytes ({effective_overlap}) must be non-negative and smaller "
                f"than chunk_size_bytes ({chunk_size_bytes})"
            )

        self.registry = registry or SignatureRegistry.default_registry()
        self.chunk_size = chunk_size_bytes
        self.overlap = effective_overlap
        self.progress_callback = progress_callback

    def scan(
        self,
        device: ReadOnlyBlockDevice,
        token: CancellationToken | None = None,
    ) -> list[RecoveryCandidate]:
        """Streamingly scan the device for file signatures and validate candidates.

        Memory remains strictly bounded by chunk_size + overlap.
        Gracefully continues on read errors.
        Stops within one chunk upon cancellation.
        """
        candidates: list[RecoveryCandidate] = []
        found_offsets: set[int] = set()
        skipped_ranges: list[tuple[int, int]] = []
        bad_sectors_count = 0
        start_time = time.perf_counter()

        total_bytes = device.size_bytes
        curr_offset = 0
        sector_size = max(1, device.logical_sector_size)

        while curr_offset < total_bytes:
            # Cancellation checkpoint: must stop within 1 chunk
            if token is not None and token.is_cancelled:
                break

            # Calculate read length (chunk_size + overlap, bounded by device end)
            remaining_bytes = total_bytes - curr_offset
            read_len = min(self.chunk_size + self.overlap, remaining_bytes)

            try:
                chunk = device.read_at(curr_offset, read_len)
            except DeviceReadError:
                # Read error continuation: skip forward by 1 sector and log bad sector
                bad_sectors_count += 1
                curr_offset += sector_size
                continue

            if not chunk:
                break

            # Only scan signatures within the primary chunk window (chunk_size)
            # The overlap window is scanned in the next iteration to avoid boundary misses
            scan_limit = min(self.chunk_size, len(chunk))

            # Scan registered signatures
            for sig in self.registry.signatures:
                if token is not None and token.is_cancelled:
                    break

                pos = 0
                while pos < scan_limit:
                    idx = chunk.find(sig.magic, pos)
                    if idx == -1 or idx >= scan_limit:
                        break

                    abs_offset = curr_offset + idx

                    # Check sector alignment rule if required
                    if sig.sector_aligned and (abs_offset % sector_size != 0):
                        pos = idx + 1
                        continue

                    # Deduplication check
                    if abs_offset in found_offsets or self._is_in_skipped_ranges(
                        abs_offset, skipped_ranges
                    ):
                        pos = idx + len(sig.magic)
                        continue

                    # Validate candidate structure
                    result = sig.validator.validate(device, abs_offset)
                    found_offsets.add(abs_offset)

                    # Create RecoveryCandidate
                    candidate_id = f"cand-{uuid.uuid4().hex[:8]}"
                    filename = f"carved_0x{abs_offset:08X}.{result.extension}"
                    rel_path = f"Carved/{result.extension.upper()}/{filename}"

                    cand = RecoveryCandidate(
                        candidate_id=candidate_id,
                        filename=filename,
                        relative_path=rel_path,
                        extension=result.extension,
                        size_bytes=result.size_bytes,
                        source_offset=abs_offset,
                        source_method=RecoverySourceMethod.CARVED,
                        status=result.status,
                        sha256_hash=result.sha256,
                        notes=result.notes,
                    )
                    candidates.append(cand)

                    # Record file span so inner records (like ZIP local headers) are not carved
                    if result.status == CandidateStatus.PREVIEW_VALIDATED and result.size_bytes > 0:
                        skipped_ranges.append((abs_offset, abs_offset + result.size_bytes))

                    # Record inner ranges to skip (e.g. EXIF embedded thumbnails)
                    for start_rel, end_rel in result.inner_ranges_to_skip:
                        skipped_ranges.append((abs_offset + start_rel, abs_offset + end_rel))

                    # Advance search position past signature
                    pos = idx + max(1, len(sig.magic))

            # Advance current offset by the chunk size
            curr_offset += self.chunk_size

            # Report progress
            if self.progress_callback is not None:
                elapsed = time.perf_counter() - start_time
                scanned = min(curr_offset, total_bytes)
                current_sector = scanned // sector_size
                rem_seconds = (elapsed / scanned) * (total_bytes - scanned) if scanned > 0 else None
                prog = ScanProgress(
                    phase="carving",
                    bytes_scanned=scanned,
                    total_bytes=total_bytes,
                    elapsed_seconds=elapsed,
                    candidates_found=len(candidates),
                    bad_sectors_found=bad_sectors_count,
                    current_sector=current_sector,
                    estimated_remaining_seconds=rem_seconds,
                )
                self.progress_callback(prog)

        return candidates

    def _is_in_skipped_ranges(self, offset: int, ranges: list[tuple[int, int]]) -> bool:
        """Check if offset falls inside an inner embedded sub-object range."""
        return any(start <= offset < end for start, end in ranges)
