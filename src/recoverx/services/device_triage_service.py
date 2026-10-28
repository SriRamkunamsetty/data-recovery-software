"""Storage device triage service evaluating health, partition tables, and filesystem state."""

import logging

from recoverx.domain.enums import DeviceTriageStatus
from recoverx.domain.session import DeviceTriageResult
from recoverx.filesystems.exfat.parser import ExFatFileSystem
from recoverx.filesystems.fat.parser import FatFileSystem
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice
from recoverx.partitions.analyzer import PartitionAnalyzer

logger = logging.getLogger(__name__)


class DeviceTriageService:
    """Evaluates device condition and classifies its triage status.

    Section 5 of MASTER_PROMPT.md:
    Classifies the device before scanning and presents a factual explanation:
    - Detected, no media / 0 bytes / implausible capacity (controller failure)
    - Readable with I/O errors (offer imaging first, warn against repeated scans)
    - Readable, partition table damaged or missing
    - Readable, filesystem unrecognized or damaged
    - Readable, supported filesystem present
    - Encrypted volume detected (BitLocker and similar signatures)
    """

    def __init__(self) -> None:
        self._fat_parser = FatFileSystem()
        self._exfat_parser = ExFatFileSystem()

    def triage_device(self, device: ReadOnlyBlockDevice) -> DeviceTriageResult:
        """Evaluate a read-only block device and classify its condition."""
        # 1. Capacity check
        if device.size_bytes <= 0:
            return DeviceTriageResult(
                status=DeviceTriageStatus.CONTROLLER_FAILURE,
                explanation="Device reports 0 bytes or implausible capacity (controller failure).",
                recommended_action=(
                    "Do not scan. Controller failure cannot be solved through software scanning. "
                    "Recommend hardware cleanroom recovery."
                ),
                can_scan=False,
                recommend_imaging=False,
            )

        # 2. Readable check (probe sector 0)
        sector_len = min(device.logical_sector_size, device.size_bytes)
        try:
            sector0 = device.read_at(0, sector_len)
        except DeviceReadError as exc:
            logger.warning("Sector 0 read failed on %s: %s", device.identity.disk_identifier, exc)
            return DeviceTriageResult(
                status=DeviceTriageStatus.READABLE_WITH_ERRORS,
                explanation=(
                    f"Device is readable with I/O errors on initial sectors: {exc}. "
                    "Media is physically or electronically degrading."
                ),
                recommended_action=(
                    "Acquire a full raw disk image immediately using multi-pass imaging. "
                    "Avoid repeated scanning directly on physical media."
                ),
                can_scan=True,
                recommend_imaging=True,
            )

        # 3. Encrypted volume signature check (BitLocker)
        # BitLocker volumes feature signature "-FVE-FS-" at offset 3 in the VBR
        if b"-FVE-FS-" in sector0:
            return DeviceTriageResult(
                status=DeviceTriageStatus.ENCRYPTED_VOLUME,
                explanation=(
                    "Encrypted volume detected (BitLocker metadata signature present). "
                    "Data is ciphertext and cannot be carved directly."
                ),
                recommended_action=(
                    "Unlock and decrypt the volume using your recovery key or Windows BitLocker "
                    "before attempting data recovery."
                ),
                can_scan=False,
                recommend_imaging=True,
            )

        # 4. Check whole-disk filesystem (unpartitioned media / superfloppy)
        if self._fat_parser.detect(device, base_offset=0) or self._exfat_parser.detect(
            device, base_offset=0
        ):
            return DeviceTriageResult(
                status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
                explanation="Readable device with supported unpartitioned filesystem present.",
                recommended_action="Proceed with metadata scan to recover directory structure.",
                can_scan=True,
                recommend_imaging=False,
            )

        # 5. Partition analysis
        try:
            part_result = PartitionAnalyzer.analyze(device, force_lost_volume_scan=True)
        except Exception as exc:
            logger.warning("Partition analysis error: %s", exc)
            return DeviceTriageResult(
                status=DeviceTriageStatus.DAMAGED_PARTITION_TABLE,
                explanation=f"Error inspecting partition table: {exc}.",
                recommended_action="Run lost volume sweep and deep carving.",
                can_scan=True,
                recommend_imaging=False,
            )

        candidate_offsets = [p.start_offset_bytes for p in part_result.partitions] + [
            v.start_offset_bytes for v in part_result.volume_candidates
        ]
        if not candidate_offsets:
            return DeviceTriageResult(
                status=DeviceTriageStatus.DAMAGED_PARTITION_TABLE,
                explanation="Readable, partition table damaged or missing (no partitions found).",
                recommended_action="Run lost volume search and deep file carving.",
                can_scan=True,
                recommend_imaging=False,
            )

        # Check if any partition contains a supported filesystem
        has_supported_fs = False
        for offset in candidate_offsets:
            if self._fat_parser.detect(device, base_offset=offset) or self._exfat_parser.detect(
                device, base_offset=offset
            ):
                has_supported_fs = True
                break

        total_parts = len(candidate_offsets)
        if has_supported_fs:
            return DeviceTriageResult(
                status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
                explanation=(
                    f"Readable, supported filesystem found on {total_parts} partition(s)."
                ),
                recommended_action="Proceed with metadata recovery and optional file carving.",
                can_scan=True,
                recommend_imaging=False,
            )

        return DeviceTriageResult(
            status=DeviceTriageStatus.UNRECOGNIZED_FILESYSTEM,
            explanation=(
                f"Readable, but filesystem unrecognized across {total_parts} partition(s)."
            ),
            recommended_action="Run deep file carving to recover files by header signatures.",
            can_scan=True,
            recommend_imaging=False,
        )
