"""Unit tests for DeviceTriageService health, encryption, and filesystem classification."""

from pathlib import Path

from recoverx.domain.enums import DeviceTriageStatus, FileSystemType
from recoverx.infrastructure.storage.fault import ByteRange, FaultConfig, FaultInjectionReader
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.services.device_triage_service import DeviceTriageService
from tests.fixtures.fat_builder import SyntheticFatBuilder


def test_triage_controller_failure_zero_bytes(tmp_path: Path) -> None:
    """Triage classifies empty / 0-byte device as controller failure."""
    img_path = tmp_path / "zero.img"
    img_path.write_bytes(b"")  # 0 bytes

    with DiskImageReader(img_path) as reader:
        service = DeviceTriageService()
        result = service.triage_device(reader)

        assert result.status == DeviceTriageStatus.CONTROLLER_FAILURE
        assert result.can_scan is False
        assert result.recommend_imaging is False


def test_triage_readable_with_errors(tmp_path: Path) -> None:
    """Triage classifies initial read error as readable with errors and recommends imaging."""
    img_path = tmp_path / "degraded.img"
    img_path.write_bytes(b"\x00" * 32768)

    with DiskImageReader(img_path) as base_reader:
        # Inject unreadable fault at sector 0 (bytes 0..512)
        cfg = FaultConfig(unreadable_ranges=[ByteRange(0, 512)])
        faulty = FaultInjectionReader(base_reader, cfg)
        service = DeviceTriageService()
        result = service.triage_device(faulty)

        assert result.status == DeviceTriageStatus.READABLE_WITH_ERRORS
        assert result.can_scan is True
        assert result.recommend_imaging is True
        assert "imaging" in result.recommended_action.lower()


def test_triage_encrypted_volume_bitlocker(tmp_path: Path) -> None:
    """Triage classifies BitLocker signature as encrypted volume."""
    img_path = tmp_path / "bitlocker.img"
    # BitLocker VBR has signature b"-FVE-FS-" at offset 3
    data = bytearray(32768)
    data[3:11] = b"-FVE-FS-"
    img_path.write_bytes(data)

    with DiskImageReader(img_path) as reader:
        service = DeviceTriageService()
        result = service.triage_device(reader)

        assert result.status == DeviceTriageStatus.ENCRYPTED_VOLUME
        assert result.can_scan is False
        assert result.recommend_imaging is True


def test_triage_supported_filesystem_fat32(tmp_path: Path) -> None:
    """Triage classifies healthy FAT32 device as supported filesystem."""
    img_path = tmp_path / "fat32.img"
    builder = SyntheticFatBuilder(fs_type=FileSystemType.FAT32, volume_label="FAT32_TEST")
    builder.build(img_path)

    with DiskImageReader(img_path) as reader:
        service = DeviceTriageService()
        result = service.triage_device(reader)

        assert result.status == DeviceTriageStatus.SUPPORTED_FILESYSTEM
        assert result.can_scan is True
        assert result.recommend_imaging is False


def test_triage_damaged_partition_table_blank_disk(tmp_path: Path) -> None:
    """Triage classifies non-filesystem zeroed disk as damaged or missing partition table."""
    img_path = tmp_path / "blank.img"
    img_path.write_bytes(b"\x00" * 65536)

    with DiskImageReader(img_path) as reader:
        service = DeviceTriageService()
        result = service.triage_device(reader)

        assert result.status == DeviceTriageStatus.DAMAGED_PARTITION_TABLE
        assert result.can_scan is True
