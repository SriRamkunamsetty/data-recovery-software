"""Helper generators for valid and corrupt binary sample files for carving tests."""

import io
import struct
import zipfile
import zlib


def create_minimal_jpeg() -> bytes:
    """Generate a minimal valid JPEG image byte stream."""
    buf = bytearray()
    # SOI
    buf.extend(b"\xff\xd8")

    # APP0 (JFIF)
    buf.extend(b"\xff\xe0")
    buf.extend(struct.pack(">H", 16))
    buf.extend(b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")

    # DQT
    buf.extend(b"\xff\xdb")
    buf.extend(struct.pack(">H", 67))
    buf.append(0)  # Table ID 0
    buf.extend(bytes([16] * 64))

    # SOF0 (Baseline DCT)
    buf.extend(b"\xff\xc0")
    buf.extend(struct.pack(">H", 11))
    buf.append(8)  # Precision 8 bits
    buf.extend(struct.pack(">HH", 1, 1))  # 1x1 pixels
    buf.append(1)  # 1 component (grayscale)
    buf.extend(b"\x01\x11\x00")

    # DHT (Define Huffman Table)
    buf.extend(b"\xff\xc4")
    buf.extend(struct.pack(">H", 20))
    buf.append(0)  # Table class DC, ID 0
    buf.extend(bytes([0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]))  # Counts
    buf.append(0)  # Symbol

    # SOS (Start of Scan)
    buf.extend(b"\xff\xda")
    buf.extend(struct.pack(">H", 8))
    buf.append(1)  # 1 component
    buf.extend(b"\x01\x00\x00\x3f\x00")

    # Scan entropy data (escaped FF if needed)
    buf.extend(b"\x12\x34\x56\x78")

    # EOI
    buf.extend(b"\xff\xd9")
    return bytes(buf)


def create_jpeg_with_exif_thumbnail() -> bytes:
    """Generate a valid outer JPEG containing an APP1 EXIF segment with an embedded thumbnail."""
    outer = bytearray()
    outer.extend(b"\xff\xd8")  # Outer SOI

    # APP1 EXIF segment with embedded thumbnail
    inner_thumb = create_minimal_jpeg()
    app1_payload = b"Exif\x00\x00" + b"\x00" * 10 + inner_thumb + b"\x00" * 10
    app1_len = len(app1_payload) + 2

    outer.extend(b"\xff\xe1")
    outer.extend(struct.pack(">H", app1_len))
    outer.extend(app1_payload)

    # Rest of outer JPEG
    rest = create_minimal_jpeg()[2:]  # Skip inner SOI
    outer.extend(rest)
    return bytes(outer)


def create_minimal_png() -> bytes:
    """Generate a minimal valid 1x1 PNG image."""
    buf = bytearray(b"\x89PNG\r\n\x1a\n")

    # IHDR: width=1, height=1, bit_depth=8, color_type=2, compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    buf.extend(struct.pack(">I4s", len(ihdr_data), b"IHDR"))
    buf.extend(ihdr_data)
    buf.extend(struct.pack(">I", ihdr_crc))

    # IDAT: raw scanline (filter 0 + 3 bytes RGB) compressed with zlib
    raw_scanline = b"\x00\xff\x00\x00"
    idat_data = zlib.compress(raw_scanline)
    idat_crc = zlib.crc32(b"IDAT" + idat_data)
    buf.extend(struct.pack(">I4s", len(idat_data), b"IDAT"))
    buf.extend(idat_data)
    buf.extend(struct.pack(">I", idat_crc))

    # IEND
    iend_crc = zlib.crc32(b"IEND")
    buf.extend(struct.pack(">I4s", 0, b"IEND"))
    buf.extend(struct.pack(">I", iend_crc))

    return bytes(buf)


def create_minimal_pdf() -> bytes:
    """Generate a valid minimal PDF document with xref, trailer, and %%EOF."""
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog /Pages 2 0 R >>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<< /Type /Pages /Kids [] /Count 0 >>\n"
        b"endobj\n"
        b"xref\n"
        b"0 3\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000060 00000 n \n"
        b"trailer\n"
        b"<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n"
        b"115\n"
        b"%%EOF\n"
    )
    return content


def create_minimal_zip() -> bytes:
    """Generate a standard ZIP archive with one file."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("test.txt", "RecoverX Forensic Test File")
    return bio.getvalue()


def create_minimal_docx() -> bytes:
    """Generate a minimal valid DOCX OpenXML archive."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        zf.writestr("word/document.xml", "<w:document><w:body></w:body></w:document>")
    return bio.getvalue()
