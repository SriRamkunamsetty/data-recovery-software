"""Hypothesis property-based fuzz testing for all format validators.

Verifies that validators never crash or hang on arbitrary, corrupted,
or adversarial byte inputs.
"""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.carving.validators.jpeg import JpegValidator
from recoverx.carving.validators.pdf import PdfValidator
from recoverx.carving.validators.png import PngValidator
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
