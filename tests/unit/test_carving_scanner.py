"""Unit and integration tests for CarvingScanner."""

from pathlib import Path

import pytest

from recoverx.carving.scanner import CancellationToken, CarvingScanner
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.fault import (
    ByteRange,
    FaultConfig,
    FaultInjectionReader,
)
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.sample_files import (
    create_jpeg_with_exif_thumbnail,
    create_minimal_docx,
    create_minimal_jpeg,
    create_minimal_pdf,
    create_minimal_png,
)


@pytest.fixture
def multi_file_image(tmp_path: Path) -> Path:
    """Generate a test disk image with known files at designated offsets."""
    jpeg_data = create_minimal_jpeg()
    png_data = create_minimal_png()
    pdf_data = create_minimal_pdf()
    docx_data = create_minimal_docx()

    builder = SyntheticImageBuilder(total_size_bytes=512 * 1024, fill_byte=b"\x00")
    builder.add_file("img1.jpg", jpeg_data, offset=2048)
    builder.add_file("img2.png", png_data, offset=32768)
    builder.add_file("doc1.pdf", pdf_data, offset=65536)
    builder.add_file("doc2.docx", docx_data, offset=131072)

    manifest = builder.build(tmp_path / "multi_files.img")
    return manifest.image_path


def test_scanner_discovers_known_files_with_correct_statuses(
    multi_file_image: Path,
) -> None:
    """Verify scanner finds all valid files at known offsets with Preview validated status."""
    scanner = CarvingScanner(chunk_size_bytes=64 * 1024, overlap_bytes=4096)
    with DiskImageReader(multi_file_image) as reader:
        candidates = scanner.scan(reader)

        assert len(candidates) == 4

        # Map by offset
        by_offset = {c.source_offset: c for c in candidates}
        assert 2048 in by_offset
        assert 32768 in by_offset
        assert 65536 in by_offset
        assert 131072 in by_offset

        # Extensions and statuses
        assert by_offset[2048].extension == "jpg"
        assert by_offset[2048].status == CandidateStatus.PREVIEW_VALIDATED

        assert by_offset[32768].extension == "png"
        assert by_offset[32768].status == CandidateStatus.PREVIEW_VALIDATED

        assert by_offset[65536].extension == "pdf"
        assert by_offset[65536].status == CandidateStatus.PREVIEW_VALIDATED

        assert by_offset[131072].extension == "docx"
        assert by_offset[131072].status == CandidateStatus.PREVIEW_VALIDATED


def test_scanner_finds_file_across_chunk_boundary(tmp_path: Path) -> None:
    """Verify scanner finds a file signature placed near/across the chunk boundary via overlap."""
    png_data = create_minimal_png()
    chunk_size = 32 * 1024  # 32 KiB chunk
    # Place header 5 bytes before the chunk boundary
    header_offset = chunk_size - 5

    builder = SyntheticImageBuilder(total_size_bytes=128 * 1024)
    builder.add_file("boundary.png", png_data, offset=header_offset)
    manifest = builder.build(tmp_path / "boundary.img")

    scanner = CarvingScanner(chunk_size_bytes=chunk_size, overlap_bytes=4096)
    with DiskImageReader(manifest.image_path) as reader:
        candidates = scanner.scan(reader)
        assert len(candidates) == 1
        assert candidates[0].source_offset == header_offset
        assert candidates[0].extension == "png"
        assert candidates[0].status == CandidateStatus.PREVIEW_VALIDATED


def test_scanner_deduplicates_exif_thumbnails(tmp_path: Path) -> None:
    """Verify that an outer JPEG with an inner EXIF thumbnail does NOT create two candidates."""
    jpeg_with_thumb = create_jpeg_with_exif_thumbnail()
    builder = SyntheticImageBuilder(total_size_bytes=128 * 1024)
    builder.add_file("exif_outer.jpg", jpeg_with_thumb, offset=1024)
    manifest = builder.build(tmp_path / "dedup_test.img")

    scanner = CarvingScanner()
    with DiskImageReader(manifest.image_path) as reader:
        candidates = scanner.scan(reader)
        # Must only produce the single outer JPEG candidate, NOT the inner thumbnail
        assert len(candidates) == 1
        assert candidates[0].source_offset == 1024
        assert candidates[0].extension == "jpg"


def test_scanner_cancellation_stops_within_one_chunk(multi_file_image: Path) -> None:
    """Verify cancellation token halts execution promptly without running through whole image."""
    token = CancellationToken()
    # Cancel immediately
    token.cancel()

    scanner = CarvingScanner(chunk_size_bytes=32 * 1024)
    with DiskImageReader(multi_file_image) as reader:
        candidates = scanner.scan(reader, token=token)
        # Should stop before scanning all chunks
        assert len(candidates) == 0


def test_scanner_graceful_continuation_on_read_errors(tmp_path: Path) -> None:
    """Verify that reading bad sectors does not abort the scan and subsequent files are found."""
    png1 = create_minimal_png()
    png2 = create_minimal_png()

    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    builder.add_file("first.png", png1, offset=1024)
    builder.add_file("second.png", png2, offset=32768)
    manifest = builder.build(tmp_path / "bad_sector.img")

    base_reader = DiskImageReader(manifest.image_path)
    # Simulate a bad sector between the two files (at offset 16384)
    fault_config = FaultConfig(
        unreadable_ranges=[ByteRange(start=16384, end=16896)],
    )
    with FaultInjectionReader(base_reader, fault_config) as fault_reader:
        scanner = CarvingScanner(chunk_size_bytes=8192, overlap_bytes=1024)
        candidates = scanner.scan(fault_reader)

        # Both files should still be found!
        assert len(candidates) == 2
        offsets = {c.source_offset for c in candidates}
        assert offsets == {1024, 32768}
