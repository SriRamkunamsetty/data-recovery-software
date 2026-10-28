"""Forensic validator for ZIP archives and ZIP-based Office OpenXML documents (DOCX, XLSX, PPTX)."""

import hashlib
import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

_ZIP_LOCAL_HEADER_MAGIC = b"PK\x03\x04"
_ZIP_CENTRAL_DIR_MAGIC = b"PK\x01\x02"
_ZIP_EOCD_MAGIC = b"PK\x05\x06"

# Zip-bomb protection ceilings
_MAX_CENTRAL_ENTRIES = 50_000
_MAX_UNCOMPRESSED_RATIO = 200.0


class ZipValidator(FormatValidator):
    """Validates ZIP archives, parses EOCD, and classifies OOXML documents."""

    @property
    def format_name(self) -> str:
        return "ZIP/Office"

    @property
    def default_extension(self) -> str:
        return "zip"

    @property
    def magic_bytes(self) -> bytes:
        return _ZIP_LOCAL_HEADER_MAGIC

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 100 * 1024 * 1024,  # 100 MiB max ZIP
    ) -> ValidationResult:
        max_len = min(device.size_bytes - header_offset, max_search_bytes)
        if max_len < 22:  # 22 is minimum empty ZIP size (EOCD alone)
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max_len,
                extension=self.default_extension,
                notes="Too short for ZIP structure",
            )

        try:
            magic = device.read_at(header_offset, 4)
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error on ZIP local header",
            )

        if magic != _ZIP_LOCAL_HEADER_MAGIC:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Invalid ZIP local header magic",
            )

        # To find EOCD, we can search backwards from search boundary or stream forward
        # Because EOCD is at the end, search backwards from min(max_len, file end)
        # EOCD is at least 22 bytes and has max 65535 comment length
        eocd_result = self._locate_eocd(device, header_offset, max_len)
        if eocd_result is None:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max_len,
                extension=self.default_extension,
                notes="ZIP local header found but missing End of Central Directory (EOCD)",
            )

        eocd_rel_offset, eocd_data = eocd_result

        # Parse EOCD:
        # 4 bytes: signature (PK\x05\x06)
        # 2 bytes: disk number
        # 2 bytes: disk with CD
        # 2 bytes: CD entries on this disk
        # 2 bytes: total CD entries
        # 4 bytes: size of CD
        # 4 bytes: offset of CD w.r.t start of archive
        # 2 bytes: comment length
        if len(eocd_data) < 22:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=eocd_rel_offset,
                extension=self.default_extension,
                notes="Truncated EOCD header",
            )

        (
            _,
            _disk_num,
            _cd_disk,
            _entries_disk,
            total_entries,
            cd_size,
            cd_offset,
            comment_len,
        ) = struct.unpack("<4sHHHHIIH", eocd_data[:22])

        total_file_size = eocd_rel_offset + 22 + comment_len
        if total_file_size > max_len:
            total_file_size = max_len

        # Zip-bomb check 1: entry count
        if total_entries > _MAX_CENTRAL_ENTRIES:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=total_file_size,
                extension=self.default_extension,
                notes=f"Exceeded safe central directory entry limit: {total_entries}",
            )

        # Validate Central Directory entries and classify OOXML
        entry_names: list[str] = []
        is_cd_valid = False
        if cd_offset + cd_size <= eocd_rel_offset:
            is_cd_valid, entry_names = self._parse_central_directory(
                device, header_offset + cd_offset, cd_size, total_entries
            )

        extension = self._classify_ooxml(entry_names)

        # Hash range
        hasher = self._hash_range(device, header_offset, total_file_size)

        status = (
            CandidateStatus.PREVIEW_VALIDATED if is_cd_valid else CandidateStatus.SIGNATURE_MATCHED
        )
        return ValidationResult(
            status=status,
            size_bytes=total_file_size,
            extension=extension,
            sha256=hasher.hexdigest() if hasher else None,
            notes=f"ZIP archive with {total_entries} entries, classified as {extension.upper()}",
        )

    def _locate_eocd(
        self, device: ReadOnlyBlockDevice, header_offset: int, max_len: int
    ) -> tuple[int, bytes] | None:
        """Locate EOCD record within the archive window."""
        # EOCD is within the last 65535 + 22 bytes of the archive
        search_window = min(max_len, 65535 + 22)
        window_start = header_offset + max_len - search_window

        try:
            buf = device.read_at(window_start, search_window)
        except DeviceReadError:
            # If unable to read tail, try progressive forward scan
            return self._forward_eocd_scan(device, header_offset, max_len)

        # Search backwards for PK\x05\x06
        idx = buf.rfind(_ZIP_EOCD_MAGIC)
        if idx != -1:
            rel_offset = (window_start - header_offset) + idx
            return (rel_offset, buf[idx:])

        # Fallback to forward scan
        return self._forward_eocd_scan(device, header_offset, max_len)

    def _forward_eocd_scan(
        self, device: ReadOnlyBlockDevice, header_offset: int, max_len: int
    ) -> tuple[int, bytes] | None:
        chunk_size = 64 * 1024
        curr = header_offset
        last_found: tuple[int, bytes] | None = None
        overlap = 22
        prev_tail = b""

        while curr - header_offset < max_len:
            to_read = min(chunk_size, max_len - (curr - header_offset))
            try:
                chunk = device.read_at(curr, to_read)
            except DeviceReadError:
                break
            if not chunk:
                break

            combined = prev_tail + chunk
            pos = 0
            while True:
                pos = combined.find(_ZIP_EOCD_MAGIC, pos)
                if pos == -1:
                    break
                file_rel = (curr - header_offset - len(prev_tail)) + pos
                last_found = (file_rel, combined[pos:])
                pos += 4

            curr += len(chunk)
            prev_tail = chunk[-overlap:] if len(chunk) >= overlap else chunk

        return last_found

    def _parse_central_directory(
        self,
        device: ReadOnlyBlockDevice,
        cd_absolute_offset: int,
        cd_size: int,
        total_entries: int,
    ) -> tuple[bool, list[str]]:
        """Walk central directory records to collect filenames and check sanity."""
        try:
            cd_data = device.read_at(cd_absolute_offset, cd_size)
        except DeviceReadError:
            return (False, [])

        names: list[str] = []
        pos = 0
        count = 0
        total_uncompressed = 0
        total_compressed = 0

        while pos < len(cd_data) and count < total_entries:
            if cd_data[pos : pos + 4] != _ZIP_CENTRAL_DIR_MAGIC:
                break

            if pos + 46 > len(cd_data):
                break

            # 46 bytes fixed header
            (
                _,
                _,
                _,
                _,
                _,
                _,
                _,
                _,
                comp_size,
                uncomp_size,
                name_len,
                extra_len,
                comment_len,
                _,
                _,
                _,
                _,
            ) = struct.unpack("<4sHHHHHHIIIHHHHHII", cd_data[pos : pos + 46])

            total_compressed += comp_size
            total_uncompressed += uncomp_size

            name_start = pos + 46
            name_end = name_start + name_len
            if name_end <= len(cd_data):
                file_name = cd_data[name_start:name_end].decode("utf-8", errors="replace")
                names.append(file_name)

            pos += 46 + name_len + extra_len + comment_len
            count += 1

        # Check zip bomb ratio
        if total_compressed > 0 and (
            total_uncompressed / total_compressed > _MAX_UNCOMPRESSED_RATIO
        ):
            return (False, names)

        return (count == total_entries, names)

    def _classify_ooxml(self, entry_names: list[str]) -> str:
        """Classify archive into docx, xlsx, pptx, epub, or standard zip."""
        has_content_types = any("[Content_Types].xml" in name for name in entry_names)
        if has_content_types:
            if any(name.startswith("word/") for name in entry_names):
                return "docx"
            if any(name.startswith("xl/") for name in entry_names):
                return "xlsx"
            if any(name.startswith("ppt/") for name in entry_names):
                return "pptx"
            return "docx"

        if any("mimetype" in name for name in entry_names):
            return "epub"

        return "zip"

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
