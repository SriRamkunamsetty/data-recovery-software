"""GIF (Graphics Interchange Format) file validator supporting GIF87a and GIF89a."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class GifValidator(FormatValidator):
    """Structural validator walking GIF data stream to the 0x3B trailer."""

    @property
    def format_name(self) -> str:
        return "GIF"

    @property
    def default_extension(self) -> str:
        return "gif"

    @property
    def magic_bytes(self) -> bytes:
        return b"GIF8"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 50 * 1024 * 1024,  # 50 MiB limit
    ) -> ValidationResult:
        """Walk GIF blocks to trailer 0x3B."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        # Read header and screen descriptor (13 bytes)
        try:
            hdr = device.read_at(header_offset, min(13, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading GIF header",
            )

        if len(hdr) < 13:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(hdr),
                extension=self.default_extension,
                notes="Insufficient bytes for GIF header",
            )

        version = hdr[:6]
        if version not in (b"GIF87a", b"GIF89a"):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=6,
                extension=self.default_extension,
                notes=f"Invalid GIF version magic: {version!r}",
            )

        width, height, packed = struct.unpack("<HHB", hdr[6:11])
        if width == 0 or height == 0:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=13,
                extension=self.default_extension,
                notes=f"Invalid dimensions: {width}x{height}",
            )

        curr_offset = header_offset + 13
        # Check Global Color Table
        has_gct = (packed & 0x80) != 0
        if has_gct:
            gct_size = 3 * (1 << ((packed & 0x07) + 1))
            curr_offset += gct_size

        limit_offset = min(device.size_bytes, header_offset + max_search_bytes)
        images_count = 0
        blocks_walked = 0

        while curr_offset < limit_offset:
            blocks_walked += 1
            if blocks_walked > 100_000:
                # Infinite loop protection
                break

            try:
                b = device.read_at(curr_offset, 1)
            except DeviceReadError:
                return ValidationResult(
                    status=CandidateStatus.TRUNCATED,
                    size_bytes=curr_offset - header_offset,
                    extension=self.default_extension,
                    notes=f"Read error at block {blocks_walked}",
                )

            if not b:
                break

            block_type = b[0]

            if block_type == 0x3B:
                # Trailer reached! File is complete
                total_size = curr_offset - header_offset + 1
                status = (
                    CandidateStatus.PREVIEW_VALIDATED
                    if images_count > 0
                    else CandidateStatus.SIGNATURE_MATCHED
                )
                return ValidationResult(
                    status=status,
                    size_bytes=total_size,
                    extension=self.default_extension,
                    notes=f"Clean trailer 0x3B reached ({images_count} image(s))",
                )

            if block_type == 0x00:
                # Stray null padding
                curr_offset += 1
                continue

            if block_type == 0x21:
                # Extension block: 1 byte label, followed by sub-blocks
                curr_offset += 2  # skip 0x21 and label
                curr_offset = self._skip_sub_blocks(device, curr_offset, limit_offset)
                if curr_offset < 0:
                    # Truncated sub-block
                    return ValidationResult(
                        status=CandidateStatus.TRUNCATED,
                        size_bytes=limit_offset - header_offset,
                        extension=self.default_extension,
                        notes="Truncated extension sub-block",
                    )
                continue

            if block_type == 0x2C:
                # Image descriptor: 9 bytes
                try:
                    desc = device.read_at(curr_offset + 1, 9)
                except DeviceReadError:
                    return ValidationResult(
                        status=CandidateStatus.TRUNCATED,
                        size_bytes=curr_offset - header_offset,
                        extension=self.default_extension,
                        notes="Read error reading image descriptor",
                    )

                if len(desc) < 9:
                    return ValidationResult(
                        status=CandidateStatus.TRUNCATED,
                        size_bytes=curr_offset - header_offset + len(desc) + 1,
                        extension=self.default_extension,
                        notes="Truncated image descriptor",
                    )

                curr_offset += 10
                img_packed = desc[8]
                has_lct = (img_packed & 0x80) != 0
                if has_lct:
                    lct_size = 3 * (1 << ((img_packed & 0x07) + 1))
                    curr_offset += lct_size

                # LZW min code size
                curr_offset += 1
                curr_offset = self._skip_sub_blocks(device, curr_offset, limit_offset)
                if curr_offset < 0:
                    return ValidationResult(
                        status=CandidateStatus.TRUNCATED,
                        size_bytes=limit_offset - header_offset,
                        extension=self.default_extension,
                        notes="Truncated image data sub-blocks",
                    )

                images_count += 1
                continue

            # Unrecognized byte
            break

        total_size = curr_offset - header_offset
        if images_count > 0:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=total_size,
                extension=self.default_extension,
                notes=f"Truncated GIF before trailer ({images_count} image(s))",
            )

        return ValidationResult(
            status=CandidateStatus.SIGNATURE_MATCHED,
            size_bytes=max(total_size, 13),
            extension=self.default_extension,
            notes="GIF signature matched without valid trailer",
        )

    def _skip_sub_blocks(self, device: ReadOnlyBlockDevice, offset: int, limit: int) -> int:
        """Skip data sub-blocks until 0-length terminator. Returns new offset or -1 if truncated."""
        curr = offset
        while curr < limit:
            try:
                b = device.read_at(curr, 1)
            except DeviceReadError:
                return -1
            if not b:
                return -1
            sb_len = b[0]
            curr += 1
            if sb_len == 0:
                return curr
            curr += sb_len
        return -1
