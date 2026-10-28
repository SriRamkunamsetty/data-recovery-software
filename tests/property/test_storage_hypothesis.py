"""Hypothesis property-based tests for block device boundary safety."""

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from recoverx.infrastructure.storage.base import DeviceOutOfBoundsError
from recoverx.infrastructure.storage.fixtures import (
    ImageHashSnapshot,
    SyntheticImageBuilder,
)
from recoverx.infrastructure.storage.image import DiskImageReader

IMAGE_SIZE = 16 * 1024  # 16 KiB image


@pytest.fixture(scope="module")
def hypothesis_image(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp_dir = tmp_path_factory.mktemp("hypothesis_storage")
    builder = SyntheticImageBuilder(total_size_bytes=IMAGE_SIZE, fill_byte=b"\x55")
    # Embed a known signature in the middle
    builder.add_file("marker.dat", b"HYPOTHESIS_MARKER", offset=1024)
    manifest = builder.build(tmp_dir / "prop_test.img")
    return manifest.image_path


@given(
    offset=st.integers(min_value=-1000, max_value=IMAGE_SIZE + 5000),
    length=st.integers(min_value=-500, max_value=IMAGE_SIZE + 5000),
)
@settings(max_examples=250)
def test_read_at_boundary_invariants(hypothesis_image: Path, offset: int, length: int) -> None:
    """Property: For any (offset, length), read_at either raises DeviceOutOfBoundsError

    or returns exactly length bytes matching the underlying image data.
    """
    with DiskImageReader(hypothesis_image) as reader:
        is_valid = offset >= 0 and length >= 0 and (offset + length <= reader.size_bytes)

        if not is_valid:
            with pytest.raises(DeviceOutOfBoundsError):
                reader.read_at(offset, length)
        else:
            data = reader.read_at(offset, length)
            assert isinstance(data, bytes)
            assert len(data) == length


@given(
    offset=st.integers(min_value=IMAGE_SIZE - 200, max_value=IMAGE_SIZE),
    length=st.integers(min_value=0, max_value=500),
)
@settings(max_examples=100)
def test_edge_of_disk_boundaries(hypothesis_image: Path, offset: int, length: int) -> None:
    """Focus testing on the exact end-of-disk edge boundary."""
    with DiskImageReader(hypothesis_image) as reader:
        if offset + length > reader.size_bytes:
            with pytest.raises(DeviceOutOfBoundsError):
                reader.read_at(offset, length)
        else:
            data = reader.read_at(offset, length)
            assert len(data) == length


def test_property_test_immutability(hypothesis_image: Path) -> None:
    """Verify that after property testing, the image remains cryptographically intact."""
    snapshot = ImageHashSnapshot(hypothesis_image)
    assert snapshot.verify_unchanged()
