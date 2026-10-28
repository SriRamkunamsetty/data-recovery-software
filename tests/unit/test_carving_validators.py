"""Unit tests for individual format validators."""

from pathlib import Path

from recoverx.carving.validators.jpeg import JpegValidator
from recoverx.carving.validators.pdf import PdfValidator
from recoverx.carving.validators.png import PngValidator
from recoverx.carving.validators.zip_ooxml import ZipValidator
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader
from tests.fixtures.sample_files import (
    create_jpeg_with_exif_thumbnail,
    create_minimal_docx,
    create_minimal_jpeg,
    create_minimal_pdf,
    create_minimal_png,
    create_minimal_zip,
)


class TestJpegValidator:
    """Validate JpegValidator behavior on complete, corrupt, and embedded thumbnail images."""

    def test_valid_minimal_jpeg(self, tmp_path: Path) -> None:
        jpeg_bytes = create_minimal_jpeg()
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("valid.jpg", jpeg_bytes, offset=1024)
        manifest = builder.build(tmp_path / "jpeg_test.img")

        validator = JpegValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=1024)

            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.size_bytes == len(jpeg_bytes)
            assert result.extension == "jpg"
            assert result.sha256 is not None

    def test_jpeg_with_embedded_exif_thumbnail(self, tmp_path: Path) -> None:
        jpeg_bytes = create_jpeg_with_exif_thumbnail()
        builder = SyntheticImageBuilder(total_size_bytes=128 * 1024)
        builder.add_file("thumb.jpg", jpeg_bytes, offset=2048)
        manifest = builder.build(tmp_path / "exif_test.img")

        validator = JpegValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=2048)

            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.size_bytes == len(jpeg_bytes)
            # Embedded thumbnail range must be captured for carving scanner deduplication
            assert len(result.inner_ranges_to_skip) > 0

    def test_truncated_jpeg_missing_eoi(self, tmp_path: Path) -> None:
        # Cut off before EOI marker
        jpeg_bytes = create_minimal_jpeg()[:-10]
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("truncated.jpg", jpeg_bytes, offset=512)
        manifest = builder.build(tmp_path / "trunc_test.img")

        validator = JpegValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=512)
            assert result.status == CandidateStatus.TRUNCATED


class TestPngValidator:
    """Validate PngValidator behavior on clean, CRC-corrupted, and truncated streams."""

    def test_valid_png(self, tmp_path: Path) -> None:
        png_bytes = create_minimal_png()
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("valid.png", png_bytes, offset=512)
        manifest = builder.build(tmp_path / "png_test.img")

        validator = PngValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=512)
            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.size_bytes == len(png_bytes)
            assert result.extension == "png"

    def test_png_corrupt_crc(self, tmp_path: Path) -> None:
        png_bytes = bytearray(create_minimal_png())
        # Corrupt 1 byte in the IHDR data section
        png_bytes[16] ^= 0xFF
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("corrupt.png", bytes(png_bytes), offset=512)
        manifest = builder.build(tmp_path / "png_crc.img")

        validator = PngValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=512)
            assert result.status == CandidateStatus.TRUNCATED
            assert "CRC mismatch" in result.notes

    def test_png_truncated_before_iend(self, tmp_path: Path) -> None:
        png_bytes = create_minimal_png()[:-12]  # Strip IEND chunk
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("no_iend.png", png_bytes, offset=512)
        manifest = builder.build(tmp_path / "png_no_iend.img")

        validator = PngValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=512)
            assert result.status == CandidateStatus.TRUNCATED


class TestPdfValidator:
    """Validate PdfValidator behavior."""

    def test_valid_pdf(self, tmp_path: Path) -> None:
        pdf_bytes = create_minimal_pdf()
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("doc.pdf", pdf_bytes, offset=1024)
        manifest = builder.build(tmp_path / "pdf_test.img")

        validator = PdfValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=1024)
            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.extension == "pdf"

    def test_truncated_pdf_missing_eof(self, tmp_path: Path) -> None:
        pdf_bytes = create_minimal_pdf()[:80]  # Cut before xref and %%EOF
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("cut.pdf", pdf_bytes, offset=1024)
        manifest = builder.build(tmp_path / "pdf_cut.img")

        validator = PdfValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=1024)
            assert result.status == CandidateStatus.TRUNCATED


class TestZipAndOfficeValidator:
    """Validate ZipValidator behavior for standard archives and OOXML classification."""

    def test_valid_zip(self, tmp_path: Path) -> None:
        zip_bytes = create_minimal_zip()
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("archive.zip", zip_bytes, offset=2048)
        manifest = builder.build(tmp_path / "zip_test.img")

        validator = ZipValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=2048)
            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.extension == "zip"

    def test_valid_docx_classification(self, tmp_path: Path) -> None:
        docx_bytes = create_minimal_docx()
        builder = SyntheticImageBuilder(total_size_bytes=128 * 1024)
        builder.add_file("document.docx", docx_bytes, offset=4096)
        manifest = builder.build(tmp_path / "docx_test.img")

        validator = ZipValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=4096)
            assert result.status == CandidateStatus.PREVIEW_VALIDATED
            assert result.extension == "docx"

    def test_truncated_zip_missing_eocd(self, tmp_path: Path) -> None:
        zip_bytes = create_minimal_zip()[:60]  # Strip Central Directory and EOCD
        builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
        builder.add_file("broken.zip", zip_bytes, offset=1024)
        manifest = builder.build(tmp_path / "zip_broken.img")

        validator = ZipValidator()
        with DiskImageReader(manifest.image_path) as reader:
            result = validator.validate(reader, header_offset=1024)
            assert result.status == CandidateStatus.TRUNCATED
