"""Windows Bitmap (BMP) file validator."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class BmpValidator(FormatValidator):
    """Structural validator for BMP files calculating exact row alignment and image size."""

    @property
    def format_name(self) -> str:
        return "BMP"

    @property
    def default_extension(self) -> str:
        return "bmp"

    @property
    def magic_bytes(self) -> bytes:
        return b"BM"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 100 * 1024 * 1024,  # 100 MiB limit
    ) -> ValidationResult:
        """Validate BMP file header and compute exact dimensions and image byte size."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        # Need at least 54 bytes for BITMAPFILEHEADER (14) + BITMAPINFOHEADER (40)
        try:
            hdr = device.read_at(header_offset, min(54, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading BMP header",
            )

        if len(hdr) < 26:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(hdr),
                extension=self.default_extension,
                notes="Insufficient bytes for BMP header",
            )

        if hdr[:2] != b"BM":
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=2,
                extension=self.default_extension,
                notes="Invalid BMP magic",
            )

        bf_size, _res1, _res2, bf_off_bits = struct.unpack("<IHHI", hdr[2:14])
        bi_size = struct.unpack("<I", hdr[14:18])[0]

        if bi_size not in (12, 40, 52, 56, 108, 124):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=14,
                extension=self.default_extension,
                notes=f"Unrecognized DIB header size: {bi_size}",
            )

        # Parse DIB header dimensions
        if bi_size >= 40 and len(hdr) >= 54:
            width, height, planes, bit_count, compression, bi_size_image = struct.unpack(
                "<iiHHII", hdr[18:38]
            )
        elif bi_size == 12:
            # BITMAPCOREHEADER
            w, h, planes, bit_count = struct.unpack("<HHHH", hdr[18:26])
            width, height, compression, bi_size_image = int(w), int(h), 0, 0
        else:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(hdr),
                extension=self.default_extension,
                notes="Truncated DIB header",
            )

        if width <= 0 or width > 65536 or abs(height) == 0 or abs(height) > 65536:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=26,
                extension=self.default_extension,
                notes=f"Plausibility check failed: dimensions {width}x{height}",
            )

        if planes != 1 or bit_count not in (1, 4, 8, 16, 24, 32):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=28,
                extension=self.default_extension,
                notes=f"Unsupported planes ({planes}) or bit count ({bit_count})",
            )

        # Row size is padded to 4-byte boundary
        row_size = ((width * bit_count + 31) // 32) * 4
        calculated_image_size = row_size * abs(height)

        if bi_size_image > 0 and compression in (1, 2):  # RLE compressed
            expected_total_size = bf_off_bits + bi_size_image
        else:
            expected_total_size = bf_off_bits + calculated_image_size

        # Cross-reference with bf_size from header
        final_size = expected_total_size
        if bf_size >= expected_total_size and bf_size <= expected_total_size + 4096:
            final_size = bf_size

        if final_size > max_search_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=54,
                extension=self.default_extension,
                notes=f"Computed BMP size {final_size} exceeds max search limit",
            )

        # Check device bounds
        if header_offset + final_size <= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=final_size,
                extension=self.default_extension,
                notes=f"Valid BMP: {width}x{abs(height)}, {bit_count} bpp, {final_size} bytes",
            )

        avail_bytes = device.size_bytes - header_offset
        return ValidationResult(
            status=CandidateStatus.TRUNCATED,
            size_bytes=avail_bytes,
            extension=self.default_extension,
            notes=f"Truncated BMP file (expected {final_size} B, got {avail_bytes} B)",
        )
