"""TIFF and camera RAW (CR2, NEF, ARW, DNG) validator walking Image File Directories."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

# TIFF field type sizes
TIFF_TYPE_SIZES = {
    1: 1,  # BYTE
    2: 1,  # ASCII
    3: 2,  # SHORT
    4: 4,  # LONG
    5: 8,  # RATIONAL
    6: 1,  # SBYTE
    7: 1,  # UNDEFINED
    8: 2,  # SSHORT
    9: 4,  # SLONG
    10: 8,  # SRATIONAL
    11: 4,  # FLOAT
    12: 8,  # DOUBLE
}


class TiffRawValidator(FormatValidator):
    """Validator for TIFF and camera RAW files walking IFDs to determine true file size."""

    def __init__(self, target_format: str = "RAW") -> None:
        self._target_format = target_format.upper()

    @property
    def format_name(self) -> str:
        return self._target_format

    @property
    def default_extension(self) -> str:
        if self._target_format == "CR2":
            return "cr2"
        if self._target_format == "NEF":
            return "nef"
        if self._target_format == "ARW":
            return "arw"
        if self._target_format == "DNG":
            return "dng"
        return "tif"

    @property
    def magic_bytes(self) -> bytes:
        return b"II*\x00"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 200 * 1024 * 1024,  # 200 MiB limit
    ) -> ValidationResult:
        """Walk TIFF Image File Directories (IFDs) and find maximum referenced extent."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        try:
            head = device.read_at(header_offset, min(16, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading TIFF header",
            )

        if len(head) < 8:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(head),
                extension=self.default_extension,
                notes="Insufficient bytes for TIFF header",
            )

        byte_order_mark = head[:2]
        if byte_order_mark == b"II":
            endian = "<"
        elif byte_order_mark == b"MM":
            endian = ">"
        else:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=2,
                extension=self.default_extension,
                notes="Invalid TIFF byte order mark",
            )

        tiff_magic = struct.unpack(f"{endian}H", head[2:4])[0]
        if tiff_magic != 42:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=4,
                extension=self.default_extension,
                notes=f"Invalid TIFF magic number: {tiff_magic}",
            )

        # Detect Canon CR2: offset 8..12 contains b"CR\x02\x00"
        is_cr2 = False
        if len(head) >= 12 and head[8:12] == b"CR\x02\x00":
            is_cr2 = True

        first_ifd_offset = struct.unpack(f"{endian}I", head[4:8])[0]
        if first_ifd_offset < 8 or first_ifd_offset > max_search_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=8,
                extension=self.default_extension,
                notes=f"Invalid first IFD offset: {first_ifd_offset}",
            )

        limit_offset = min(device.size_bytes, header_offset + max_search_bytes)
        max_extent = max(16, first_ifd_offset)
        next_ifd = first_ifd_offset
        ifds_walked = 0
        detected_make = ""

        # Walk up to 10 IFD chains
        while next_ifd > 0 and ifds_walked < 10:
            ifds_walked += 1
            ifd_abs = header_offset + next_ifd
            if ifd_abs + 2 > limit_offset:
                break

            try:
                count_bytes = device.read_at(ifd_abs, 2)
            except DeviceReadError:
                break

            if len(count_bytes) < 2:
                break

            num_entries = struct.unpack(f"{endian}H", count_bytes)[0]
            if num_entries == 0 or num_entries > 4096:
                break

            ifd_size = 2 + (num_entries * 12) + 4
            if ifd_abs + ifd_size > limit_offset:
                max_extent = max(max_extent, next_ifd + ifd_size)
                break

            try:
                entries_data = device.read_at(ifd_abs + 2, num_entries * 12)
            except DeviceReadError:
                break

            max_extent = max(max_extent, next_ifd + ifd_size)
            strip_offsets: list[int] = []
            strip_counts: list[int] = []

            # Parse entries
            for i in range(num_entries):
                entry = entries_data[i * 12 : (i + 1) * 12]
                tag, field_type, count, val_or_offset = struct.unpack(f"{endian}HHI4s", entry)
                type_size = TIFF_TYPE_SIZES.get(field_type, 1)
                data_size = count * type_size

                val_offset = struct.unpack(f"{endian}I", val_or_offset)[0]
                if data_size > 4 and val_offset < max_search_bytes:
                    max_extent = max(max_extent, val_offset + data_size)

                    # Tag 0x010F = Make (camera manufacturer)
                    if tag == 0x010F and count < 64:
                        try:
                            make_bytes = device.read_at(header_offset + val_offset, min(count, 32))
                            detected_make = make_bytes.decode("ascii", errors="ignore").upper()
                        except Exception:
                            pass

                # StripOffsets (0x0111) or TileOffsets (0x0144)
                if tag in (0x0111, 0x0144):
                    if count == 1 and val_offset < max_search_bytes:
                        strip_offsets.append(val_offset)
                    elif count > 1 and val_offset < max_search_bytes:
                        try:
                            offs_raw = device.read_at(
                                header_offset + val_offset, min(count * 4, 1024)
                            )
                            for idx in range(0, len(offs_raw), 4):
                                if idx + 4 <= len(offs_raw):
                                    strip_offsets.append(
                                        struct.unpack(f"{endian}I", offs_raw[idx : idx + 4])[0]
                                    )
                        except Exception:
                            pass

                # StripByteCounts (0x0117) or TileByteCounts (0x0145)
                if tag in (0x0117, 0x0145):
                    if count == 1 and val_offset < max_search_bytes:
                        strip_counts.append(val_offset)
                    elif count > 1 and val_offset < max_search_bytes:
                        try:
                            cnts_raw = device.read_at(
                                header_offset + val_offset, min(count * 4, 1024)
                            )
                            for idx in range(0, len(cnts_raw), 4):
                                if idx + 4 <= len(cnts_raw):
                                    strip_counts.append(
                                        struct.unpack(f"{endian}I", cnts_raw[idx : idx + 4])[0]
                                    )
                        except Exception:
                            pass

            for s_off, s_cnt in zip(strip_offsets, strip_counts, strict=False):
                if s_off + s_cnt < max_search_bytes:
                    max_extent = max(max_extent, s_off + s_cnt)

            # Read next IFD offset
            try:
                next_ifd_bytes = device.read_at(ifd_abs + 2 + num_entries * 12, 4)
                next_ifd = struct.unpack(f"{endian}I", next_ifd_bytes)[0]
            except Exception:
                break

        # Classify extension
        extension = "tif"
        if is_cr2 or "CANON" in detected_make:
            extension = "cr2"
        elif "NIKON" in detected_make:
            extension = "nef"
        elif "SONY" in detected_make:
            extension = "arw"
        elif self._target_format in ("CR2", "NEF", "ARW", "DNG"):
            extension = self.default_extension

        total_size = min(max_extent, max_search_bytes)

        if ifds_walked > 0 and header_offset + total_size <= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.PREVIEW_VALIDATED,
                size_bytes=total_size,
                extension=extension,
                notes=f"Valid TIFF/RAW ({ifds_walked} IFDs, {extension.upper()}, {total_size} B)",
            )

        if ifds_walked > 0:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=min(total_size, device.size_bytes - header_offset),
                extension=extension,
                notes=f"Truncated TIFF/RAW file ({ifds_walked} IFDs parsed)",
            )

        return ValidationResult(
            status=CandidateStatus.SIGNATURE_MATCHED,
            size_bytes=max(max_extent, 8),
            extension=extension,
            notes="TIFF signature matched without verified IFD",
        )
