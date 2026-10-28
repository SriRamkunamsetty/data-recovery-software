"""Persistent sector range status map for multi-pass disk acquisition."""

import json
import os
from pathlib import Path
from typing import Any, Self

from recoverx.domain.imaging import BlockRange, SectorStatus


class RangeStatusMap:
    """Maintains a contiguous, non-overlapping sequence of sector ranges.

    Coalesces adjacent ranges of identical status and supports splitting
    intervals when sub-ranges change status during multi-pass imaging.
    """

    def __init__(
        self,
        total_sectors: int,
        sector_size: int = 512,
        default_status: SectorStatus = SectorStatus.NON_TRIED,
    ) -> None:
        if total_sectors <= 0:
            raise ValueError(f"total_sectors must be positive: {total_sectors}")
        if sector_size <= 0:
            raise ValueError(f"sector_size must be positive: {sector_size}")

        self._total_sectors = total_sectors
        self._sector_size = sector_size
        self._ranges: list[BlockRange] = [
            BlockRange(start_sector=0, sector_count=total_sectors, status=default_status)
        ]

    @property
    def total_sectors(self) -> int:
        return self._total_sectors

    @property
    def sector_size(self) -> int:
        return self._sector_size

    @property
    def ranges(self) -> list[BlockRange]:
        return list(self._ranges)

    @property
    def is_all_finished(self) -> bool:
        """True only if every sector on the device is in FINISHED status."""
        return len(self._ranges) == 1 and self._ranges[0].status == SectorStatus.FINISHED

    def count_sectors_by_status(self, status: SectorStatus) -> int:
        """Total number of sectors currently having the specified status."""
        return sum(r.sector_count for r in self._ranges if r.status == status)

    @property
    def finished_sectors_count(self) -> int:
        return self.count_sectors_by_status(SectorStatus.FINISHED)

    @property
    def bad_sectors_count(self) -> int:
        return self.count_sectors_by_status(SectorStatus.BAD)

    def get_ranges_by_status(self, status: SectorStatus) -> list[BlockRange]:
        """Return all contiguous block ranges currently matching the given status."""
        return [r for r in self._ranges if r.status == status]

    def update_range(
        self,
        start_sector: int,
        sector_count: int,
        new_status: SectorStatus,
        error_message: str = "",
    ) -> None:
        """Update the status of [start_sector, start_sector + sector_count).

        Splits existing intervals at boundaries and coalesces adjacent intervals
        with matching status.
        """
        if sector_count <= 0:
            return
        if start_sector < 0 or start_sector >= self._total_sectors:
            raise ValueError(
                f"start_sector {start_sector} out of bounds [0, {self._total_sectors})"
            )

        end_sector = min(start_sector + sector_count, self._total_sectors)
        actual_count = end_sector - start_sector
        if actual_count <= 0:
            return

        new_ranges: list[BlockRange] = []

        for r in self._ranges:
            r_start = r.start_sector
            r_end = r.start_sector + r.sector_count

            # Case 1: Entirely before target range
            if r_end <= start_sector:
                new_ranges.append(r)
                continue

            # Case 2: Entirely after target range
            if r_start >= end_sector:
                new_ranges.append(r)
                continue

            # Case 3: Left piece survives
            if r_start < start_sector:
                left_count = start_sector - r_start
                new_ranges.append(
                    BlockRange(
                        start_sector=r_start,
                        sector_count=left_count,
                        status=r.status,
                        error_message=r.error_message,
                    )
                )

            # Insert updated middle segment on first intersecting range
            if not any(
                nr.start_sector == start_sector and nr.sector_count == actual_count
                for nr in new_ranges
            ):
                new_ranges.append(
                    BlockRange(
                        start_sector=start_sector,
                        sector_count=actual_count,
                        status=new_status,
                        error_message=error_message,
                    )
                )

            # Case 4: Right piece survives
            if r_end > end_sector:
                right_count = r_end - end_sector
                new_ranges.append(
                    BlockRange(
                        start_sector=end_sector,
                        sector_count=right_count,
                        status=r.status,
                        error_message=r.error_message,
                    )
                )

        # Sort by start_sector
        new_ranges.sort(key=lambda r: r.start_sector)

        # Coalesce adjacent intervals with same status
        coalesced: list[BlockRange] = []
        for r in new_ranges:
            if not coalesced:
                coalesced.append(r)
                continue

            last = coalesced[-1]
            if last.status == r.status and last.start_sector + last.sector_count == r.start_sector:
                coalesced[-1] = BlockRange(
                    start_sector=last.start_sector,
                    sector_count=last.sector_count + r.sector_count,
                    status=last.status,
                    error_message=last.error_message or r.error_message,
                )
            else:
                coalesced.append(r)

        self._ranges = coalesced

    def to_dict(self) -> dict[str, Any]:
        """Serialize map to dictionary."""
        return {
            "total_sectors": self._total_sectors,
            "sector_size": self._sector_size,
            "ranges": [
                {
                    "start_sector": r.start_sector,
                    "sector_count": r.sector_count,
                    "status": r.status.value,
                    "error_message": r.error_message,
                }
                for r in self._ranges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Reconstruct map from dictionary."""
        total_sectors = int(data["total_sectors"])
        sector_size = int(data.get("sector_size", 512))
        obj = cls(total_sectors=total_sectors, sector_size=sector_size)

        loaded_ranges: list[BlockRange] = []
        for r_dict in data["ranges"]:
            loaded_ranges.append(
                BlockRange(
                    start_sector=int(r_dict["start_sector"]),
                    sector_count=int(r_dict["sector_count"]),
                    status=SectorStatus(r_dict["status"]),
                    error_message=r_dict.get("error_message", ""),
                )
            )

        obj._ranges = loaded_ranges
        return obj

    def save_file(self, path: Path | str) -> None:
        """Atomically save mapfile to disk."""
        target_path = Path(path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_path, target_path)

    @classmethod
    def load_file(cls, path: Path | str) -> Self:
        """Load mapfile from disk."""
        target_path = Path(path).resolve()
        with open(target_path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def export_bad_sectors_json(self, path: Path | str) -> None:
        """Export machine-readable JSON listing exclusively unreadable bad sectors."""
        target_path = Path(path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        bad_ranges = self.get_ranges_by_status(SectorStatus.BAD)

        out_list = [
            {
                "start_sector": r.start_sector,
                "sector_count": r.sector_count,
                "start_offset": r.start_offset(self._sector_size),
                "size_bytes": r.size_bytes(self._sector_size),
                "error_message": r.error_message,
            }
            for r in bad_ranges
        ]

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(out_list, f, indent=2)

    def export_ddrescue_mapfile(self, path: Path | str, current_pos: int = 0) -> None:
        """Export standard ddrescue-compatible ASCII mapfile."""
        target_path = Path(path).resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = [
            "# Mapfile. Generated by RecoverX DiskImagingService",
            "# current_pos  current_status  current_pass",
            f"0x{current_pos * self._sector_size:08X}     ?               1",
            "#      pos        size  status",
        ]

        for r in self._ranges:
            pos = r.start_sector * self._sector_size
            size = r.sector_count * self._sector_size
            lines.append(f"0x{pos:08X}  0x{size:08X}  {r.status.value}")

        with open(target_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
