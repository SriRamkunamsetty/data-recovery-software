"""Orchestrator for partition table analysis and lost-volume discovery."""

import logging
from collections.abc import Callable

from recoverx.domain.partition import PartitionInfo
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.subdevice import SubDeviceReader
from recoverx.partitions.gpt import GptParser
from recoverx.partitions.mbr import MbrParser
from recoverx.partitions.models import (
    GptHeaderHealth,
    PartitionAnalysisResult,
    PartitionTableType,
    VolumeCandidate,
)
from recoverx.partitions.scanner import LostVolumeScanner

logger = logging.getLogger(__name__)


class PartitionAnalyzer:
    """Read-only analyzer for MBR, GPT, and lost filesystem volumes."""

    @classmethod
    def analyze(
        cls,
        reader: ReadOnlyBlockDevice,
        scan_lost_volumes_if_empty: bool = True,
        force_lost_volume_scan: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> PartitionAnalysisResult:
        """Perform comprehensive partition analysis.

        Order of evaluation:
        1. Parse MBR (sector 0).
        2. If protective MBR or standard GPT signature detected, parse GPT.
        3. If GPT is valid (primary or backup), report GPT partitions.
           - If primary is corrupt and backup is intact, report BACKUP_VALID_PRIMARY_CORRUPT
             and use backup partitions!
        4. If MBR is valid and not protective, report MBR partitions.
        5. If partition table is missing/empty/corrupted, or if force_lost_volume_scan=True,
           run the LostVolumeScanner to discover lost/orphaned volumes.
        """
        notes: list[str] = []
        partitions: list[PartitionInfo] = []
        volume_candidates: list[VolumeCandidate] = []
        sector_size = reader.logical_sector_size

        # 1. Inspect MBR
        mbr_table = MbrParser.parse(reader)
        is_protective_mbr = mbr_table.is_protective if mbr_table else False

        if mbr_table and mbr_table.notes:
            notes.extend(mbr_table.notes)

        # 2. Inspect GPT
        gpt_table = GptParser.parse(reader)
        gpt_health: GptHeaderHealth | None = None
        disk_sig_or_guid = ""

        if gpt_table is not None:
            gpt_health = gpt_table.health
            disk_sig_or_guid = gpt_table.disk_guid
            if gpt_table.notes:
                notes.extend(gpt_table.notes)

        # Determine table type and partitions
        table_type = PartitionTableType.NONE

        if gpt_table is not None and gpt_health in (
            GptHeaderHealth.BOTH_VALID,
            GptHeaderHealth.PRIMARY_VALID_BACKUP_CORRUPT,
            GptHeaderHealth.BACKUP_VALID_PRIMARY_CORRUPT,
        ):
            table_type = PartitionTableType.GPT
            partitions = gpt_table.to_partition_infos(sector_size=sector_size)
            if not disk_sig_or_guid and gpt_table.disk_guid:
                disk_sig_or_guid = gpt_table.disk_guid

        elif mbr_table is not None and not is_protective_mbr:
            mbr_parts = mbr_table.to_partition_infos(sector_size=sector_size)
            if mbr_parts:
                table_type = PartitionTableType.MBR
                partitions = mbr_parts
                disk_sig_or_guid = f"0x{mbr_table.disk_signature:08X}"
            elif mbr_table.disk_signature != 0:
                table_type = PartitionTableType.MBR
                disk_sig_or_guid = f"0x{mbr_table.disk_signature:08X}"

        # Populate volume candidates from detected partitions
        for part in partitions:
            vol_cand = VolumeCandidate(
                start_sector=part.start_sector,
                sector_count=part.sector_count,
                sector_size=part.sector_size,
                detection_source=f"{table_type.value} partition {part.partition_number}",
                label=part.name,
                evidence=f"Partition table record: {part.partition_type_or_guid}",
                is_backup_structure=False,
            )
            volume_candidates.append(vol_cand)

        # 3. Lost volume discovery if table is missing/empty/corrupted or explicitly forced
        is_empty_or_none = len(partitions) == 0 or table_type == PartitionTableType.NONE
        should_scan_lost = force_lost_volume_scan or (
            scan_lost_volumes_if_empty and is_empty_or_none
        )

        if should_scan_lost:
            notes.append(
                "Scanning for lost/unpartitioned filesystem volumes and backup boot structures..."
            )
            discovered = LostVolumeScanner.scan(
                reader=reader,
                progress_callback=progress_callback,
            )

            # Deduplicate against existing partition volume candidates
            known_starts = {c.start_sector for c in volume_candidates}
            for disc in discovered:
                if disc.start_sector not in known_starts:
                    volume_candidates.append(disc)
                    known_starts.add(disc.start_sector)
                    notes.append(
                        f"Discovered {disc.filesystem_type.value} candidate volume at sector "
                        f"{disc.start_sector} ({disc.detection_source})"
                    )

        return PartitionAnalysisResult(
            table_type=table_type,
            partitions=partitions,
            volume_candidates=volume_candidates,
            gpt_health=gpt_health,
            disk_signature_or_guid=disk_sig_or_guid,
            notes=notes,
        )

    @classmethod
    def create_subdevice(
        cls,
        reader: ReadOnlyBlockDevice,
        candidate_or_partition: VolumeCandidate | PartitionInfo,
        name: str = "",
    ) -> SubDeviceReader:
        """Create an in-memory ReadOnlyBlockDevice slice for a volume without touching disk."""
        if isinstance(candidate_or_partition, VolumeCandidate):
            start_offset = candidate_or_partition.start_offset_bytes
            size = candidate_or_partition.size_bytes
            dev_name = name or f"vol@{candidate_or_partition.start_sector}"
        else:
            start_offset = candidate_or_partition.start_offset_bytes
            size = candidate_or_partition.size_bytes
            p_num = candidate_or_partition.partition_number
            p_start = candidate_or_partition.start_sector
            dev_name = name or f"part{p_num}@{p_start}"

        return SubDeviceReader(
            parent=reader,
            base_offset=start_offset,
            size_bytes=size,
            name=dev_name,
        )
