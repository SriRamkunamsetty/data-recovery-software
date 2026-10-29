"""Hypothesis property-based fuzz testing for all format validators.

Verifies that validators never crash or hang on arbitrary, corrupted,
or adversarial byte inputs.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.carving.validators.bmp import BmpValidator
from recoverx.carving.validators.gif import GifValidator
from recoverx.carving.validators.isobmff import IsoBmffValidator
from recoverx.carving.validators.jpeg import JpegValidator
from recoverx.carving.validators.pdf import PdfValidator
from recoverx.carving.validators.png import PngValidator
from recoverx.carving.validators.riff import RiffValidator
from recoverx.carving.validators.sqlite import SqliteValidator
from recoverx.carving.validators.zip_ooxml import ZipValidator
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader


@pytest.fixture(scope="module")
def fuzzer_tmp_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("validator_fuzzing")


@given(payload=st.binary(min_size=0, max_size=5000))
@settings(max_examples=100)
def test_jpeg_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz JpegValidator with arbitrary byte streams prefixed by JPEG SOI."""
    fuzzed_data = b"\xff\xd8" + payload
    test_path = fuzzer_tmp_dir / "fuzz_jpeg.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=256)
    manifest = builder.build(test_path)

    validator = JpegValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=256)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=5000))
@settings(max_examples=100)
def test_png_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz PngValidator with arbitrary byte streams prefixed by PNG signature."""
    fuzzed_data = b"\x89PNG\r\n\x1a\n" + payload
    test_path = fuzzer_tmp_dir / "fuzz_png.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=128)
    manifest = builder.build(test_path)

    validator = PngValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=128)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=5000))
@settings(max_examples=100)
def test_pdf_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz PdfValidator with arbitrary byte streams prefixed by PDF header."""
    fuzzed_data = b"%PDF-1.7\n" + payload
    test_path = fuzzer_tmp_dir / "fuzz_pdf.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=64)
    manifest = builder.build(test_path)

    validator = PdfValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=64)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=5000))
@settings(max_examples=100)
def test_zip_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz ZipValidator with arbitrary byte streams prefixed by PK header."""
    fuzzed_data = b"PK\x03\x04" + payload
    test_path = fuzzer_tmp_dir / "fuzz_zip.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=512)
    manifest = builder.build(test_path)

    validator = ZipValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=512)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=4000))
@settings(max_examples=50)
def test_isobmff_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz IsoBmffValidator with arbitrary byte streams prefixed by ftyp."""
    fuzzed_data = b"\x00\x00\x00\x18ftypisom" + payload
    test_path = fuzzer_tmp_dir / "fuzz_isobmff.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=128)
    manifest = builder.build(test_path)

    validator = IsoBmffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=128)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=4000))
@settings(max_examples=50)
def test_gif_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz GifValidator with arbitrary byte streams prefixed by GIF89a."""
    fuzzed_data = b"GIF89a\x0a\x00\x0a\x00\x80\x00\x00" + payload
    test_path = fuzzer_tmp_dir / "fuzz_gif.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=64)
    manifest = builder.build(test_path)

    validator = GifValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=64)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=4000))
@settings(max_examples=50)
def test_bmp_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz BmpValidator with arbitrary byte streams prefixed by BM."""
    fuzzed_data = b"BM\x36\x00\x00\x00\x00\x00\x00\x00\x36\x00\x00\x00\x28\x00\x00\x00" + payload
    test_path = fuzzer_tmp_dir / "fuzz_bmp.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=128)
    manifest = builder.build(test_path)

    validator = BmpValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=128)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=4000))
@settings(max_examples=50)
def test_riff_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz RiffValidator with arbitrary byte streams prefixed by RIFF."""
    fuzzed_data = b"RIFF\x24\x00\x00\x00WAVEfmt " + payload
    test_path = fuzzer_tmp_dir / "fuzz_riff.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=256)
    manifest = builder.build(test_path)

    validator = RiffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=256)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0


@given(payload=st.binary(min_size=0, max_size=4000))
@settings(max_examples=50)
def test_sqlite_validator_fuzzing(fuzzer_tmp_dir: Path, payload: bytes) -> None:
    """Fuzz SqliteValidator with arbitrary byte streams prefixed by SQLite format 3."""
    fuzzed_data = b"SQLite format 3\x00\x10\x00\x01\x01\x00\x40\x20\x20" + payload
    test_path = fuzzer_tmp_dir / "fuzz_sqlite.img"

    builder = SyntheticImageBuilder(total_size_bytes=len(fuzzed_data) + 512)
    builder.add_raw(fuzzed_data, offset=128)
    manifest = builder.build(test_path)

    validator = SqliteValidator()
    with DiskImageReader(manifest.image_path) as reader:
        result = validator.validate(reader, header_offset=128)
        assert isinstance(result.status, CandidateStatus)
        assert result.size_bytes >= 0
