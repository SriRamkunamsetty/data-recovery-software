"""Unit and integration tests for FAT12/16/32 metadata recovery engine."""

import hashlib
import struct
from pathlib import Path

from recoverx.domain.enums import CandidateStatus, FileSystemType, RecoverySourceMethod
from recoverx.filesystems.fat.parser import FatFileSystem
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.fat_builder import SyntheticFatBuilder
from tests.fixtures.sample_files import (
    create_minimal_jpeg,
    create_minimal_pdf,
    create_minimal_png,
)


def test_fat32_deleted_files_recovery(tmp_path: Path) -> None:
    """Verify deleted files in FAT32 are recovered with exact names, paths, and statuses."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="USB_RECOVER")

    jpeg_bytes = create_minimal_jpeg()
    png_bytes = create_minimal_png()

    # 1. Deleted JPEG with short name
    builder.add_file("PHOTO.JPG", jpeg_bytes, is_deleted=True)
    # 2. Deleted PNG with Long File Name (LFN)
    builder.add_file("Vacation_Photo_2026.png", png_bytes, is_deleted=True)
    # 3. Active text file (should not be recovered by default deleted scan)
    builder.add_file("ACTIVE.TXT", b"Active un-deleted file content", is_deleted=False)
    # 4. Overwritten deleted file (first cluster reused in FAT table)
    builder.add_file(
        "OVERWRIT.DAT", b"Data that got overwritten" * 20, is_deleted=True, is_overwritten=True
    )

    manifest = builder.build(tmp_path / "fat32_recovery.img")

    fs = FatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        assert fs.detect(reader)
        info = fs.get_fs_info(reader)
        assert info is not None
        assert info.fs_type == FileSystemType.FAT32
        assert info.volume_label == "USB_RECOVER"

        # Recover deleted candidates only (default include_active=False)
        candidates = fs.recover_candidates(reader, base_offset=0, include_active=False)

        # Expected: PHOTO.JPG, Vacation_Photo_2026.png, OVERWRIT.DAT
        # ACTIVE.TXT is excluded because include_active=False
        cand_by_name = {c.filename: c for c in candidates}
        assert len(candidates) == 3

        # 1. Check PHOTO.JPG
        assert "PHOTO.JPG" in cand_by_name or "_HOTO.JPG" in cand_by_name
        photo_cand = cand_by_name.get("PHOTO.JPG") or cand_by_name["_HOTO.JPG"]
        assert photo_cand.source_method == RecoverySourceMethod.METADATA
        assert photo_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert photo_cand.size_bytes == len(jpeg_bytes)
        assert photo_cand.sha256_hash == hashlib.sha256(jpeg_bytes).hexdigest()

        # 2. Check Vacation_Photo_2026.png (LFN reassembled even though deleted!)
        assert "Vacation_Photo_2026.png" in cand_by_name
        png_cand = cand_by_name["Vacation_Photo_2026.png"]
        assert png_cand.source_method == RecoverySourceMethod.METADATA
        assert png_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert png_cand.size_bytes == len(png_bytes)
        assert png_cand.sha256_hash == hashlib.sha256(png_bytes).hexdigest()

        # 3. Check OVERWRIT.DAT (overwritten clusters detected!)
        over_cand = cand_by_name.get("OVERWRIT.DAT") or cand_by_name.get("_VERWRIT.DAT")
        assert over_cand is not None
        assert over_cand.status == CandidateStatus.OVERWRITTEN
        assert (
            over_cand.sha256_hash is None
        )  # Never claim hash or recovered payload for overwritten clusters!


def test_fat16_deleted_files_recovery(tmp_path: Path) -> None:
    """Verify deleted files in FAT16 are recovered correctly."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT16, volume_label="FAT16_DISK")
    pdf_bytes = create_minimal_pdf()
    builder.add_file("DOCUMENT.PDF", pdf_bytes, is_deleted=True)
    manifest = builder.build(tmp_path / "fat16_recovery.img")

    fs = FatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        assert fs.detect(reader)
        candidates = fs.recover_candidates(reader, base_offset=0)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.size_bytes == len(pdf_bytes)
        assert cand.status == CandidateStatus.PREVIEW_VALIDATED


def test_fat12_deleted_files_recovery(tmp_path: Path) -> None:
    """Verify deleted files in FAT12 are recovered correctly."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT12, volume_label="FLOPPY")
    builder.add_file("NOTES.TXT", b"Plain text notes recovered from FAT12 floppy.", is_deleted=True)
    manifest = builder.build(tmp_path / "fat12_recovery.img")

    fs = FatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        assert fs.detect(reader)
        candidates = fs.recover_candidates(reader, base_offset=0)
        assert len(candidates) == 1
        cand = candidates[0]
        assert cand.size_bytes == len(b"Plain text notes recovered from FAT12 floppy.")
        # No format validator for TXT, so status is METADATA_RECOVERED
        assert cand.status == CandidateStatus.METADATA_RECOVERED
        assert (
            cand.sha256_hash
            == hashlib.sha256(b"Plain text notes recovered from FAT12 floppy.").hexdigest()
        )


def test_directory_cycle_detection_stops_safely(tmp_path: Path) -> None:
    """Verify that a circular cluster chain in FAT directory does not loop infinitely."""
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="CYCLE_TEST")
    manifest = builder.build(tmp_path / "cycle.img")

    # Manually create a circular cluster chain in FAT table:
    # Set cluster 2's next cluster to cluster 2!
    with open(manifest.image_path, "r+b") as f:
        # Cluster 2 offset in FAT1: 32 * 512 + (2 * 4) = 16384 + 8 = 16392
        f.seek(16384 + 8)
        f.write(struct.pack("<I", 2))  # Points to itself!

    fs = FatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        # Must terminate immediately without hanging
        candidates = fs.recover_candidates(reader, base_offset=0)
        assert isinstance(candidates, list)
