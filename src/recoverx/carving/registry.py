"""Declarative signature registry for file carving."""

from dataclasses import dataclass

from recoverx.carving.validators.base import FormatValidator
from recoverx.carving.validators.jpeg import JpegValidator
from recoverx.carving.validators.pdf import PdfValidator
from recoverx.carving.validators.png import PngValidator
from recoverx.carving.validators.zip_ooxml import ZipValidator


@dataclass(frozen=True)
class FileSignature:
    """Declarative signature mapping magic bytes to a structural validator."""

    magic: bytes
    format_name: str
    validator: FormatValidator
    sector_aligned: bool = False  # If true, only matches at sector boundaries


class SignatureRegistry:
    """Registry maintaining active carving file signatures."""

    def __init__(self) -> None:
        self._signatures: list[FileSignature] = []

    def register(
        self,
        magic: bytes,
        validator: FormatValidator,
        sector_aligned: bool = False,
    ) -> None:
        """Register a new signature rule."""
        self._signatures.append(
            FileSignature(
                magic=magic,
                format_name=validator.format_name,
                validator=validator,
                sector_aligned=sector_aligned,
            )
        )

    @property
    def signatures(self) -> list[FileSignature]:
        """List of all registered signatures."""
        return list(self._signatures)

    @classmethod
    def default_registry(cls) -> "SignatureRegistry":
        """Construct the default registry with Milestone M3 first-set formats."""
        reg = cls()
        reg.register(b"\xff\xd8", JpegValidator())
        reg.register(b"\x89PNG\r\n\x1a\n", PngValidator())
        reg.register(b"%PDF-", PdfValidator())
        reg.register(b"PK\x03\x04", ZipValidator())
        return reg
