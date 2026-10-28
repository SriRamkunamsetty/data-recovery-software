"""Forensic validator for PDF (Portable Document Format) files."""

import hashlib
import re

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

_PDF_MAGIC = b"%PDF-"
_PDF_EOF = b"%%EOF"
_STARTXREF_RE = re.compile(rb"startxref\s+(\d+)\s+%%EOF", re.IGNORECASE)


class PdfValidator(FormatValidator):
    """Validates PDF documents by inspecting header, startxref, and %%EOF markers."""

    @property
    def format_name(self) -> str:
        return "PDF"

    @property
    def default_extension(self) -> str:
        return "pdf"

    @property
    def magic_bytes(self) -> bytes:
        return _PDF_MAGIC

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 100 * 1024 * 1024,  # 100 MiB max PDF
    ) -> ValidationResult:
        max_len = min(device.size_bytes - header_offset, max_search_bytes)
        if max_len < 10:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max_len,
                extension=self.default_extension,
                notes="Too short for PDF document",
            )

        try:
            magic = device.read_at(header_offset, 5)
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error on PDF header",
            )

        if magic != _PDF_MAGIC:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Invalid PDF magic signature",
            )

        # Stream forward in chunks to locate %%EOF markers, respecting incremental updates
        chunk_size = 64 * 1024
        curr_offset = header_offset
        last_valid_eof_offset: int | None = None

        overlap = 256  # Overlap to avoid splitting %%EOF or startxref across chunk boundaries
        prev_tail = b""

        while curr_offset - header_offset < max_len:
            bytes_left = max_len - (curr_offset - header_offset)
            to_read = min(chunk_size, bytes_left)
            try:
                chunk = device.read_at(curr_offset, to_read)
            except DeviceReadError:
                break

            if not chunk:
                break

            combined = prev_tail + chunk

            # Search for all %%EOF occurrences in this chunk window
            search_pos = 0
            while True:
                eof_pos = combined.find(_PDF_EOF, search_pos)
                if eof_pos == -1:
                    break

                # Found %%EOF. Calculate its file offset
                # The %%EOF is at combined[eof_pos : eof_pos + 5]
                # Look backwards up to 256 bytes for startxref
                window_start = max(0, eof_pos - 256)
                preceding_text = combined[window_start : eof_pos + 5]

                if _STARTXREF_RE.search(preceding_text) or b"trailer" in preceding_text:
                    # Calculate end offset including trailing newline
                    end_idx = eof_pos + 5
                    while end_idx < len(combined) and combined[end_idx] in (b"\r"[0], b"\n"[0]):
                        end_idx += 1

                    # File offset corresponding to end_idx in combined
                    # Note: combined = prev_tail + chunk
                    offset_in_chunk = end_idx - len(prev_tail)
                    file_offset = curr_offset + offset_in_chunk
                    last_valid_eof_offset = file_offset

                search_pos = eof_pos + 5

            curr_offset += len(chunk)
            prev_tail = chunk[-overlap:] if len(chunk) >= overlap else chunk

        if last_valid_eof_offset is not None and last_valid_eof_offset > header_offset:
            total_size = last_valid_eof_offset - header_offset
            # Compute hash of the exact validated range
            range_hasher = self._hash_range(device, header_offset, total_size)
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=total_size,
                extension=self.default_extension,
                sha256=range_hasher.hexdigest() if range_hasher else None,
                notes="Valid PDF structure with verified startxref and %%EOF",
            )

        # Header was matched but no valid %%EOF found
        return ValidationResult(
            status=CandidateStatus.TRUNCATED,
            size_bytes=max_len,
            extension=self.default_extension,
            notes="PDF header found but missing valid %%EOF",
        )

    def _hash_range(
        self, device: ReadOnlyBlockDevice, offset: int, length: int
    ) -> "hashlib._Hash | None":
        hasher = hashlib.sha256()
        chunk_size = 64 * 1024
        curr = offset
        while curr < offset + length:
            to_read = min(chunk_size, (offset + length) - curr)
            try:
                data = device.read_at(curr, to_read)
            except DeviceReadError:
                return None
            hasher.update(data)
            curr += len(data)
        return hasher
