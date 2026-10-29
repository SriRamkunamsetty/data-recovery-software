"""ISO Base Media File Format validator for MP4, MOV, and HEIC files."""

import struct

from recoverx.carving.validators.base import FormatValidator, ValidationResult
from recoverx.domain.enums import CandidateStatus
from recoverx.infrastructure.storage.base import DeviceReadError, ReadOnlyBlockDevice

# Common ISOBMFF top-level box types
KNOWN_BOX_TYPES: frozenset[bytes] = frozenset(
    [
        b"ftyp",
        b"moov",
        b"mdat",
        b"free",
        b"skip",
        b"wide",
        b"meta",
        b"idat",
        b"uuid",
        b"pdin",
        b"styp",
        b"prft",
    ]
)

HEIC_BRANDS: frozenset[bytes] = frozenset(
    [
        b"heic",
        b"heix",
        b"heim",
        b"heis",
        b"mif1",
        b"msf1",
        b"hevc",
        b"hevx",
    ]
)


class IsoBmffValidator(FormatValidator):
    """Structural validator for ISOBMFF containers (MP4, MOV, HEIC)."""

    def __init__(self, target_format: str = "MP4") -> None:
        self._target_format = target_format.upper()

    @property
    def format_name(self) -> str:
        return self._target_format

    @property
    def default_extension(self) -> str:
        if self._target_format == "HEIC":
            return "heic"
        if self._target_format == "MOV":
            return "mov"
        return "mp4"

    @property
    def magic_bytes(self) -> bytes:
        return b"ftyp"

    def validate(
        self,
        device: ReadOnlyBlockDevice,
        header_offset: int,
        max_search_bytes: int = 500 * 1024 * 1024,  # 500 MiB limit
    ) -> ValidationResult:
        """Walk the atom box tree from header_offset."""
        if header_offset < 0 or header_offset >= device.size_bytes:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Offset out of device bounds",
            )

        # Read first box header (must be ftyp at header_offset)
        try:
            head_bytes = device.read_at(header_offset, min(64, device.size_bytes - header_offset))
        except DeviceReadError:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=0,
                extension=self.default_extension,
                notes="Read error reading initial box header",
            )

        if len(head_bytes) < 8:
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=len(head_bytes),
                extension=self.default_extension,
                notes="Insufficient bytes for ISOBMFF header",
            )

        first_size = struct.unpack(">I", head_bytes[:4])[0]
        first_type = head_bytes[4:8]
        if first_type != b"ftyp" or first_size < 8:
            return ValidationResult(
                status=CandidateStatus.SIGNATURE_MATCHED,
                size_bytes=8,
                extension=self.default_extension,
                notes=f"First box is not valid ftyp: {first_type!r}",
            )

        # Determine extension from ftyp brands
        extension = self.default_extension
        if len(head_bytes) >= 12:
            major_brand = head_bytes[8:12]
            if major_brand in HEIC_BRANDS or any(
                b in head_bytes[16:first_size] for b in HEIC_BRANDS
            ):
                extension = "heic"
            elif major_brand == b"qt  ":
                extension = "mov"
            elif major_brand == b"M4A ":
                extension = "m4a"
            else:
                extension = "mp4"

        # Walk top-level boxes
        curr_offset = header_offset
        limit_offset = min(device.size_bytes, header_offset + max_search_bytes)
        has_moov = False
        has_mdat = False
        has_meta = False
        boxes_walked = 0
        total_size = 0

        while curr_offset < limit_offset:
            bytes_left = limit_offset - curr_offset
            if bytes_left < 8:
                # Incomplete box header at EOF -> Truncated
                total_size = curr_offset - header_offset + bytes_left
                rel_off = curr_offset - header_offset
                return ValidationResult(
                    status=CandidateStatus.TRUNCATED,
                    size_bytes=total_size,
                    extension=extension,
                    notes=f"Stream truncated inside box header at relative offset {rel_off}",
                )

            try:
                hdr = device.read_at(curr_offset, min(16, bytes_left))
            except DeviceReadError:
                total_size = curr_offset - header_offset
                return ValidationResult(
                    status=CandidateStatus.TRUNCATED,
                    size_bytes=total_size,
                    extension=extension,
                    notes=f"Read error at relative offset {curr_offset - header_offset}",
                )

            box_size = struct.unpack(">I", hdr[:4])[0]
            box_type = hdr[4:8]

            hdr_size = 8
            if box_size == 1:
                # 64-bit largesize
                if len(hdr) < 16:
                    return ValidationResult(
                        status=CandidateStatus.TRUNCATED,
                        size_bytes=curr_offset - header_offset + len(hdr),
                        extension=extension,
                        notes="Truncated 64-bit largesize box header",
                    )
                box_size = struct.unpack(">Q", hdr[8:16])[0]
                hdr_size = 16
            elif box_size == 0:
                # Atom goes to end of file
                box_size = bytes_left

            if box_size < hdr_size:
                # Corrupt box size
                break

            # Check for non-ASCII or corrupt box type
            if not all(32 <= b <= 126 for b in box_type):
                break

            if box_type == b"moov":
                has_moov = True
            elif box_type == b"mdat":
                has_mdat = True
            elif box_type == b"meta":
                has_meta = True

            boxes_walked += 1
            curr_offset += box_size

            # If curr_offset exceeded limit, file is truncated
            if curr_offset > device.size_bytes:
                b_name = box_type.decode("latin1", errors="replace")
                return ValidationResult(
                    status=CandidateStatus.TRUNCATED,
                    size_bytes=device.size_bytes - header_offset,
                    extension=extension,
                    notes=f"Box {b_name} extends beyond device size",
                )

            # Heic files often only have ftyp + meta + mdat
            if extension == "heic" and has_meta and has_mdat:
                # HEIC container is structurally complete
                total_size = curr_offset - header_offset
                return ValidationResult(
                    status=CandidateStatus.PREVIEW_VALIDATED,
                    size_bytes=total_size,
                    extension=extension,
                    notes=f"Complete HEIC container ({boxes_walked} boxes)",
                )

            # MP4/MOV files require both moov and mdat for full playback
            if has_moov and has_mdat:
                total_size = curr_offset - header_offset
                return ValidationResult(
                    status=CandidateStatus.PREVIEW_VALIDATED,
                    size_bytes=total_size,
                    extension=extension,
                    notes=f"Complete ISOBMFF container ({boxes_walked} boxes, moov + mdat)",
                )

        total_size = curr_offset - header_offset
        if boxes_walked > 0 and (has_moov or has_mdat or has_meta):
            return ValidationResult(
                status=CandidateStatus.TRUNCATED,
                size_bytes=max(total_size, 8),
                extension=extension,
                notes=f"Truncated container after {boxes_walked} boxes",
            )

        return ValidationResult(
            status=CandidateStatus.SIGNATURE_MATCHED,
            size_bytes=max(total_size, 8),
            extension=extension,
            notes="Signature matched but incomplete box sequence",
        )
