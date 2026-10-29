"""Resource Interchange File Format (RIFF) validator for WAV and AVI files."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice


class RiffValidator(FormatValidator):
    """Structural validator for RIFF containers (WAV audio, AVI video)."""

    def __init__(self, target_format: str = "WAV") -> None:
        self._target_format = target_format.upper()

    @property
    def format_name(self) -> str:
        return self._target_format

    @property
    def default_extension(self) -> str:
        if self._target_format == "AVI":
            return "avi"
        return "wav"

    @property
    def magic_bytes(self) -> bytes:
        return b"RIFF"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 500 * 1024 * 1024,  # 500 MiB limit
    ) -> ValidationResult:
        """Walk RIFF header and verify chunk integrity."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        try:
            hdr = device.read_at(header_offset, min(12, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading RIFF header",
            )

        if len(hdr) < 12:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(hdr),
                extension=self.default_extension,
                notes="Insufficient bytes for RIFF header",
            )

        if hdr[:4] != b"RIFF":
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=4,
                extension=self.default_extension,
                notes="Invalid RIFF magic",
            )

        riff_payload_size = struct.unpack("<I", hdr[4:8])[0]
        riff_type = hdr[8:12]

        total_file_size = riff_payload_size + 8
        if total_file_size < 12 or total_file_size > max_search_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=12,
                extension=self.default_extension,
                notes=f"Implausible RIFF size: {total_file_size} bytes",
            )

        extension = self.default_extension
        if riff_type == b"WAVE":
            extension = "wav"
        elif riff_type == b"AVI ":
            extension = "avi"
        elif riff_type == b"WEBP":
            extension = "webp"
        else:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=12,
                extension=self.default_extension,
                notes=f"Unrecognized RIFF type: {riff_type!r}",
            )

        # Walk chunks
        curr_offset = header_offset + 12
        limit_offset = min(device.size_bytes, header_offset + total_file_size)
        has_fmt = False
        has_data = False
        has_hdrl = False
        chunks_walked = 0

        while curr_offset < limit_offset:
            bytes_left = limit_offset - curr_offset
            if bytes_left < 8:
                break

            try:
                chunk_hdr = device.read_at(curr_offset, min(12, bytes_left))
            except DeviceReadError:
                break

            if len(chunk_hdr) < 8:
                break

            chunk_id = chunk_hdr[:4]
            chunk_size = struct.unpack("<I", chunk_hdr[4:8])[0]

            if chunk_id == b"fmt ":
                has_fmt = True
            elif chunk_id == b"data":
                has_data = True
            elif chunk_id == b"LIST" and len(chunk_hdr) >= 12:
                list_type = chunk_hdr[8:12]
                if list_type in (b"hdrl", b"movi"):
                    has_hdrl = True

            chunks_walked += 1
            # Chunks in RIFF are word-aligned (padded to 2-byte boundary)
            padded_chunk_size = (chunk_size + 1) & ~1
            curr_offset += 8 + padded_chunk_size

        is_complete = header_offset + total_file_size <= device.size_bytes
        valid_structure = (
            (extension == "wav" and has_fmt and (has_data or chunks_walked >= 2))
            or (extension == "avi" and (has_hdrl or chunks_walked >= 2))
            or (extension == "webp" and chunks_walked >= 1)
        )

        type_str = riff_type.decode("ascii", errors="replace")
        if is_complete and valid_structure:
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=total_file_size,
                extension=extension,
                notes=f"Complete {type_str} file ({chunks_walked} chunks, {total_file_size} bytes)",
            )

        if valid_structure or chunks_walked > 0:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=min(total_file_size, device.size_bytes - header_offset),
                extension=extension,
                notes=f"Truncated {extension.upper()} file (found {chunks_walked} chunks)",
            )

        return ValidationResult(
            status=CandidateStatus.SIGNATURE_MATCHED,
            size_bytes=min(total_file_size, 12),
            extension=extension,
            notes="RIFF signature matched without verified chunks",
        )
