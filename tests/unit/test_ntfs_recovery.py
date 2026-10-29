"""Unit and integration tests for NTFS metadata recovery engine."""

import hashlib
from pathlib import Path

from recoverx.domain.enums import CandidateStatus, FileSystemType
from recoverx.filesystems.ntfs.parser import NtfsFileSystem
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.ntfs_builder import SyntheticNtfsBuilder
from tests.fixtures.sample_files import create_minimal_jpeg, create_minimal_png


def test_ntfs_deleted_files_recovery(tmp_path: Path) -> None:
    """Verify deleted files in NTFS recover with exact names, paths, and matching hashes."""
    builder = SyntheticNtfsBuilder(volume_label="REC_NTFS")

    jpeg_bytes = create_minimal_jpeg()
    # Large PNG exceeding resident limit (e.g. 5000 bytes)
    png_bytes = create_minimal_png() + b"\x00" * 4096

    # 1. Directory: "Reports" (parent 5)
    dir_idx = builder.add_file(
        "Reports",
        content=b"",
        is_directory=True,
        parent_record_index=5,
    )

    # 2. Deleted resident JPEG file in Root (parent 5)
    builder.add_file(
        "Photo_Small.jpg",
        jpeg_bytes,
        is_deleted=True,
        is_resident=True,
        parent_record_index=5,
    )

    # 3. Deleted non-resident PNG file in Root (parent 5)
    builder.add_file(
        "Chart_Large.png",
        png_bytes,
        is_deleted=True,
        is_resident=False,
        parent_record_index=5,
    )

    # 4. Deleted file in subdirectory "Reports"
    report_text = b"Quarterly forensic recovery report summary text."
    builder.add_file(
        "Summary.txt",
        report_text,
        is_deleted=True,
        is_resident=True,
        parent_record_index=dir_idx,
        relative_dir="Reports",
    )

    # 5. Overwritten deleted file (marked in use in $Bitmap)
    builder.add_file(
        "Overwritten.bin",
        b"Cluster data reallocated by new file",
        is_deleted=True,
        is_resident=False,
        is_overwritten=True,
        parent_record_index=5,
    )

    # 6. Active file (excluded from deleted scan)
    builder.add_file(
        "Active_Doc.txt",
        b"Active live document content",
        is_deleted=False,
        parent_record_index=5,
    )

    # 7. Corrupted MFT record (fixup error)
    builder.add_file(
        "Corrupted.dat",
        b"Broken fixup bytes",
        is_deleted=True,
        corrupt_fixup=True,
        parent_record_index=5,
    )

    manifest = builder.build(tmp_path / "ntfs_recovery.img")

    fs = NtfsFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        assert fs.detect(reader)
        info = fs.get_fs_info(reader)
        assert info is not None
        assert info.fs_type == FileSystemType.NTFS
        assert info.volume_label == "REC_NTFS"

        # Recover deleted candidates only (include_active=False)
        candidates = fs.recover_candidates(reader, base_offset=0, include_active=False)

        cand_by_name = {c.filename: c for c in candidates}

        # 1. Check Photo_Small.jpg (resident deleted JPEG)
        assert "Photo_Small.jpg" in cand_by_name
        jpg_cand = cand_by_name["Photo_Small.jpg"]
        assert jpg_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert jpg_cand.size_bytes == len(jpeg_bytes)
        assert jpg_cand.sha256_hash == hashlib.sha256(jpeg_bytes).hexdigest()

        # 2. Check Chart_Large.png (non-resident deleted PNG)
        assert "Chart_Large.png" in cand_by_name
        png_cand = cand_by_name["Chart_Large.png"]
        assert png_cand.status == CandidateStatus.PREVIEW_VALIDATED
        assert png_cand.size_bytes == len(png_bytes)
        assert png_cand.sha256_hash == hashlib.sha256(png_bytes).hexdigest()

        # 3. Check Summary.txt in Reports subdirectory
        assert "Summary.txt" in cand_by_name
        txt_cand = cand_by_name["Summary.txt"]
        assert txt_cand.status == CandidateStatus.METADATA_RECOVERED
        assert txt_cand.relative_path == "Reports/Summary.txt"
        assert txt_cand.size_bytes == len(report_text)
        assert txt_cand.sha256_hash == hashlib.sha256(report_text).hexdigest()

        # 4. Check Overwritten.bin (detected in $Bitmap as reallocated)
        assert "Overwritten.bin" in cand_by_name
        over_cand = cand_by_name["Overwritten.bin"]
        assert over_cand.status == CandidateStatus.OVERWRITTEN

        # 5. Active file is NOT included
        assert "Active_Doc.txt" not in cand_by_name


def test_ntfs_include_active_files_recovery(tmp_path: Path) -> None:
    """Verify include_active=True recovers both active and deleted files."""
    builder = SyntheticNtfsBuilder()
    builder.add_file("Active.txt", b"Hello active file", is_deleted=False)
    builder.add_file("Deleted.txt", b"Hello deleted file", is_deleted=True)
    manifest = builder.build(tmp_path / "ntfs_active.img")

    fs = NtfsFileSystem()
    with DiskImageReader(manifest.image_path) as reader:
        candidates = fs.recover_candidates(reader, base_offset=0, include_active=True)
        cand_by_name = {c.filename: c for c in candidates}

        assert "Active.txt" in cand_by_name
        assert cand_by_name["Active.txt"].status == CandidateStatus.ALLOCATED

        assert "Deleted.txt" in cand_by_name
        assert cand_by_name["Deleted.txt"].status in (
            CandidateStatus.METADATA_RECOVERED,
            CandidateStatus.PREVIEW_VALIDATED,
        )
