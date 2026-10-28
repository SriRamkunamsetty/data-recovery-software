"""Forensic validator for PNG (Portable Network Graphics) images."""

import hashlib
import struct
import zlib

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class PngValidator(FormatValidator):
    """Walks raw PNG chunk streams, validates chunk CRCs, and confirms IEND."""

    @property
    def format_name(self) -> str:
        return "PNG"

    @property
    def default_extension(self) -> str:
        return "png"

    @property
    def magic_bytes(self) -> bytes:
        return _PNG_MAGIC

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 50 * 1024 * 1024,  # 50 MiB max PNG
    ) -> ValidationResult:
        max_len = min(device.size_bytes - header_offset, max_search_bytes)
        if max_len < 8:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max_len,
                extension=self.default_extension,
                notes="Too short for PNG header",
            )

        try:
            magic = device.read_at(header_offset, 8)
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error on PNG magic header",
            )

        if magic != _PNG_MAGIC:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Invalid PNG magic header",
            )

        current_offset = header_offset + 8
        hasher = hashlib.sha256()
        hasher.update(_PNG_MAGIC)

        first_chunk = True
        has_idat = False

        while current_offset - header_offset < max_len:
            # Each chunk header is 8 bytes: 4 bytes length, 4 bytes chunk type
            bytes_left = max_len - (current_offset - header_offset)
            if bytes_left < 12:  # Min chunk (0 length data + 4 bytes CRC = 12 bytes)
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Unexpected EOF reading chunk header"
                )

            try:
                chunk_header = device.read_at(current_offset, 8)
            except DeviceReadError:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Read error reading chunk header"
                )

            data_length, chunk_type = struct.unpack(">I4s", chunk_header)

            if first_chunk:
                if chunk_type != b"IHDR" or data_length != 13:
                    return self._truncated_result(
                        header_offset,
                        current_offset,
                        hasher,
                        f"First chunk must be IHDR(13), got {chunk_type!r}({data_length})",
                    )
                first_chunk = False

            if chunk_type == b"IDAT":
                has_idat = True

            # Total chunk length = 8 (header) + data_length + 4 (CRC)
            total_chunk_bytes = 8 + data_length + 4
            if current_offset - header_offset + total_chunk_bytes > max_len:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Chunk data extends beyond file bounds"
                )

            # Read chunk payload + CRC
            try:
                payload_and_crc = device.read_at(current_offset + 8, data_length + 4)
            except DeviceReadError:
                return self._truncated_result(
                    header_offset, current_offset, hasher, "Read error in chunk payload"
                )

            chunk_data = payload_and_crc[:data_length]
            (expected_crc,) = struct.unpack(">I", payload_and_crc[data_length:])

            # Verify CRC (calculated over chunk_type + chunk_data)
            actual_crc = zlib.crc32(chunk_type + chunk_data)
            if actual_crc != expected_crc:
                return self._truncated_result(
                    header_offset,
                    current_offset,
                    hasher,
                    f"CRC mismatch in chunk {chunk_type.decode('latin1', errors='replace')}: "
                    f"expected 0x{expected_crc:08X}, got 0x{actual_crc:08X}",
                )

            # Update hash and advance
            hasher.update(chunk_header)
            hasher.update(payload_and_crc)
            current_offset += total_chunk_bytes

            # Check for IEND
            if chunk_type == b"IEND":
                total_file_size = current_offset - header_offset
                status = (
                    CandidateStatus.PREVIEW_VALIDATED
                    if has_idat
                    else CandidateStatus.SIGNATURE_MATCHED
                )
                return ValidationResult(
                    status=status,
                    size_bytes=total_file_size,
                    extension=self.default_extension,
                    sha256=hasher.hexdigest(),
                    notes="Complete PNG structure with valid CRCs and IEND",
                )

        return self._truncated_result(
            header_offset, current_offset, hasher, "Search limit reached before IEND"
        )

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
