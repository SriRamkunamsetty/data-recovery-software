"""Unit tests for file collision resolution and no-overwrite guarantees."""

from pathlib import Path

import pytest

from recoverx.config import CollisionPolicy
from recoverx.services.destination_validator import resolve_collision


def test_no_collision_returns_original_path(tmp_path: Path) -> None:
    target = tmp_path / "fresh_file.txt"
    resolved = resolve_collision(target, CollisionPolicy.RENAME)
    assert resolved == target


def test_rename_policy_increments_counter(tmp_path: Path) -> None:
    original = tmp_path / "document.pdf"
    original.write_bytes(b"EXISTING_1")

    # First collision -> document (1).pdf
    resolved_1 = resolve_collision(original, CollisionPolicy.RENAME)
    assert resolved_1 == tmp_path / "document (1).pdf"
    assert resolved_1 is not None
    resolved_1.write_bytes(b"EXISTING_2")

    # Second collision -> document (2).pdf
    resolved_2 = resolve_collision(original, CollisionPolicy.RENAME)
    assert resolved_2 == tmp_path / "document (2).pdf"


def test_case_insensitive_collision_detected(tmp_path: Path) -> None:
    """Verify that case differences (FILE.TXT vs file.txt) trigger collision handling."""
    existing = tmp_path / "IMAGE.PNG"
    existing.write_bytes(b"EXISTING_IMAGE")

    # Attempt to resolve lowercase 'image.png'
    incoming = tmp_path / "image.png"
    resolved = resolve_collision(incoming, CollisionPolicy.RENAME)

    # Must rename rather than clobbering existing file on case-insensitive filesystems
    assert resolved != incoming
    assert resolved == tmp_path / "image (1).png"


def test_skip_policy_returns_none(tmp_path: Path) -> None:
    existing = tmp_path / "existing.zip"
    existing.write_bytes(b"ORIGINAL_DATA")

    resolved = resolve_collision(existing, CollisionPolicy.SKIP)
    assert resolved is None
    # Existing file unmodified
    assert existing.read_bytes() == b"ORIGINAL_DATA"


def test_overwrite_never_policy_raises(tmp_path: Path) -> None:
    existing = tmp_path / "locked.bin"
    existing.write_bytes(b"KEEP_SAFE")

    with pytest.raises(FileExistsError, match="overwrite is strictly forbidden"):
        resolve_collision(existing, CollisionPolicy.OVERWRITE_NEVER)
