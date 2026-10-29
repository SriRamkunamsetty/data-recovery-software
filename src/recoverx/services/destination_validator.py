"""Path sanitization, Windows reserved name handling, and destination validation."""

import os
import re
from pathlib import Path

from recoverx.config import CollisionPolicy
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import (
    DestinationOnSourceError,
    VolumeIdentityResolver,
)

# Reserved Windows device names (case-insensitive)
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Illegal characters for Windows filenames: < > : " / \ | ? * and ASCII 0-31
_ILLEGAL_CHAR_REGEX = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


def sanitize_filename(name: str, fallback_prefix: str = "recovered_file") -> str:
    """Sanitize a filename component according to Windows and forensic rules.

    - Rewrites Windows reserved device names (e.g., CON.txt -> _CON.txt).
    - Neutralizes illegal characters and Alternate Data Streams (:).
    - Strips trailing dots and spaces.
    - Ensures non-empty result.
    """
    if not name or not name.strip():
        return fallback_prefix

    # Replace illegal characters (including :) with underscores
    cleaned = _ILLEGAL_CHAR_REGEX.sub("_", name)

    # Windows filenames cannot end in a period or a space
    cleaned = cleaned.rstrip(". ")

    if not cleaned:
        return fallback_prefix

    # Check reserved device names (checked against base name before the first dot)
    base_stem = cleaned.split(".")[0].upper()
    if base_stem in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    return cleaned


def sanitize_relative_path(rel_path: str, default_filename: str = "recovered_file") -> Path:
    """Sanitize a relative directory path and filename to strictly prevent traversal.

    Neutralizes '../', '..\\', absolute path components, drive letters, and reserved names.
    """
    # Replace backslashes with forward slashes for uniform splitting
    normalized = rel_path.replace("\\", "/").strip()

    # Strip leading drive letters (e.g. C:/ or D:/)
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[2:]

    parts = [p.strip() for p in normalized.split("/") if p.strip()]

    safe_parts: list[str] = []
    for part in parts:
        # Prevent path traversal
        if part in (".", ".."):
            continue
        safe_part = sanitize_filename(part)
        if safe_part:
            safe_parts.append(safe_part)

    if not safe_parts:
        return Path(default_filename)

    return Path(*safe_parts)


def resolve_collision(
    target_path: Path,
    policy: CollisionPolicy = CollisionPolicy.RENAME,
) -> Path | None:
    """Resolve file existence collisions in a case-insensitive manner.

    Returns:
        Path: Target path to write to (potentially renamed).
        None: If policy is SKIP and file exists.
    Raises:
        FileExistsError: If policy is OVERWRITE_NEVER and file exists.
    """
    if not _case_insensitive_exists(target_path):
        return target_path

    if policy == CollisionPolicy.SKIP:
        return None

    if policy == CollisionPolicy.OVERWRITE_NEVER:
        raise FileExistsError(
            f"Destination file already exists and overwrite is strictly forbidden: {target_path}"
        )

    # RENAME policy: generate file (1).ext, file (2).ext, etc.
    parent = target_path.parent
    stem = target_path.stem
    ext = target_path.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){ext}"
        if not _case_insensitive_exists(candidate):
            return candidate
        counter += 1


def _case_insensitive_exists(path: Path) -> bool:
    """Check if path exists on disk, accounting for case-insensitive filesystems."""
    if path.exists():
        return True

    parent = path.parent
    if not parent.exists():
        return False

    target_name_lower = path.name.lower()
    try:
        for entry in os.scandir(parent):
            if entry.name.lower() == target_name_lower:
                return True
    except OSError:
        return False

    return False


def validate_destination_directory(
    destination: Path | str,
    source_device: ReadOnlyBlockDevice,
    resolver: VolumeIdentityResolver,
    work_directory: Path | str | None = None,
) -> Path:
    """Validate destination and work directory separation from the source device.

    Verifies write permissions and directory creation.
    Raises:
        DestinationOnSourceError: If destination or work directory is on source disk/volume.
        AmbiguousSeparationError: If separation cannot be verified.
        PermissionError: If destination is not writable.
    """
    dest_path = Path(destination).resolve()

    # 0. Check if destination contains the source image file or is on its direct path
    source_path_str = getattr(source_device.device_info, "source_path", None)
    if source_path_str:
        try:
            source_file = Path(source_path_str).resolve()
            if source_file.is_file() and (
                dest_path == source_file
                or dest_path == source_file.parent
                or dest_path in source_file.parents
            ):
                raise DestinationOnSourceError(
                    f"Destination directory '{dest_path}' contains or matches the source "
                    f"image path '{source_file}'. Refused to prevent corrupting source image."
                )
        except Exception as e:
            if isinstance(e, DestinationOnSourceError):
                raise

    # Ensure destination directory exists or can be created
    try:
        dest_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise PermissionError(
            f"Cannot create or access destination directory '{dest_path}': {e}"
        ) from e

    # 1. Enforce strict destination separation from source
    resolver.verify_separation(source_device, dest_path, role="destination directory")

    # 2. Enforce strict work directory separation from source
    if work_directory is not None:
        work_path = Path(work_directory).resolve()
        resolver.verify_separation(source_device, work_path, role="work directory")

    # 3. Test write permissions in destination directory
    test_probe = dest_path / f".recoverx_probe_{os.getpid()}"
    try:
        with open(test_probe, "wb") as f:
            f.write(b"probe")
        test_probe.unlink()
    except OSError as e:
        raise PermissionError(f"Destination directory '{dest_path}' is not writable: {e}") from e

    return dest_path
