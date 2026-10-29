"""Declarative signature registry for file carving."""

from dataclasses import dataclass

from recoverx.carving.validators.base import FormatValidator
from recoverx.carving.validators.bmp import BmpValidator
from recoverx.carving.validators.gif import GifValidator
from recoverx.carving.validators.isobmff import IsoBmffValidator
from recoverx.carving.validators.jpeg import JpegValidator
from recoverx.carving.validators.mp3 import Mp3Validator
from recoverx.carving.validators.pdf import PdfValidator
from recoverx.carving.validators.png import PngValidator
from recoverx.carving.validators.riff import RiffValidator
from recoverx.carving.validators.sqlite import SqliteValidator
from recoverx.carving.validators.tiff_raw import TiffRawValidator
from recoverx.carving.validators.zip_ooxml import ZipValidator


@dataclass(frozen=True)
class FileSignature:
    """Declarative signature mapping magic bytes to a structural validator."""

    magic: bytes
    format_name: str
    validator: FormatValidator
    sector_aligned: bool = False  # If true, only matches at sector boundaries
    magic_offset: int = 0  # Offset of magic bytes from file start (e.g. 4 for ftyp)


class SignatureRegistry:
    """Registry maintaining active carving file signatures."""

    def __init__(self) -> None:
        self._signatures: list[FileSignature] = []

    def register(
        self,
        magic: bytes,
        validator: FormatValidator,
        sector_aligned: bool = False,
        magic_offset: int = 0,
    ) -> None:
        """Register a new signature rule."""
        self._signatures.append(
            FileSignature(
                magic=magic,
                format_name=validator.format_name,
                validator=validator,
                sector_aligned=sector_aligned,
                magic_offset=magic_offset,
            )
        )

    @property
    def signatures(self) -> list[FileSignature]:
        """List of all registered signatures."""
        return list(self._signatures)

    def get_validator_for_extension(self, extension: str) -> FormatValidator | None:
        """Lookup a format validator by file extension (without dot)."""
        ext = extension.lower().strip()
        for sig in self._signatures:
            fmt_lower = sig.validator.format_name.lower()
            if fmt_lower == ext:
                return sig.validator
            # Handle aliases
            if ext in ("jpg", "jpeg") and fmt_lower == "jpeg":
                return sig.validator
            if ext in ("zip", "docx", "xlsx", "pptx") and fmt_lower in ("zip", "ooxml"):
                return sig.validator
            if ext in ("mp4", "mov", "m4a", "heic") and fmt_lower in ("mp4", "mov", "heic"):
                return sig.validator
            if ext in ("wav", "avi", "webp") and fmt_lower in ("wav", "avi"):
                return sig.validator
            if ext in ("tif", "tiff", "cr2", "nef", "arw", "dng") and fmt_lower in ("raw", "tiff"):
                return sig.validator
            if ext in ("sqlite", "db", "sqlite3") and fmt_lower == "sqlite":
                return sig.validator
        return None

    @classmethod
    def default_registry(cls) -> "SignatureRegistry":
        """Construct the default registry with all first-set and second-set formats."""
        reg = cls()
        # First set (M3)
        reg.register(b"\xff\xd8", JpegValidator())
        reg.register(b"\x89PNG\r\n\x1a\n", PngValidator())
        reg.register(b"%PDF-", PdfValidator())
        reg.register(b"PK\x03\x04", ZipValidator())

        # Second set (M11 - SD cards, cameras, and multimedia)
        reg.register(b"ftyp", IsoBmffValidator("MP4"), magic_offset=4)
        reg.register(b"GIF8", GifValidator())
        reg.register(b"BM", BmpValidator())
        reg.register(b"RIFF", RiffValidator("WAV"))
        reg.register(b"ID3", Mp3Validator())
        reg.register(b"II*\x00", TiffRawValidator("RAW"))
        reg.register(b"MM\x00*", TiffRawValidator("RAW"))
        reg.register(b"SQLite format 3\x00", SqliteValidator())
        return reg
