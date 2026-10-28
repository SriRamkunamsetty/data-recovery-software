"""Unit tests for DiskImagingService multi-pass acquisition and safety guarantees."""

import hashlib
from pathlib import Path

import pytest

from recoverx.domain.imaging import ImagingConfig, SectorStatus
from recoverx.infrastructure.storage.fault import ByteRange, FaultConfig, FaultInjectionReader
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.range_map import RangeStatusMap
from recoverx.infrastructure.storage.resolver import (
    DestinationOnSourceError,
    FakeVolumeIdentityResolver,
)
from recoverx.services.disk_imaging_service import (
    DiskImagingService,
    ImagingCancelledError,
    ResumeIdentityMismatchError,
)


def _create_source_image(path: Path, size_bytes: int = 128 * 1024) -> str:
    """Create a test source image filled with recognizable pattern."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pattern = b"RECOVERX_SOURCE_RAW_PATTERN_"
    data = (pattern * ((size_bytes // len(pattern)) + 1))[:size_bytes]
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def test_clean_imaging_healthy_device(tmp_path: Path) -> None:
    src_path = tmp_path / "source.img"
    src_hash = _create_source_image(src_path, size_bytes=64 * 1024)
    dest_path = tmp_path / "dest" / "acquired.img"

    resolver = FakeVolumeIdentityResolver()
    service = DiskImagingService(resolver=resolver)

    with DiskImageReader(src_path) as reader:
        result = service.acquire_image(
            source_device=reader,
            destination_image_path=dest_path,
        )

        assert result.is_complete is True
        assert result.bad_sectors == 0
        assert result.finished_sectors == reader.total_sectors
        assert result.sha256_hash == src_hash

        # Verify acquired image bytes match source bit-for-bit
        assert dest_path.read_bytes() == src_path.read_bytes()

        # Check sidecar files exist
        assert result.metadata_path.exists()
        assert result.map_path.exists()

        # Load range map and verify 100% finished
        rmap = RangeStatusMap.load_file(result.map_path)
        assert rmap.is_all_finished is True


def test_faulty_device_sector_precision_and_incomplete(tmp_path: Path) -> None:
    """Bad ranges found to sector precision; incomplete run never reported complete."""
    src_path = tmp_path / "faulty_source.img"
    _create_source_image(src_path, size_bytes=64 * 1024)  # 128 sectors of 512B
    dest_path = tmp_path / "dest" / "faulty_acquired.img"

    # Inject unreadable fault exactly at sectors 10 and 11 (bytes 5120 to 6144)
    bad_byte_range = ByteRange(10 * 512, 12 * 512)
    fault_cfg = FaultConfig(unreadable_ranges=[bad_byte_range])

    resolver = FakeVolumeIdentityResolver()
    service = DiskImagingService(resolver=resolver)

    with DiskImageReader(src_path) as base_reader:
        fault_reader = FaultInjectionReader(base_reader, config=fault_cfg)

        img_cfg = ImagingConfig(
            block_size_bytes=4096,  # 8 sectors per block in copy pass
            initial_skip_sectors=8,
            enable_trim_pass=True,
            enable_scrape_pass=True,
        )

        result = service.acquire_image(
            source_device=fault_reader,
            destination_image_path=dest_path,
            config=img_cfg,
        )

        # Acceptance: an acquisition with unreadable ranges is NEVER reported complete
        assert result.is_complete is False
        # Acceptance: bad ranges are found to sector precision (exactly 2 sectors: 10 and 11)
        assert result.bad_sectors == 2
        assert result.finished_sectors == 126

        # Check range map contents
        rmap = RangeStatusMap.load_file(result.map_path)
        bad_ranges = rmap.get_ranges_by_status(SectorStatus.BAD)
        assert len(bad_ranges) == 1
        assert bad_ranges[0].start_sector == 10
        assert bad_ranges[0].sector_count == 2

        # Acceptance: zero-filled placeholders are never confused with genuine zeros
        # Destination image at sectors 10..12 is filled with zeros
        with open(dest_path, "rb") as f:
            f.seek(10 * 512)
            zeros = f.read(2 * 512)
            assert zeros == b"\x00" * 1024


def test_interrupted_imaging_and_resume(tmp_path: Path) -> None:
    """Acceptance check: interrupted imaging resumes correctly and produces identical result."""
    src_path = tmp_path / "resume_source.img"
    src_hash = _create_source_image(src_path, size_bytes=64 * 1024)
    dest_path = tmp_path / "dest" / "resumed.img"

    resolver = FakeVolumeIdentityResolver()
    service = DiskImagingService(resolver=resolver)

    # 1. Run with simulated cancellation after 4 blocks (16KB)
    call_count = 0

    def check_cancel() -> bool:
        nonlocal call_count
        call_count += 1
        return call_count > 4

    with (
        DiskImageReader(src_path) as reader,
        pytest.raises(ImagingCancelledError),
    ):
        service.acquire_image(
            source_device=reader,
            destination_image_path=dest_path,
            config=ImagingConfig(block_size_bytes=4096),
            should_cancel=check_cancel,
        )

    assert dest_path.exists()
    map_path = dest_path.with_suffix(f"{dest_path.suffix}.map.json")
    assert map_path.exists()

    # Load partial map: not all finished
    partial_map = RangeStatusMap.load_file(map_path)
    assert not partial_map.is_all_finished
    assert partial_map.finished_sectors_count > 0

    # 2. Resume acquisition on the same source device
    with DiskImageReader(src_path) as reader:
        res = service.acquire_image(
            source_device=reader,
            destination_image_path=dest_path,
            resume=True,
        )

        assert res.is_complete is True
        assert res.sha256_hash == src_hash
        assert dest_path.read_bytes() == src_path.read_bytes()


def test_resume_mismatched_identity_refused(tmp_path: Path) -> None:
    """Acceptance check: resume with a mismatched identity is refused."""
    src1_path = tmp_path / "src1.img"
    _create_source_image(src1_path, size_bytes=32 * 1024)

    src2_path = tmp_path / "src2.img"
    _create_source_image(src2_path, size_bytes=64 * 1024)  # Different capacity / content

    dest_path = tmp_path / "dest" / "mismatch.img"

    resolver = FakeVolumeIdentityResolver()
    service = DiskImagingService(resolver=resolver)

    # Acquire initial partial run with src1
    with DiskImageReader(src1_path) as reader1:
        service.acquire_image(reader1, dest_path)

    # Attempt to resume with src2 (mismatched identity)
    with (
        DiskImageReader(src2_path) as reader2,
        pytest.raises(ResumeIdentityMismatchError, match="Resume rejected"),
    ):
        service.acquire_image(reader2, dest_path, resume=True)


def test_destination_on_source_refused(tmp_path: Path) -> None:
    src_path = tmp_path / "src.img"
    _create_source_image(src_path, size_bytes=16 * 1024)

    # Configure resolver so dest_path is reported on the same volume as src
    resolver = FakeVolumeIdentityResolver()
    dest_path = tmp_path / "acquired.img"

    # Register src_path and dest_path to have same volume_id
    with DiskImageReader(src_path) as reader:
        resolver.register_device_volume(reader, "VOL_COLLISION", 1)
        resolver.register_path_volume(dest_path.parent, "VOL_COLLISION", 1)

        service = DiskImagingService(resolver=resolver)
        with pytest.raises(DestinationOnSourceError, match=r"(?i)same volume"):
            service.acquire_image(reader, dest_path)
