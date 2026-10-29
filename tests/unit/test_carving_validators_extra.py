"""Unit tests for second-set validators: MP4/MOV, HEIC, GIF, BMP, WAV/AVI, MP3, RAW, SQLite."""

import struct
from pathlib import Path

from recoverx.carving.validators.bmp import BmpValidator
from recoverx.carving.validators.gif import GifValidator
from recoverx.carving.validators.isobmff import IsoBmffValidator
from recoverx.carving.validators.mp3 import Mp3Validator
from recoverx.carving.validators.riff import RiffValidator
from recoverx.carving.validators.sqlite import SqliteValidator
from recoverx.carving.validators.tiff_raw import TiffRawValidator
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader

# ---------------------------------------------------------------------------
# Synthetic test builders for second-set file formats
# ---------------------------------------------------------------------------


def create_minimal_mp4(brand: bytes = b"isom") -> bytes:
    """Build a minimal valid MP4 file container (ftyp + moov + mdat)."""
    # ftyp box (16 bytes)
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", brand, 0x00000200)
    # moov box (24 bytes)
    moov_payload = b"\x00" * 16
    moov = struct.pack(">I4s", len(moov_payload) + 8, b"moov") + moov_payload
    # mdat box (32 bytes)
    mdat_payload = b"MEDIA_DATA_STREAM_TEST_CONTENT_!"
    mdat = struct.pack(">I4s", len(mdat_payload) + 8, b"mdat") + mdat_payload
    return ftyp + moov + mdat


def create_minimal_heic() -> bytes:
    """Build a minimal valid HEIC container (ftyp with heic brand + meta + mdat)."""
    ftyp = struct.pack(">I4s4sI", 16, b"ftyp", b"heic", 0)
    meta_payload = b"\x00" * 16
    meta = struct.pack(">I4s", len(meta_payload) + 8, b"meta") + meta_payload
    mdat_payload = b"IMAGE_ITEM_DATA_0123456789ABCDEF"
    mdat = struct.pack(">I4s", len(mdat_payload) + 8, b"mdat") + mdat_payload
    return ftyp + meta + mdat


def create_minimal_gif(version: bytes = b"GIF89a", width: int = 10, height: int = 10) -> bytes:
    """Build a minimal valid GIF stream terminating with 0x3B."""
    # Header: 6 bytes version + 7 bytes screen descriptor
    # Packed byte: 0x80 (Global Color Table present, 2 colors)
    hdr = version + struct.pack("<HHBBB", width, height, 0x80, 0, 0)
    # Global Color Table: 2 colors * 3 bytes = 6 bytes (Black, White)
    gct = b"\x00\x00\x00\xff\xff\xff"
    # Image Descriptor: 0x2C + 9 bytes
    img_desc = b"\x2c" + struct.pack("<HHHHB", 0, 0, width, height, 0)
    # LZW code size + data sub-blocks + terminator
    lzw_data = b"\x02\x02\x44\x01\x00"  # LZW min size 2, sub-block of 2 bytes, 0 terminator
    # Trailer: 0x3B
    trailer = b"\x3b"
    return hdr + gct + img_desc + lzw_data + trailer


def create_minimal_bmp(width: int = 4, height: int = 4) -> bytes:
    """Build a minimal valid uncompressed 24-bit BMP image."""
    row_size = ((width * 24 + 31) // 32) * 4  # 4 * 3 = 12 bytes -> aligned to 12
    image_size = row_size * height  # 12 * 4 = 48 bytes
    bf_off_bits = 54  # 14 + 40
    bf_size = bf_off_bits + image_size

    # BITMAPFILEHEADER (14 bytes)
    file_hdr = struct.pack("<2sIHHI", b"BM", bf_size, 0, 0, bf_off_bits)
    # BITMAPINFOHEADER (40 bytes)
    info_hdr = struct.pack(
        "<iiiHHIIiiII", 40, width, height, 1, 24, 0, image_size, 2835, 2835, 0, 0
    )
    pixel_data = b"\xff\x00\x00" * width  # Blue row
    padded_row = pixel_data + b"\x00" * (row_size - len(pixel_data))
    return file_hdr + info_hdr + (padded_row * height)


def create_minimal_wav(sample_rate: int = 44100, channels: int = 2) -> bytes:
    """Build a minimal valid WAV audio file container."""
    audio_data = b"\x00\x10\x00\x20" * 32  # 128 bytes of PCM data
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        sample_rate * channels * 2,
        channels * 2,
        16,
    )
    data_chunk = struct.pack("<4sI", b"data", len(audio_data)) + audio_data
    riff_payload = b"WAVE" + fmt_chunk + data_chunk
    riff_hdr = struct.pack("<4sI", b"RIFF", len(riff_payload)) + riff_payload
    return riff_hdr


def create_minimal_avi(width: int = 320, height: int = 240) -> bytes:
    """Build a minimal valid AVI video container."""
    avih_chunk = struct.pack(
        "<4sIIIIIIIIIII", b"avih", 40, 33333, 10000, 0, 0, 100, 0, 1, 1024, width, height
    )
    list_chunk = struct.pack("<4sI4s", b"LIST", len(avih_chunk) + 4, b"hdrl") + avih_chunk
    riff_payload = b"AVI " + list_chunk
    return struct.pack("<4sI", b"RIFF", len(riff_payload)) + riff_payload


def create_minimal_mp3(num_frames: int = 8) -> bytes:
    """Build an MP3 byte stream with an ID3v2 tag and MPEG Layer III frames."""
    # ID3v2 tag: 10 bytes header + 10 bytes payload
    id3_payload = b"TIT2\x00\x00\x00\x04\x00\x00Song"
    id3_hdr = struct.pack(">3sBBB4B", b"ID3", 3, 0, 0, 0, 0, 0, len(id3_payload))
    id3_tag = id3_hdr + id3_payload

    # Single MPEG1 Layer III frame: 128 kbps, 44100 Hz -> 417 bytes
    # Frame header: 0xFF, 0xFB (MPEG1, Layer III), 0x90 (128 kbps, 44.1 kHz), 0x00
    frame_hdr = b"\xff\xfb\x90\x00"
    frame_body = b"\x55" * (417 - len(frame_hdr))
    frame = frame_hdr + frame_body
    return id3_tag + (frame * num_frames)


def create_minimal_tiff(width: int = 8, height: int = 8) -> bytes:
    """Build a minimal valid little-endian TIFF file."""
    # Header: II, magic 42, first IFD offset 8
    hdr = struct.pack("<2sHI", b"II", 42, 8)
    strip_data = b"\xaa" * (width * height)
    strip_offset = (
        8 + 2 + (4 * 12) + 4
    )  # Header (8) + num_entries (2) + 4 entries (48) + next_ifd (4) = 62

    # IFD0 with 4 tags: ImageWidth, ImageLength, StripOffsets, StripByteCounts
    entries = (
        struct.pack("<HHI4s", 0x0100, 4, 1, struct.pack("<I", width))
        + struct.pack("<HHI4s", 0x0101, 4, 1, struct.pack("<I", height))
        + struct.pack("<HHI4s", 0x0111, 4, 1, struct.pack("<I", strip_offset))
        + struct.pack("<HHI4s", 0x0117, 4, 1, struct.pack("<I", len(strip_data)))
    )
    ifd0 = struct.pack("<H", 4) + entries + struct.pack("<I", 0)
    return hdr + ifd0 + strip_data


def create_minimal_sqlite(page_size: int = 4096, page_count: int = 3) -> bytes:
    """Build a minimal valid SQLite 3 database header and B-tree page 1."""
    hdr = bytearray(100)
    hdr[:16] = b"SQLite format 3\x00"
    struct.pack_into(">H", hdr, 16, page_size)
    struct.pack_into(">I", hdr, 28, page_count)
    struct.pack_into(">I", hdr, 56, 1)  # UTF-8 encoding

    # B-tree page 1 header: leaf table (0x0D) at offset 100
    btree_hdr = b"\x0d\x00\x00\x00\x00\x00\x00\x00"
    page1 = bytes(hdr) + btree_hdr + b"\x00" * (page_size - 108)
    pages = [page1] + [b"\x55" * page_size for _ in range(page_count - 1)]
    return b"".join(pages)


# ---------------------------------------------------------------------------
# Validator Unit Tests
# ---------------------------------------------------------------------------


def test_isobmff_validator_mp4_complete(tmp_path: Path) -> None:
    """Test IsoBmffValidator validates complete MP4 container with ftyp, moov, mdat."""
    mp4_bytes = create_minimal_mp4()
    builder = SyntheticImageBuilder(total_size_bytes=len(mp4_bytes) + 1024)
    builder.add_raw(mp4_bytes, offset=512)
    manifest = builder.build(tmp_path / "test_mp4.raw")

    validator = IsoBmffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=512)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "mp4"
        assert res.size_bytes == len(mp4_bytes)


def test_isobmff_validator_heic(tmp_path: Path) -> None:
    """Test IsoBmffValidator recognizes HEIC brand and sets extension."""
    heic_bytes = create_minimal_heic()
    builder = SyntheticImageBuilder(total_size_bytes=len(heic_bytes) + 1024)
    builder.add_raw(heic_bytes, offset=256)
    manifest = builder.build(tmp_path / "test_heic.raw")

    validator = IsoBmffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=256)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "heic"
        assert res.size_bytes == len(heic_bytes)


def test_isobmff_validator_truncated(tmp_path: Path) -> None:
    """Test IsoBmffValidator reports TRUNCATED when box size extends past end of device."""
    mp4_bytes = create_minimal_mp4()
    truncated_bytes = mp4_bytes[:24]  # Truncated inside moov box
    builder = SyntheticImageBuilder(total_size_bytes=len(truncated_bytes) + 128)
    builder.add_raw(truncated_bytes, offset=64)
    manifest = builder.build(tmp_path / "test_mp4_trunc.raw")

    validator = IsoBmffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=64)
        assert res.status == CandidateStatus.TRUNCATED


def test_gif_validator_valid_gif89a(tmp_path: Path) -> None:
    """Test GifValidator successfully walks GIF89a to trailer 0x3B."""
    gif_bytes = create_minimal_gif(version=b"GIF89a", width=32, height=32)
    builder = SyntheticImageBuilder(total_size_bytes=len(gif_bytes) + 512)
    builder.add_raw(gif_bytes, offset=128)
    manifest = builder.build(tmp_path / "test_gif.raw")

    validator = GifValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=128)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "gif"
        assert res.size_bytes == len(gif_bytes)


def test_gif_validator_truncated(tmp_path: Path) -> None:
    """Test GifValidator marks file TRUNCATED if trailer 0x3B is missing."""
    gif_bytes = create_minimal_gif()[:-1]  # Strip trailer 0x3B
    builder = SyntheticImageBuilder(total_size_bytes=len(gif_bytes) + 512)
    builder.add_raw(gif_bytes, offset=128)
    manifest = builder.build(tmp_path / "test_gif_trunc.raw")

    validator = GifValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=128)
        assert res.status == CandidateStatus.TRUNCATED


def test_bmp_validator_valid(tmp_path: Path) -> None:
    """Test BmpValidator verifies row alignment and full image size."""
    bmp_bytes = create_minimal_bmp(width=8, height=8)
    builder = SyntheticImageBuilder(total_size_bytes=len(bmp_bytes) + 1024)
    builder.add_raw(bmp_bytes, offset=256)
    manifest = builder.build(tmp_path / "test_bmp.raw")

    validator = BmpValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=256)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "bmp"
        assert res.size_bytes == len(bmp_bytes)


def test_bmp_validator_truncated(tmp_path: Path) -> None:
    """Test BmpValidator marks file TRUNCATED when device ends before pixel rows."""
    bmp_bytes = create_minimal_bmp(width=8, height=8)
    short_bmp = bmp_bytes[:60]  # Only header and first partial row
    builder = SyntheticImageBuilder(total_size_bytes=len(short_bmp) + 64)
    builder.add_raw(short_bmp, offset=32)
    manifest = builder.build(tmp_path / "test_bmp_trunc.raw")

    validator = BmpValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=32)
        assert res.status == CandidateStatus.TRUNCATED


def test_riff_validator_wav(tmp_path: Path) -> None:
    """Test RiffValidator validates WAV audio structure and chunk sizes."""
    wav_bytes = create_minimal_wav()
    builder = SyntheticImageBuilder(total_size_bytes=len(wav_bytes) + 1024)
    builder.add_raw(wav_bytes, offset=512)
    manifest = builder.build(tmp_path / "test_wav.raw")

    validator = RiffValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=512)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "wav"
        assert res.size_bytes == len(wav_bytes)


def test_riff_validator_avi(tmp_path: Path) -> None:
    """Test RiffValidator validates AVI container structure."""
    avi_bytes = create_minimal_avi()
    builder = SyntheticImageBuilder(total_size_bytes=len(avi_bytes) + 1024)
    builder.add_raw(avi_bytes, offset=256)
    manifest = builder.build(tmp_path / "test_avi.raw")

    validator = RiffValidator("AVI")
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=256)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "avi"
        assert res.size_bytes == len(avi_bytes)


def test_mp3_validator_valid_chain(tmp_path: Path) -> None:
    """Test Mp3Validator walks ID3v2 tag and MPEG audio frame chain."""
    mp3_bytes = create_minimal_mp3(num_frames=8)
    builder = SyntheticImageBuilder(total_size_bytes=len(mp3_bytes) + 2048)
    builder.add_raw(mp3_bytes, offset=1024)
    manifest = builder.build(tmp_path / "test_mp3.raw")

    validator = Mp3Validator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=1024)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "mp3"
        assert res.size_bytes == len(mp3_bytes)


def test_tiff_raw_validator_valid(tmp_path: Path) -> None:
    """Test TiffRawValidator walks IFD entries and calculates file size from strip offsets."""
    tiff_bytes = create_minimal_tiff(width=16, height=16)
    builder = SyntheticImageBuilder(total_size_bytes=len(tiff_bytes) + 1024)
    builder.add_raw(tiff_bytes, offset=512)
    manifest = builder.build(tmp_path / "test_tiff.raw")

    validator = TiffRawValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=512)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "tif"
        assert res.size_bytes == len(tiff_bytes)


def test_sqlite_validator_valid(tmp_path: Path) -> None:
    """Test SqliteValidator validates page count and page size from 100-byte header."""
    sqlite_bytes = create_minimal_sqlite(page_size=4096, page_count=4)
    builder = SyntheticImageBuilder(total_size_bytes=len(sqlite_bytes) + 4096)
    builder.add_raw(sqlite_bytes, offset=2048)
    manifest = builder.build(tmp_path / "test_sqlite.raw")

    validator = SqliteValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=2048)
        assert res.status == CandidateStatus.PREVIEW_VALIDATED
        assert res.extension == "sqlite"
        assert res.size_bytes == len(sqlite_bytes)


def test_sqlite_validator_truncated(tmp_path: Path) -> None:
    """Test SqliteValidator detects when total pages exceed device capacity."""
    sqlite_bytes = create_minimal_sqlite(page_size=4096, page_count=5)
    # Only write 2 pages out of 5
    partial_bytes = sqlite_bytes[: 4096 * 2]
    builder = SyntheticImageBuilder(total_size_bytes=len(partial_bytes) + 512)
    builder.add_raw(partial_bytes, offset=128)
    manifest = builder.build(tmp_path / "test_sqlite_trunc.raw")

    validator = SqliteValidator()
    with DiskImageReader(manifest.image_path) as reader:
        res = validator.validate(reader, header_offset=128)
        assert res.status == CandidateStatus.TRUNCATED
