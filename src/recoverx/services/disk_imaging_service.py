"""Multi-pass, forensic disk acquisition engine with bad-sector mapping and checkpoints."""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from recoverx.domain.device import DeviceIdentity
from recoverx.domain.imaging import (
    ImagingConfig,
    ImagingProgress,
    ImagingResult,
    SectorStatus,
)
from recoverx.infrastructure.storage.base import (
    DeviceOutOfBoundsError,
    DeviceReadError,
    ReadOnlyBlockDevice,
)
from recoverx.infrastructure.storage.range_map import RangeStatusMap
from recoverx.infrastructure.storage.resolver import (
    VolumeIdentityResolver,
)

logger = logging.getLogger(__name__)


class ImagingError(Exception):
    """Base exception for disk imaging errors."""


class ResumeIdentityMismatchError(ImagingError):
    """Raised when attempting to resume imaging with a mismatched source device identity."""


class ImagingCancelledError(ImagingError):
    """Raised when disk imaging is cancelled by user request."""


class DiskImagingService:
    """Orchestrates multi-pass disk acquisition with ddrescue-style copy, trim, and scrape."""

    def __init__(self, resolver: VolumeIdentityResolver) -> None:
        self._resolver = resolver

    def acquire_image(
        self,
        source_device: ReadOnlyBlockDevice,
        destination_image_path: Path | str,
        config: ImagingConfig | None = None,
        resume: bool = False,
        progress_callback: Callable[[ImagingProgress], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> ImagingResult:
        """Acquire a raw disk image from source_device to destination_image_path.

        Enforces source-destination separation, checkpoint persistence,
        growing skip size, exact sector-precision trimming/scraping, and
        factual completion accounting.
        """
        cfg = config or ImagingConfig()
        dest_path = Path(destination_image_path).resolve()
        dest_dir = dest_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 1. Validate separation (Rule 2 & 3 of CLAUDE.md)
        self._verify_separation(source_device, dest_dir)

        sector_size = source_device.logical_sector_size
        total_sectors = source_device.total_sectors
        total_bytes = source_device.size_bytes

        meta_path = dest_path.with_suffix(f"{dest_path.suffix}.info.json")
        map_path = dest_path.with_suffix(f"{dest_path.suffix}.map.json")
        ddrescue_map_path = dest_path.with_suffix(f"{dest_path.suffix}.map")
        badsectors_path = dest_path.with_suffix(f"{dest_path.suffix}.badsectors.json")

        range_map: RangeStatusMap
        start_time_iso = datetime.now(UTC).isoformat()
        start_time_mono = time.monotonic()

        # 2. Check for resume
        is_resuming = resume and dest_path.exists() and map_path.exists()
        if is_resuming:
            logger.info("Resuming imaging from checkpoint map %s", map_path)
            self._verify_resume_identity(meta_path, source_device.identity)
            range_map = RangeStatusMap.load_file(map_path)
            file_mode = "r+b"
        else:
            range_map = RangeStatusMap(
                total_sectors=total_sectors,
                sector_size=sector_size,
                default_status=SectorStatus.NON_TRIED,
            )
            file_mode = "w+b"

        last_checkpoint_mono = time.monotonic()
        bytes_written_since_checkpoint = 0

        def save_checkpoint(current_sector: int, phase: str) -> None:
            nonlocal last_checkpoint_mono, bytes_written_since_checkpoint
            range_map.save_file(map_path)
            range_map.export_ddrescue_mapfile(ddrescue_map_path, current_pos=current_sector)
            range_map.export_bad_sectors_json(badsectors_path)

            meta_data: dict[str, Any] = {
                "version": "1.0",
                "source_identity": {
                    "vendor": source_device.identity.vendor,
                    "product": source_device.identity.product,
                    "serial": source_device.identity.serial,
                    "capacity_bytes": source_device.identity.capacity_bytes,
                    "logical_sector_size": source_device.identity.logical_sector_size,
                    "physical_sector_size": source_device.identity.physical_sector_size,
                    "disk_identifier": source_device.identity.disk_identifier,
                    "sector0_hash": source_device.identity.sector0_hash,
                },
                "destination_image": dest_path.name,
                "settings": {
                    "block_size_bytes": cfg.block_size_bytes,
                    "initial_skip_sectors": cfg.initial_skip_sectors,
                    "max_skip_sectors": cfg.max_skip_sectors,
                    "max_retries": cfg.max_retries,
                    "retry_delay_seconds": cfg.retry_delay_seconds,
                },
                "acquisition_start_utc": start_time_iso,
                "total_sectors": total_sectors,
                "finished_sectors": range_map.finished_sectors_count,
                "bad_sectors": range_map.bad_sectors_count,
                "phase": phase,
                "is_complete": False,
            }
            tmp_meta = meta_path.with_suffix(f"{meta_path.suffix}.tmp")
            with open(tmp_meta, "w", encoding="utf-8") as f_meta:
                json.dump(meta_data, f_meta, indent=2)
                f_meta.flush()
                os.fsync(f_meta.fileno())
            os.replace(tmp_meta, meta_path)

            last_checkpoint_mono = time.monotonic()
            bytes_written_since_checkpoint = 0

        with open(dest_path, file_mode) as img_file:
            # Pre-allocate sparse/zero placeholder file if new
            if not is_resuming:
                img_file.truncate(total_bytes)
                img_file.flush()
                os.fsync(img_file.fileno())
                save_checkpoint(0, "initialized")

            sectors_per_block = max(1, cfg.block_size_bytes // sector_size)

            # =========================================================
            # PASS 1: COPY PASS (Large aligned blocks + growing skip)
            # =========================================================
            current_skip_sectors = cfg.initial_skip_sectors
            non_tried_ranges = range_map.get_ranges_by_status(SectorStatus.NON_TRIED)

            for r in non_tried_ranges:
                curr_sec = r.start_sector
                end_sec = r.start_sector + r.sector_count

                while curr_sec < end_sec:
                    if should_cancel and should_cancel():
                        save_checkpoint(curr_sec, "cancelled")
                        raise ImagingCancelledError("Imaging cancelled during copy pass.")

                    chunk_sec = min(sectors_per_block, end_sec - curr_sec)
                    chunk_bytes = chunk_sec * sector_size
                    offset = curr_sec * sector_size

                    try:
                        data = source_device.read_at(offset, chunk_bytes)
                        img_file.seek(offset)
                        img_file.write(data)
                        range_map.update_range(curr_sec, chunk_sec, SectorStatus.FINISHED)
                        curr_sec += chunk_sec
                        current_skip_sectors = cfg.initial_skip_sectors  # Reset skip on success
                        bytes_written_since_checkpoint += chunk_bytes
                    except (DeviceReadError, DeviceOutOfBoundsError):
                        # Mark this chunk as untrimmed
                        range_map.update_range(curr_sec, chunk_sec, SectorStatus.NON_TRIMMED)
                        curr_sec += chunk_sec

                        # Apply growing skip size
                        skip_count = min(current_skip_sectors, end_sec - curr_sec)
                        if skip_count > 0:
                            range_map.update_range(curr_sec, skip_count, SectorStatus.NON_TRIMMED)
                            curr_sec += skip_count
                            current_skip_sectors = min(
                                current_skip_sectors * 2, cfg.max_skip_sectors
                            )

                    # Checkpoint trigger
                    now = time.monotonic()
                    if (
                        bytes_written_since_checkpoint >= cfg.checkpoint_every_bytes
                        or now - last_checkpoint_mono >= cfg.checkpoint_interval_seconds
                    ):
                        img_file.flush()
                        os.fsync(img_file.fileno())
                        save_checkpoint(curr_sec, "copy")

                    if progress_callback:
                        progress = ImagingProgress(
                            phase="copy",
                            bytes_finished=range_map.finished_sectors_count * sector_size,
                            total_bytes=total_bytes,
                            bad_bytes=range_map.bad_sectors_count * sector_size,
                            current_sector=curr_sec,
                            pass_number=1,
                            elapsed_seconds=now - start_time_mono,
                        )
                        progress_callback(progress)

            img_file.flush()
            os.fsync(img_file.fileno())
            save_checkpoint(0, "copy_finished")

            # =========================================================
            # PASS 2: TRIM PASS (Find exact edges of unreadable areas)
            # =========================================================
            if cfg.enable_trim_pass:
                untrimmed_ranges = range_map.get_ranges_by_status(SectorStatus.NON_TRIMMED)
                for r in untrimmed_ranges:
                    if should_cancel and should_cancel():
                        save_checkpoint(r.start_sector, "cancelled")
                        raise ImagingCancelledError("Imaging cancelled during trim pass.")

                    left_sec = r.start_sector
                    right_sec = r.start_sector + r.sector_count - 1

                    # 1. Trim from left boundary
                    while left_sec <= right_sec:
                        try:
                            d = source_device.read_at(left_sec * sector_size, sector_size)
                            img_file.seek(left_sec * sector_size)
                            img_file.write(d)
                            range_map.update_range(left_sec, 1, SectorStatus.FINISHED)
                            left_sec += 1
                        except (DeviceReadError, DeviceOutOfBoundsError):
                            range_map.update_range(left_sec, 1, SectorStatus.NON_SCRAPED)
                            left_sec += 1
                            break

                    # 2. Trim from right boundary
                    while right_sec >= left_sec:
                        try:
                            d = source_device.read_at(right_sec * sector_size, sector_size)
                            img_file.seek(right_sec * sector_size)
                            img_file.write(d)
                            range_map.update_range(right_sec, 1, SectorStatus.FINISHED)
                            right_sec -= 1
                        except (DeviceReadError, DeviceOutOfBoundsError):
                            range_map.update_range(right_sec, 1, SectorStatus.NON_SCRAPED)
                            right_sec -= 1
                            break

                    # Any interior sectors between left_sec and right_sec become non_scraped
                    if right_sec >= left_sec:
                        interior_count = right_sec - left_sec + 1
                        range_map.update_range(left_sec, interior_count, SectorStatus.NON_SCRAPED)

                    if progress_callback:
                        now = time.monotonic()
                        progress = ImagingProgress(
                            phase="trim",
                            bytes_finished=range_map.finished_sectors_count * sector_size,
                            total_bytes=total_bytes,
                            bad_bytes=range_map.bad_sectors_count * sector_size,
                            current_sector=left_sec,
                            pass_number=2,
                            elapsed_seconds=now - start_time_mono,
                        )
                        progress_callback(progress)

                img_file.flush()
                os.fsync(img_file.fileno())
                save_checkpoint(0, "trim_finished")

            # =========================================================
            # PASS 3: SCRAPE PASS (1 sector at a time with retries)
            # =========================================================
            if cfg.enable_scrape_pass:
                # Scrape both unscraped and any surviving untrimmed
                scrape_candidates = range_map.get_ranges_by_status(
                    SectorStatus.NON_SCRAPED
                ) + range_map.get_ranges_by_status(SectorStatus.NON_TRIMMED)

                for r in scrape_candidates:
                    for sec in range(r.start_sector, r.start_sector + r.sector_count):
                        if should_cancel and should_cancel():
                            save_checkpoint(sec, "cancelled")
                            raise ImagingCancelledError("Imaging cancelled during scrape pass.")

                        sec_offset = sec * sector_size
                        success = False
                        last_err = ""

                        # Try up to max_retries + 1
                        attempts = 1 + cfg.max_retries
                        for att in range(attempts):
                            if att > 0 and cfg.retry_delay_seconds > 0.0:
                                time.sleep(cfg.retry_delay_seconds)

                            try:
                                sec_data = source_device.read_at(sec_offset, sector_size)
                                img_file.seek(sec_offset)
                                img_file.write(sec_data)
                                range_map.update_range(sec, 1, SectorStatus.FINISHED)
                                success = True
                                break
                            except (DeviceReadError, DeviceOutOfBoundsError) as err:
                                last_err = str(err)

                        if not success:
                            # Confirmed bad sector: write zero-filled placeholder
                            img_file.seek(sec_offset)
                            img_file.write(b"\x00" * sector_size)
                            range_map.update_range(
                                sec,
                                1,
                                SectorStatus.BAD,
                                error_message=last_err or "Unreadable sector",
                            )

                        if progress_callback:
                            now = time.monotonic()
                            progress = ImagingProgress(
                                phase="scrape",
                                bytes_finished=range_map.finished_sectors_count * sector_size,
                                total_bytes=total_bytes,
                                bad_bytes=range_map.bad_sectors_count * sector_size,
                                current_sector=sec,
                                pass_number=3,
                                elapsed_seconds=now - start_time_mono,
                            )
                            progress_callback(progress)

                img_file.flush()
                os.fsync(img_file.fileno())
                save_checkpoint(0, "scrape_finished")

        # 3. Finalize acquisition
        end_time_iso = datetime.now(UTC).isoformat()
        total_elapsed = time.monotonic() - start_time_mono

        bad_count = range_map.bad_sectors_count
        fin_count = range_map.finished_sectors_count
        # Rule 7 of CLAUDE.md: an acquisition with unreadable ranges is never reported complete
        is_complete = range_map.is_all_finished and (bad_count == 0)

        # 4. Compute image SHA-256 hash if requested
        image_sha256: str | None = None
        if cfg.compute_sha256 and dest_path.exists():
            hasher = hashlib.sha256()
            with open(dest_path, "rb") as f_hash:
                while chunk := f_hash.read(1024 * 1024):
                    hasher.update(chunk)
            image_sha256 = hasher.hexdigest()

        # Write final metadata
        final_meta: dict[str, Any] = {
            "version": "1.0",
            "source_identity": {
                "vendor": source_device.identity.vendor,
                "product": source_device.identity.product,
                "serial": source_device.identity.serial,
                "capacity_bytes": source_device.identity.capacity_bytes,
                "logical_sector_size": source_device.identity.logical_sector_size,
                "physical_sector_size": source_device.identity.physical_sector_size,
                "disk_identifier": source_device.identity.disk_identifier,
                "sector0_hash": source_device.identity.sector0_hash,
            },
            "destination_image": dest_path.name,
            "settings": {
                "block_size_bytes": cfg.block_size_bytes,
                "initial_skip_sectors": cfg.initial_skip_sectors,
                "max_skip_sectors": cfg.max_skip_sectors,
                "max_retries": cfg.max_retries,
                "retry_delay_seconds": cfg.retry_delay_seconds,
            },
            "acquisition_start_utc": start_time_iso,
            "acquisition_end_utc": end_time_iso,
            "elapsed_seconds": total_elapsed,
            "total_sectors": total_sectors,
            "finished_sectors": fin_count,
            "bad_sectors": bad_count,
            "is_complete": is_complete,
            "sha256": image_sha256,
        }
        with open(meta_path, "w", encoding="utf-8") as f_meta:
            json.dump(final_meta, f_meta, indent=2)

        notes: list[str] = []
        if is_complete:
            notes.append("Image acquisition completed successfully (100% of sectors recovered).")
        else:
            notes.append(
                f"Image acquisition finished with {bad_count} unreadable sector(s). "
                f"Acquisition marked incomplete."
            )

        return ImagingResult(
            image_path=dest_path,
            metadata_path=meta_path,
            map_path=map_path,
            total_sectors=total_sectors,
            finished_sectors=fin_count,
            bad_sectors=bad_count,
            is_complete=is_complete,
            sha256_hash=image_sha256,
            elapsed_seconds=total_elapsed,
            notes=notes,
        )

    def _verify_separation(self, source_device: ReadOnlyBlockDevice, dest_dir: Path) -> None:
        """Assert that the destination directory is not located on the source device."""
        self._resolver.verify_separation(
            source_device=source_device,
            target_path=dest_dir,
            role="destination directory",
        )

    def _verify_resume_identity(self, meta_path: Path, current_identity: DeviceIdentity) -> None:
        """Assert that current source device identity matches recorded acquisition metadata."""
        if not meta_path.exists():
            raise ResumeIdentityMismatchError(
                f"Cannot resume acquisition: metadata file not found at '{meta_path}'"
            )

        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            raise ResumeIdentityMismatchError(
                f"Cannot resume acquisition: corrupted metadata file: {e}"
            ) from e

        src_meta = meta.get("source_identity", {})
        recorded_id = DeviceIdentity(
            vendor=src_meta.get("vendor", ""),
            product=src_meta.get("product", ""),
            serial=src_meta.get("serial", ""),
            capacity_bytes=int(src_meta.get("capacity_bytes", 0)),
            logical_sector_size=int(src_meta.get("logical_sector_size", 512)),
            physical_sector_size=int(src_meta.get("physical_sector_size", 512)),
            disk_identifier=src_meta.get("disk_identifier", ""),
            sector0_hash=src_meta.get("sector0_hash", ""),
        )

        if not recorded_id.matches(current_identity):
            raise ResumeIdentityMismatchError(
                "Resume rejected: source device identity does not match metadata.\n"
                f"Recorded: capacity={recorded_id.capacity_bytes}, "
                f"id={recorded_id.disk_identifier}\n"
                f"Current : capacity={current_identity.capacity_bytes}, "
                f"id={current_identity.disk_identifier}"
            )
