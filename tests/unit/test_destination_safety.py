"""Unit tests for destination path sanitization and source/destination separation."""

from pathlib import Path

import pytest

from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import (
    AmbiguousSeparationError,
    DestinationOnSourceError,
    FakeVolumeIdentityResolver,
)
from recoverx.services.destination_validator import (
    sanitize_filename,
    sanitize_relative_path,
    validate_destination_directory,
)


def test_sanitize_windows_reserved_device_names() -> None:
    """Verify that all 22 Windows reserved device names are safely rewritten."""
    reserved = ["CON", "PRN", "AUX", "NUL"]
    for i in range(1, 10):
        reserved.append(f"COM{i}")
        reserved.append(f"LPT{i}")

    for name in reserved:
        # Both bare name and name with extension must be rewritten
        assert sanitize_filename(name).startswith("_")
        assert sanitize_filename(f"{name}.txt").startswith("_")
        assert sanitize_filename(f"{name.lower()}.jpg").startswith("_")


def test_sanitize_illegal_characters_and_ads() -> None:
    """Verify illegal characters and Alternate Data Streams (:) are neutralized."""
    dirty = 'bad<file>:stream"name|test?star*.txt'
    clean = sanitize_filename(dirty)
    assert ":" not in clean
    assert "<" not in clean
    assert ">" not in clean
    assert '"' not in clean
    assert "|" not in clean
    assert "?" not in clean
    assert "*" not in clean


def test_sanitize_trailing_dots_and_spaces() -> None:
    """Verify trailing dots and spaces are stripped per Windows API rules."""
    assert sanitize_filename("document.txt...") == "document.txt"
    assert sanitize_filename("document.txt   ") == "document.txt"
    assert sanitize_filename("document.txt. . ") == "document.txt"


def test_sanitize_relative_path_traversal() -> None:
    """Verify path traversal attacks are neutralized."""
    evil_paths = [
        "../../etc/passwd",
        r"..\..\Windows\System32\cmd.exe",
        "/absolute/path/file.txt",
        "C:/Windows/win.ini",
        "subdir/../../../escape.bin",
    ]
    for evil in evil_paths:
        safe = sanitize_relative_path(evil)
        # Result must not contain ..
        assert ".." not in safe.parts
        # Result must be relative
        assert not safe.is_absolute()


def test_separation_enforcement_same_volume_refused(tmp_path: Path) -> None:
    """CLAUDE.md Rule 2: Destination on the same volume as the source must be strictly refused."""
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    manifest = builder.build(tmp_path / "source.img")

    resolver = FakeVolumeIdentityResolver()
    dest_dir = tmp_path / "recovered_output"
    dest_dir.mkdir()

    with DiskImageReader(manifest.image_path) as reader:
        # Register both source and destination on Volume "VOL-SOURCE-1"
        resolver.register_device_volume(reader, volume_id="VOL-SOURCE-1", physical_disk_number=1)
        resolver.register_path_volume(dest_dir, volume_id="VOL-SOURCE-1", physical_disk_number=2)

        with pytest.raises(DestinationOnSourceError, match="SAME VOLUME"):
            validate_destination_directory(
                destination=dest_dir,
                source_device=reader,
                resolver=resolver,
            )


def test_separation_enforcement_same_physical_disk_refused(tmp_path: Path) -> None:
    """CLAUDE.md Rule 2: Destination on the same physical disk must be strictly refused."""
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    manifest = builder.build(tmp_path / "source.img")

    resolver = FakeVolumeIdentityResolver()
    dest_dir = tmp_path / "recovered_output"
    dest_dir.mkdir()

    with DiskImageReader(manifest.image_path) as reader:
        # Different volumes, but SAME PHYSICAL DISK (Disk 2)
        resolver.register_device_volume(reader, volume_id="VOL-A", physical_disk_number=2)
        resolver.register_path_volume(dest_dir, volume_id="VOL-B", physical_disk_number=2)

        with pytest.raises(DestinationOnSourceError, match="SAME PHYSICAL DISK"):
            validate_destination_directory(
                destination=dest_dir,
                source_device=reader,
                resolver=resolver,
            )


def test_separation_enforcement_work_directory_on_source_refused(
    tmp_path: Path,
) -> None:
    """CLAUDE.md Rule 2: Work directory on the source device must also be strictly refused."""
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    manifest = builder.build(tmp_path / "source.img")

    resolver = FakeVolumeIdentityResolver()
    safe_dest = tmp_path / "safe_destination"
    safe_dest.mkdir()
    unsafe_work_dir = tmp_path / "unsafe_work"
    unsafe_work_dir.mkdir()

    with DiskImageReader(manifest.image_path) as reader:
        resolver.register_device_volume(reader, volume_id="VOL-SRC", physical_disk_number=1)
        resolver.register_path_volume(safe_dest, volume_id="VOL-SAFE", physical_disk_number=2)
        # Work dir on source volume
        resolver.register_path_volume(unsafe_work_dir, volume_id="VOL-SRC", physical_disk_number=1)

        with pytest.raises(DestinationOnSourceError, match="SAME VOLUME"):
            validate_destination_directory(
                destination=safe_dest,
                source_device=reader,
                resolver=resolver,
                work_directory=unsafe_work_dir,
            )


def test_ambiguous_separation_refused(tmp_path: Path) -> None:
    """CLAUDE.md Rule 3: If separation cannot be established with confidence, refuse."""
    builder = SyntheticImageBuilder(total_size_bytes=64 * 1024)
    manifest = builder.build(tmp_path / "source.img")

    resolver = FakeVolumeIdentityResolver()
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()

    with DiskImageReader(manifest.image_path) as reader:
        # Source has physical disk 1, but target has unknown disk (None)
        resolver.register_device_volume(reader, volume_id="VOL-SRC", physical_disk_number=1)
        resolver.register_path_volume(dest_dir, volume_id="VOL-UNK", physical_disk_number=None)

        with pytest.raises(
            AmbiguousSeparationError, match="Cannot establish physical disk identity"
        ):
            validate_destination_directory(
                destination=dest_dir,
                source_device=reader,
                resolver=resolver,
            )
