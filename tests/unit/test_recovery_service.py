"""Unit and integration tests for RecoveryService."""

from pathlib import Path

import pytest

from recoverx.carving.scanner import CarvingScanner
from recoverx.config import CollisionPolicy
from recoverx.infrastructure.storage.fixtures import (
    ImageHashSnapshot,
    SyntheticImageBuilder,
)
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import (
    DestinationOnSourceError,
    FakeVolumeIdentityResolver,
)
from recoverx.services.recovery_service import RecoveryService
from tests.fixtures.sample_files import create_minimal_jpeg, create_minimal_png


@pytest.fixture
def recovery_test_env(
    tmp_path: Path,
) -> tuple[Path, Path, FakeVolumeIdentityResolver]:
    """Create a synthetic disk image, destination directory, and configured resolver."""
    jpeg_data = create_minimal_jpeg()
    png_data = create_minimal_png()

    builder = SyntheticImageBuilder(total_size_bytes=128 * 1024)
    builder.add_file("photo.jpg", jpeg_data, offset=2048)
    builder.add_file("chart.png", png_data, offset=32768)

    img_path = tmp_path / "source_device.img"
    manifest = builder.build(img_path)

    dest_dir = tmp_path / "safe_recovery_dest"
    dest_dir.mkdir()

    resolver = FakeVolumeIdentityResolver()
    # Register source as Disk 1, Volume SRC_VOL
    resolver.register_path_volume(img_path, volume_id="SRC_VOL", physical_disk_number=1)
    # Register destination as Disk 2, Volume DEST_VOL
    resolver.register_path_volume(dest_dir, volume_id="DEST_VOL", physical_disk_number=2)

    return manifest.image_path, dest_dir, resolver


def test_recovery_service_extracts_files_matching_hashes(
    recovery_test_env: tuple[Path, Path, FakeVolumeIdentityResolver],
) -> None:
    img_path, dest_dir, resolver = recovery_test_env

    # 1. Take cryptographic snapshot of source
    snapshot = ImageHashSnapshot(img_path)

    # 2. Scan image for candidates
    scanner = CarvingScanner()
    with DiskImageReader(img_path) as reader:
        resolver.register_device_volume(reader, volume_id="SRC_VOL", physical_disk_number=1)
        candidates = scanner.scan(reader)
        assert len(candidates) == 2

        # 3. Recover to separate destination
        service = RecoveryService(resolver=resolver)
        results = service.recover_candidates(
            device=reader,
            destination_directory=dest_dir,
            candidates=candidates,
        )

        assert len(results) == 2
        for r in results:
            assert r.is_successful
            assert r.hash_verified
            recovered_file = Path(r.destination_path)
            assert recovered_file.exists()
            assert recovered_file.stat().st_size == r.bytes_written

    # 4. Prove source was never modified
    assert snapshot.verify_unchanged()


def test_recovery_service_refuses_destination_on_source(
    recovery_test_env: tuple[Path, Path, FakeVolumeIdentityResolver],
) -> None:
    img_path, dest_dir, resolver = recovery_test_env

    scanner = CarvingScanner()
    with DiskImageReader(img_path) as reader:
        # Re-register destination on SAME volume as source
        resolver.register_device_volume(reader, volume_id="SAME_VOL", physical_disk_number=1)
        resolver.register_path_volume(dest_dir, volume_id="SAME_VOL", physical_disk_number=1)

        candidates = scanner.scan(reader)
        service = RecoveryService(resolver=resolver)

        with pytest.raises(DestinationOnSourceError):
            service.recover_candidates(
                device=reader,
                destination_directory=dest_dir,
                candidates=candidates,
            )


def test_recovery_service_handles_collision_renaming(
    recovery_test_env: tuple[Path, Path, FakeVolumeIdentityResolver],
) -> None:
    img_path, dest_dir, resolver = recovery_test_env

    scanner = CarvingScanner()
    with DiskImageReader(img_path) as reader:
        resolver.register_device_volume(reader, volume_id="SRC_VOL", physical_disk_number=1)
        candidates = scanner.scan(reader)
        service = RecoveryService(resolver=resolver)

        # First recovery run
        results_1 = service.recover_candidates(
            device=reader,
            destination_directory=dest_dir,
            candidates=candidates,
            collision_policy=CollisionPolicy.RENAME,
        )
        assert all(r.status == "success" for r in results_1)

        # Second recovery run to the same destination with RENAME policy
        results_2 = service.recover_candidates(
            device=reader,
            destination_directory=dest_dir,
            candidates=candidates,
            collision_policy=CollisionPolicy.RENAME,
        )
        assert all(r.status == "collision_renamed" for r in results_2)
        # Verify no files were overwritten; both sets exist
        for r in results_2:
            assert Path(r.destination_path).exists()
