"""SQLite 3 database file validator."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

SQLITE_MAGIC = b"SQLite format 3\x00"


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


class SqliteValidator(FormatValidator):
    """Structural validator for SQLite 3 database files verifying header and page size."""

    @property
    def format_name(self) -> str:
        return "SQLite"

    @property
    def default_extension(self) -> str:
        return "sqlite"

    @property
    def magic_bytes(self) -> bytes:
        return SQLITE_MAGIC

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 500 * 1024 * 1024,  # 500 MiB limit
    ) -> ValidationResult:
        """Validate SQLite database 100-byte header and compute exact database size."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        try:
            hdr = device.read_at(header_offset, min(108, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading SQLite header",
            )

        if len(hdr) < 100:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(hdr),
                extension=self.default_extension,
                notes="Insufficient bytes for 100-byte SQLite header",
            )

        if hdr[:16] != SQLITE_MAGIC:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=16,
                extension=self.default_extension,
                notes="Invalid SQLite magic string",
            )

        raw_page_size = struct.unpack(">H", hdr[16:18])[0]
        page_size = 65536 if raw_page_size == 1 else raw_page_size

        if page_size < 512 or page_size > 65536 or not _is_power_of_two(page_size):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=18,
                extension=self.default_extension,
                notes=f"Invalid page size: {page_size}",
            )

        page_count = struct.unpack(">I", hdr[28:32])[0]
        text_encoding = struct.unpack(">I", hdr[56:60])[0]

        if text_encoding not in (1, 2, 3):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=60,
                extension=self.default_extension,
                notes=f"Invalid text encoding: {text_encoding}",
            )

        # Check B-tree page 1 header at offset 100
        page1_type = hdr[100]
        # 0x02 = interior index, 0x05 = interior table, 0x0A = leaf index, 0x0D = leaf table
        if page1_type not in (0x02, 0x05, 0x0A, 0x0D):
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=101,
                extension=self.default_extension,
                notes=f"Invalid page 1 B-tree type: 0x{page1_type:02X}",
            )

        total_size = page_size * max(1, page_count)
        if total_size > max_search_bytes:
            total_size = page_size

        if header_offset + total_size <= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=total_size,
                extension=self.default_extension,
                notes=f"Valid SQLite DB: {page_count} pages @ {page_size} B ({total_size} B)",
            )

        avail_bytes = device.size_bytes - header_offset
        return ValidationResult(
            status=CandidateStatus.TRUNCATED,
            size_bytes=avail_bytes,
            extension=self.default_extension,
            notes=f"Truncated SQLite DB (expected {total_size} B, got {avail_bytes} B)",
        )
