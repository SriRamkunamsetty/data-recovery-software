"""Synthetic disk image generator and image hash snapshot verification helper."""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SyntheticFile:
    """A file embedded within a synthetic disk image."""

    name: str
    content: bytes
    offset: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class SyntheticImageManifest:
    """Manifest describing a generated synthetic disk image."""

    image_path: Path
    total_size_bytes: int
    sector_size: int
    image_sha256: str
    files: list[SyntheticFile] = field(default_factory=list)

    def get_file(self, name: str) -> SyntheticFile:
        """Find synthetic file by name."""
        for f in self.files:
            if f.name == name:
                return f
        raise KeyError(f"File '{name}' not found in synthetic image manifest")


class SyntheticImageBuilder:
    """Builder for generating synthetic disk images with known files at specific offsets."""

    def __init__(
        self,
        total_size_bytes: int,
        sector_size: int = 512,
        fill_byte: bytes = b"\x00",
    ) -> None:
        if total_size_bytes <= 0:
            raise ValueError(f"total_size_bytes must be positive: {total_size_bytes}")
        if sector_size <= 0:
            raise ValueError(f"sector_size must be positive: {sector_size}")
        if len(fill_byte) != 1:
            raise ValueError("fill_byte must be a single byte")

        self.total_size_bytes = total_size_bytes
        self.sector_size = sector_size
        self.fill_byte = fill_byte
        self._files: list[SyntheticFile] = []
        self._raw_regions: list[tuple[int, bytes]] = []

    def add_file(self, name: str, content: bytes, offset: int) -> SyntheticFile:
        """Add a file to be placed at a specific byte offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if offset + len(content) > self.total_size_bytes:
            raise ValueError(
                f"File '{name}' of length {len(content)} at offset {offset} "
                f"exceeds image capacity ({self.total_size_bytes} bytes)"
            )

        file_sha256 = hashlib.sha256(content).hexdigest()
        syn_file = SyntheticFile(
            name=name,
            content=content,
            offset=offset,
            size_bytes=len(content),
            sha256=file_sha256,
        )
        self._files.append(syn_file)
        self._raw_regions.append((offset, content))
        return syn_file

    def add_raw(self, data: bytes, offset: int) -> None:
        """Add arbitrary raw byte sequence at a specific offset."""
        if offset < 0:
            raise ValueError(f"Offset cannot be negative: {offset}")
        if offset + len(data) > self.total_size_bytes:
            raise ValueError("Data exceeds image capacity")
        self._raw_regions.append((offset, data))

    def build(self, output_path: str | Path) -> SyntheticImageManifest:
        """Write the synthetic image to disk and return its manifest."""
        out_path = Path(output_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Build in-memory buffer or file depending on size
        with open(out_path, "wb") as f:
            # Create sparse / filled file of total_size_bytes
            f.seek(self.total_size_bytes - 1)
            f.write(self.fill_byte)
            f.seek(0)

            # Write raw regions and files
            for offset, data in self._raw_regions:
                f.seek(offset)
                f.write(data)

            f.flush()

        # Compute full image SHA-256
        hasher = hashlib.sha256()
        with open(out_path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)

        image_hash = hasher.hexdigest()
        return SyntheticImageManifest(
            image_path=out_path,
            total_size_bytes=self.total_size_bytes,
            sector_size=self.sector_size,
            image_sha256=image_hash,
            files=list(self._files),
        )


class ImageHashSnapshot:
    """Helper to take a cryptographic hash snapshot of an image and verify immutability."""

    def __init__(self, image_path: str | Path) -> None:
        self._path = Path(image_path).resolve()
        if not self._path.exists():
            raise FileNotFoundError(f"File not found: {self._path}")
        self._initial_size = os.path.getsize(self._path)
        self._initial_sha256 = self._compute_hash()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def initial_sha256(self) -> str:
        return self._initial_sha256

    @property
    def initial_size(self) -> int:
        return self._initial_size

    def _compute_hash(self) -> str:
        hasher = hashlib.sha256()
        with open(self._path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        return hasher.hexdigest()

    def verify_unchanged(self) -> bool:
        """Verify that size and SHA-256 have not changed since snapshot creation."""
        current_size = os.path.getsize(self._path)
        if current_size != self._initial_size:
            raise AssertionError(
                f"Image size modified! Initial: {self._initial_size}, current: {current_size}"
            )

        current_hash = self._compute_hash()
        if current_hash != self._initial_sha256:
            raise AssertionError(
                f"Image content modified! Initial SHA-256: {self._initial_sha256}, "
                f"current SHA-256: {current_hash}"
            )

        return True
