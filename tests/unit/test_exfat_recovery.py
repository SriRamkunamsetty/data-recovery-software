"""Unit and integration tests for exFAT metadata recovery engine."""

import hashlib
from pathlib import Path

from recoverx.domain.enums import CandidateStatus, FileSystemType, RecoverySourceMethod
from recoverx.filesystems.exfat.parser import ExFatFileSystem
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.exfat_builder import SyntheticExFatBuilder
from tests.fixtures.sample_files import create_minimal_jpeg, create_minimal_png


def test_exfat_deleted_files_recovery(tmp_path: Path) -> None:
    """Verify deleted files in exFAT recover with exact names, paths, and matching hashes."""
    builder = SyntheticExFatBuilder(volume_label="REC_EXFAT")

    jpeg_bytes = create_minimal_jpeg()
    png_bytes = create_minimal_png()

    # 1. Deleted JPEG with NoFatChain=True
    builder.add_file("Summer_Vacation.jpg", jpeg_bytes, is_deleted=True, no_fat_chain=True)
    # 2. Deleted PNG with NoFatChain=True
    builder.add_file("Diagram.png", png_bytes, is_deleted=True, no_fat_chain=True)
    # 3. Active file (excluded from deleted scan)
    builder.add_file("Active_Document.docx", b"Active data stream", is_deleted=False)
    # 4. Overwritten deleted file (marked allocated in Allocation Bitmap)
    builder.add_file(
        "ReusedCluster.dat", b"Overwritten cluster payload", is_deleted=True, is_overwritten=True
    )
    # 5. Deleted file with corrupted entry-set checksum
    builder.add_file("Corrupted_Set.bin", b"Some data", is_deleted=True, corrupt_checksum=True)

    manifest = builder.build(tmp_path / "exfat_recovery.img")

    fs = ExFatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        assert fs.detect(reader)
        info = fs.get_fs_info(reader)
        assert info is not None
        assert info.fs_type == FileSystemType.EXFAT
        assert info.volume_label == "REC_EXFAT"

        # Recover deleted candidates only (include_active=False)
        candidates = fs.recover_candidates(reader, base_offset=0, include_active=False)

        # Expected: Summer_Vacation.jpg, Diagram.png, ReusedCluster.dat, Corrupted_Set.bin
        cand_by_name = {c.filename: c for c in candidates}
        assert len(candidates) == 4

        # 1. Check Summer_Vacation.jpg
        jpg_cand = cand_by_name["Summer_Vacation.jpg"]
        assert jpg_cand.source_method == RecoverySourceMethod.METADATA
        assert jpg_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert jpg_cand.size_bytes == len(jpeg_bytes)
        assert jpg_cand.sha256_hash == hashlib.sha256(jpeg_bytes).hexdigest()

        # 2. Check Diagram.png
        png_cand = cand_by_name["Diagram.png"]
        assert png_cand.source_method == RecoverySourceMethod.METADATA
        assert png_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert png_cand.size_bytes == len(png_bytes)
        assert png_cand.sha256_hash == hashlib.sha256(png_bytes).hexdigest()

        # 3. Check ReusedCluster.dat (detected in bitmap as overwritten)
        over_cand = cand_by_name["ReusedCluster.dat"]
        assert over_cand.status == CandidateStatus.OVERWRITTEN
        assert over_cand.sha256_hash is None

        # 4. Check Corrupted_Set.bin (entry-set checksum failure reported as corrupted metadata)
        bad_cand = cand_by_name["Corrupted_Set.bin"]
        assert bad_cand.status == CandidateStatus.CORRUPTED
        assert bad_cand.sha256_hash is None


def test_exfat_include_active_files_recovery(tmp_path: Path) -> None:
    """Verify include_active=True recovers both active and deleted files."""
    builder = SyntheticExFatBuilder()
    builder.add_file("Active.txt", b"Hello active file", is_deleted=False)
    builder.add_file("Deleted.txt", b"Hello deleted file", is_deleted=True)
    manifest = builder.build(tmp_path / "exfat_active.img")

    fs = ExFatFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        candidates = fs.recover_candidates(reader, include_active=True)
        assert len(candidates) == 2
        cand_map = {c.filename: c for c in candidates}
        assert cand_map["Active.txt"].status == CandidateStatus.ALLOCATED
        assert cand_map["Deleted.txt"].status == CandidateStatus.METADATA_RECOVERED
