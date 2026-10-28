"""Forensic validator for JPEG (Joint Photographic Experts Group) images."""

import hashlib
import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"

# Restart markers RST0..RST7 and TEM
_STANDALONE_MARKERS = {
    0xD8,  # SOI
    0xD9,  # EOI
    0x00,  # Escaped 0xFF inside entropy data
    0x01,  # TEM
    0xD0,
    0xD1,
    0xD2,
    0xD3,
    0xD4,
    0xD5,
    0xD6,
    0xD7,  # RST0..RST7
}

# Start of frame markers indicating actual image dimensions
_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


class JpegValidator(FormatValidator):
    """Walks raw JPEG marker streams and properly handles embedded EXIF thumbnails."""

    @property
    def format_name(self) -> str:
        return "JPEG"

    @property
    def default_extension(self) -> str:
        return "jpg"

    @property
    def magic_bytes(self) -> bytes:
        return _JPEG_SOI

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 50 * 1024 * 1024,  # 50 MiB max JPEG
    ) -> ValidationResult:
        max_len = min(device.size_bytes - header_offset, max_search_bytes)
        if max_len < 4:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max_len,
                extension=self.default_extension,
                notes="Too short to contain valid JPEG header",
            )

        try:
            initial_magic = device.read_at(header_offset, 2)
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Unreadable sector at header",
            )

        if initial_magic != _JPEG_SOI:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Invalid JPEG SOI marker",
            )

        current_offset = header_offset + 2
        has_sof = False
        has_sos = False
        inner_skip_ranges: list[tuple[int, int]] = []
        hasher = hashlib.sha256()
        hasher.update(_JPEG_SOI)

        while current_offset - header_offset < max_len:
            # Read next 2 bytes for marker
            bytes_left = max_len - (current_offset - header_offset)
            read_chunk_len = min(bytes_left, 4096)
            try:
                buf = device.read_at(current_offset, read_chunk_len)
            except DeviceReadError:
                return self._truncated_result(header_offset, current_offset, hasher, "Read error")

            if len(buf) < 2:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Unexpected EOF reading marker"
                )

            # Skip consecutive 0xFF padding bytes
            idx = 0
            while idx < len(buf) and buf[idx] == 0xFF:
                idx += 1

            if idx == 0 or idx >= len(buf):
                # Malformed marker stream or trailing padding
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Invalid marker alignment"
                )

            marker = buf[idx]
            current_offset += idx + 1

            # Check for EOI
            if marker == 0xD9:  # EOI
                total_size = current_offset - header_offset
                hasher.update(buf[: idx + 1])
                status = (
                    CandidateStatus.PREVIEW_VALIDATED
                    if has_sof and has_sos
                    else CandidateStatus.SIGNATURE_MATCHED
                )
                return ValidationResult(
                    status=status,
                    size_bytes=total_size,
                    extension=self.default_extension,
                    sha256=hasher.hexdigest(),
                    notes="Complete JPEG EOI marker found",
                    inner_ranges_to_skip=inner_skip_ranges,
                )

            # Standalone markers without payload length
            if marker in _STANDALONE_MARKERS:
                hasher.update(buf[: idx + 1])
                continue

            # Variable length marker: read 2-byte big-endian length
            len_offset = current_offset
            try:
                len_bytes = device.read_at(len_offset, 2)
            except DeviceReadError:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Read error on segment length"
                )

            if len(len_bytes) < 2:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Truncated segment length"
                )

            (seg_len,) = struct.unpack(">H", len_bytes)
            if seg_len < 2:
                return self._truncated_result(
                    header_offset, current_offset, hasher, f"Corrupt segment length: {seg_len}"
                )

            if marker in _SOF_MARKERS:
                has_sof = True
            elif marker == 0xDA:  # SOS (Start of Scan)
                has_sos = True

            # Record APP1 EXIF embedded thumbnail range to avoid re-carving inner thumbnail
            if marker == 0xE1:  # APP1
                inner_skip_ranges.append(
                    (len_offset - header_offset, len_offset - header_offset + seg_len)
                )

            # Read and hash the segment payload
            payload_to_read = min(seg_len, max_len - (len_offset - header_offset))
            try:
                seg_data = device.read_at(len_offset, payload_to_read)
            except DeviceReadError:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Read error in segment payload"
                )

            hasher.update(b"\xff" + bytes([marker]))
            hasher.update(seg_data)
            current_offset = len_offset + seg_len

            # If this was SOS (Start of Scan), entropy data follows until next marker
            if marker == 0xDA:
                entropy_result = self._scan_entropy_data(
                    device, current_offset, header_offset, max_len, hasher
                )
                if entropy_result is not None:
                    status, eoi_offset, notes = entropy_result
                    return ValidationResult(
                        status=status,
                        size_bytes=eoi_offset - header_offset,
                        extension=self.default_extension,
                        sha256=hasher.hexdigest(),
                        notes=notes,
                        inner_ranges_to_skip=inner_skip_ranges,
                    )
                else:
                    return self._truncated_result(
                        header_offset, current_offset, hasher, "Truncated entropy stream"
                    )

        return self._truncated_result(
            header_offset, current_offset, hasher, "Reached search limit before EOI"
        )

    def _scan_entropy_data(
        self,
        device: ReadOnlyBlockDevice,
        start_offset: int,
        header_offset: int,
        max_len: int,
        hasher: "hashlib._Hash",
    ) -> tuple[CandidateStatus, int, str] | None:
        """Scan through JPEG entropy-coded scan data for the terminating EOI marker."""
        curr = start_offset
        chunk_size = 64 * 1024

        while curr - header_offset < max_len:
            bytes_left = max_len - (curr - header_offset)
            to_read = min(chunk_size, bytes_left)
            try:
                chunk = device.read_at(curr, to_read)
            except DeviceReadError:
                return None

            if not chunk:
                return None

            pos = 0
            while True:
                ff_pos = chunk.find(b"\xff", pos)
                if ff_pos == -1 or ff_pos + 1 >= len(chunk):
                    # No marker in chunk, or 0xFF at very end
                    if ff_pos != -1 and ff_pos == len(chunk) - 1:
                        hasher.update(chunk[:ff_pos])
                        curr += ff_pos
                    else:
                        hasher.update(chunk)
                        curr += len(chunk)
                    break

                next_byte = chunk[ff_pos + 1]

                # If byte is 0x00 (escaped FF) or RST0..RST7 (0xD0..0xD7), continue scan
                if next_byte == 0x00 or (0xD0 <= next_byte <= 0xD7) or next_byte == 0xFF:
                    pos = ff_pos + 2
                    continue

                if next_byte == 0xD9:  # EOI!
                    eoi_offset = curr + ff_pos + 2
                    hasher.update(chunk[: ff_pos + 2])
                    return (CandidateStatus.PREVIEW_VALIDATED, eoi_offset, "Valid EOI reached")

                # Any other marker terminates the entropy scan
                pos = ff_pos + 2

        return None

    def _truncated_result(
        self,
        header_offset: int,
        current_offset: int,
        hasher: "hashlib._Hash",
        notes: str,
    ) -> ValidationResult:
        size = max(0, current_offset - header_offset)
        return ValidationResult(
            status=CandidateStatus.TRUNCATED,
            size_bytes=size,
            extension=self.default_extension,
            sha256=hasher.hexdigest(),
            notes=notes,
        )
