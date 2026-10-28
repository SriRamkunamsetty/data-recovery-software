"""Scan coordinator implementing the full 10-step forensic recovery orchestration."""

import logging
import time
from collections.abc import Callable
from typing import Any

from recoverx.carving.scanner import CarvingScanner
from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import CandidateStatus, DeviceTriageStatus, RecoverySourceMethod
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.scan import ScanProgress
from recoverx.domain.session import (
    CancellationToken,
    DeviceTriageResult,
)
from recoverx.filesystems.exfat.parser import ExFatFileSystem
from recoverx.filesystems.fat.parser import FatFileSystem
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.partitions.analyzer import PartitionAnalyzer

logger = logging.getLogger(__name__)

ScanProgressCallback = Callable[[ScanProgress], None]


class ScanCoordinatorResult:
    """Consolidated result produced by ScanCoordinator."""

    def __init__(
        self,
        source_identity: DeviceIdentity,
        triage_result: DeviceTriageResult,
        partitions: list[PartitionInfo],
        candidates: list[RecoveryCandidate],
        elapsed_seconds: float,
        carving_executed: bool,
        imaging_recommended: bool,
    ) -> None:
        self.source_identity = source_identity
        self.triage_result = triage_result
        self.partitions = partitions
        self.candidates = candidates
        self.elapsed_seconds = elapsed_seconds
        self.carving_executed = carving_executed
        self.imaging_recommended = imaging_recommended


class ScanCoordinator:
    """Orchestrates forensic scanning across triage, partitions, metadata, and carving.

    Section 12 of MASTER_PROMPT.md:
    1. Validate and identify the source (identity record, revalidation).
    2. Triage (section 5).
    3. If read errors or instability: recommend imaging first and warn against repeated scans.
    4. Analyze partitions (section 6).
    5. Run metadata recovery for supported filesystems.
    6. Offer carving with plain explanation. Deep scan NEVER starts without an explicit request.
    7. Merge and deduplicate without losing metadata (names, paths, timestamps).
    8. Validate candidates.
    9. Present findings with factual statuses.
    10. Handoff to recovery.
    """

    def __init__(self) -> None:
        from recoverx.services.device_triage_service import DeviceTriageService

        self.triage_service = DeviceTriageService()
        self.fat_parser = FatFileSystem()
        self.exfat_parser = ExFatFileSystem()

    def coordinate_scan(
        self,
        device: ReadOnlyBlockDevice,
        expected_identity: DeviceIdentity | None = None,
        enable_carving: bool = False,
        scan_lost_volumes: bool = True,
        progress_callback: ScanProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> ScanCoordinatorResult:
        """Execute the coordinated recovery scan workflow."""
        start_time = time.time()
        token = cancellation_token or CancellationToken()

        def emit_progress(
            phase: str,
            scanned: int,
            total: int,
            found: int,
            curr_sec: int = 0,
        ) -> None:
            if progress_callback is not None:
                progress = ScanProgress(
                    phase=phase,
                    bytes_scanned=scanned,
                    total_bytes=total,
                    elapsed_seconds=time.time() - start_time,
                    candidates_found=found,
                    bad_sectors_found=0,
                    current_sector=curr_sec,
                )
                progress_callback(progress)

        # -------------------------------------------------------------
        # Step 1: Validate and identify the source
        # -------------------------------------------------------------
        emit_progress("validating_source", 0, device.size_bytes, 0)
        token.check_cancelled()

        current_identity = device.identity
        if expected_identity is not None and not expected_identity.matches(current_identity):
            raise ValueError(
                f"Source device identity mismatch: expected {expected_identity.disk_identifier}, "
                f"got {current_identity.disk_identifier}"
            )

        # -------------------------------------------------------------
        # Step 2: Triage
        # -------------------------------------------------------------
        emit_progress("triage", 0, device.size_bytes, 0)
        token.check_cancelled()

        triage_result = self.triage_service.triage_device(device)
        logger.info(
            "Triage result for %s: %s", device.identity.disk_identifier, triage_result.status.value
        )

        # -------------------------------------------------------------
        # Step 3: Check stability / imaging recommendation
        # -------------------------------------------------------------
        imaging_recommended = (
            triage_result.recommend_imaging
            or triage_result.status == DeviceTriageStatus.READABLE_WITH_ERRORS
        )
        if imaging_recommended:
            logger.warning(
                "Source media instability detected. Recommending raw disk imaging prior to scan."
            )

        # -------------------------------------------------------------
        # Step 4: Analyze partitions
        # -------------------------------------------------------------
        emit_progress("analyzing_partitions", 0, device.size_bytes, 0)
        token.check_cancelled()

        part_analysis = PartitionAnalyzer.analyze(device, force_lost_volume_scan=scan_lost_volumes)
        all_partitions = list(part_analysis.partitions)
        for idx, vc in enumerate(part_analysis.volume_candidates, start=len(all_partitions) + 1):
            all_partitions.append(
                PartitionInfo(
                    partition_number=idx,
                    start_sector=vc.start_sector,
                    sector_count=vc.sector_count,
                    sector_size=vc.sector_size,
                    partition_type_or_guid=str(vc.filesystem_type),
                    name=f"Lost Volume ({vc.detection_source})",
                )
            )

        # -------------------------------------------------------------
        # Step 5: Run metadata recovery for supported filesystems
        # -------------------------------------------------------------
        emit_progress("metadata_recovery", 0, device.size_bytes, 0)
        token.check_cancelled()

        metadata_candidates: list[RecoveryCandidate] = []

        if all_partitions:
            for part in all_partitions:
                token.check_cancelled()
                sub = PartitionAnalyzer.create_subdevice(device, part)
                try:
                    # Probe FAT
                    if self.fat_parser.detect(sub):
                        part_candidates = self.fat_parser.recover_candidates(sub)
                        # Re-base candidate offsets to whole device
                        rebased = self._rebase_candidates(part_candidates, part.start_offset_bytes)
                        metadata_candidates.extend(rebased)
                    # Probe exFAT
                    elif self.exfat_parser.detect(sub):
                        part_candidates = self.exfat_parser.recover_candidates(sub)
                        rebased = self._rebase_candidates(part_candidates, part.start_offset_bytes)
                        metadata_candidates.extend(rebased)
                finally:
                    sub.close()
        else:
            # Unpartitioned device / superfloppy check
            if self.fat_parser.detect(device):
                metadata_candidates.extend(self.fat_parser.recover_candidates(device))
            elif self.exfat_parser.detect(device):
                metadata_candidates.extend(self.exfat_parser.recover_candidates(device))

        emit_progress("metadata_completed", 0, device.size_bytes, len(metadata_candidates))
        token.check_cancelled()

        # -------------------------------------------------------------
        # Step 6: Offer carving (Deep scan NEVER starts without explicit request)
        # -------------------------------------------------------------
        carved_candidates: list[RecoveryCandidate] = []
        carving_executed = False

        if enable_carving:
            carving_executed = True
            emit_progress("deep_carving", 0, device.size_bytes, len(metadata_candidates))

            def carving_progress_adapter(p: Any) -> None:
                token.check_cancelled()
                emit_progress(
                    "deep_carving",
                    p.bytes_scanned,
                    p.total_bytes,
                    len(metadata_candidates) + p.candidates_found,
                    p.current_sector,
                )

            from recoverx.carving.scanner import CancellationToken as CarvingToken

            carving_token = CarvingToken()
            if token.is_cancelled:
                carving_token.cancel()

            scanner = CarvingScanner(progress_callback=carving_progress_adapter)
            carved_candidates = scanner.scan(device, token=carving_token)

        # -------------------------------------------------------------
        # Step 7: Merge and deduplicate candidates
        # -------------------------------------------------------------
        emit_progress(
            "merging",
            device.size_bytes,
            device.size_bytes,
            len(metadata_candidates) + len(carved_candidates),
        )
        merged_candidates = self._merge_and_deduplicate(metadata_candidates, carved_candidates)

        # -------------------------------------------------------------
        # Step 8 & 9: Present findings with factual statuses
        # -------------------------------------------------------------
        elapsed = time.time() - start_time
        emit_progress("completed", device.size_bytes, device.size_bytes, len(merged_candidates))

        return ScanCoordinatorResult(
            source_identity=current_identity,
            triage_result=triage_result,
            partitions=all_partitions,
            candidates=merged_candidates,
            elapsed_seconds=elapsed,
            carving_executed=carving_executed,
            imaging_recommended=imaging_recommended,
        )

    def _rebase_candidates(
        self, candidates: list[RecoveryCandidate], base_offset: int
    ) -> list[RecoveryCandidate]:
        """Adjust candidate source offsets relative to the whole block device."""
        if base_offset == 0:
            return candidates

        rebased: list[RecoveryCandidate] = []
        for c in candidates:
            rebased.append(
                RecoveryCandidate(
                    candidate_id=c.candidate_id,
                    filename=c.filename,
                    relative_path=c.relative_path,
                    extension=c.extension,
                    size_bytes=c.size_bytes,
                    source_offset=c.source_offset + base_offset,
                    source_method=c.source_method,
                    status=c.status,
                    sha256_hash=c.sha256_hash,
                    created_at=c.created_at,
                    modified_at=c.modified_at,
                    notes=c.notes,
                )
            )
        return rebased

    def _merge_and_deduplicate(
        self,
        metadata_candidates: list[RecoveryCandidate],
        carved_candidates: list[RecoveryCandidate],
    ) -> list[RecoveryCandidate]:
        """Merge metadata and carved candidates without losing filenames, paths, or timestamps.

        If a carved file starts at the exact offset of a metadata candidate:
        - The metadata candidate is preserved with all path and timestamp attributes.
        - If the carved candidate was Preview Validated, the status is upgraded.
        - Unmatched carved candidates are added as new entries.
        """
        # Map by source_offset -> metadata candidate
        meta_by_offset: dict[int, RecoveryCandidate] = {
            c.source_offset: c for c in metadata_candidates
        }
        merged_list: list[RecoveryCandidate] = []
        consumed_carved_offsets: set[int] = set()

        for offset, meta_cand in meta_by_offset.items():
            # Check if there is a matching carved candidate at this offset
            carved_match = next((c for c in carved_candidates if c.source_offset == offset), None)
            if carved_match is not None:
                consumed_carved_offsets.add(offset)
                # Keep metadata identity, but upgrade validation status if carving verified it
                new_status = meta_cand.status
                if carved_match.status == CandidateStatus.PREVIEW_VALIDATED:
                    new_status = CandidateStatus.PREVIEW_VALIDATED

                merged_list.append(
                    RecoveryCandidate(
                        candidate_id=meta_cand.candidate_id,
                        filename=meta_cand.filename,
                        relative_path=meta_cand.relative_path,
                        extension=meta_cand.extension or carved_match.extension,
                        size_bytes=meta_cand.size_bytes or carved_match.size_bytes,
                        source_offset=meta_cand.source_offset,
                        source_method=RecoverySourceMethod.METADATA,
                        status=new_status,
                        sha256_hash=meta_cand.sha256_hash or carved_match.sha256_hash,
                        created_at=meta_cand.created_at,
                        modified_at=meta_cand.modified_at,
                        notes=(
                            f"{meta_cand.notes}; Carving validated: {carved_match.status.value}"
                            if meta_cand.notes
                            else f"Carving validated: {carved_match.status.value}"
                        ),
                    )
                )
            else:
                merged_list.append(meta_cand)

        # Add remaining non-duplicate carved candidates
        for c in carved_candidates:
            if (
                c.source_offset not in consumed_carved_offsets
                and c.source_offset not in meta_by_offset
            ):
                merged_list.append(c)

        # Return sorted by source offset
        merged_list.sort(key=lambda x: x.source_offset)
        return merged_list
