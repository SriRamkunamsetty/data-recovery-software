"""Unit tests for RecoverX domain models and validation."""

import pytest

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity, StorageDevice
from recoverx.domain.enums import (
    CandidateStatus,
    DeviceTriageStatus,
    FileSystemType,
    JobStatus,
    RecoverySourceMethod,
)
from recoverx.domain.filesystem import FileSystemInfo
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.report import RecoveryReport
from recoverx.domain.scan import BadSectorRange, ScanJob, ScanProgress, SectorReadResult


class TestCandidateStatus:
    """Validate CandidateStatus strictly conforms to Rule 7 of CLAUDE.md."""

    def test_all_factual_statuses_present(self) -> None:
        expected = {
            "Metadata recovered",
            "Signature matched",
            "Preview validated",
            "Partially readable",
            "Truncated",
            "Corrupted",
            "Unallocated",
            "Allocated (active file)",
            "Overwritten",
            "Unverified",
            "Recovery failed",
        }
        actual = {status.value for status in CandidateStatus}
        assert actual == expected


class TestDeviceIdentity:
    """Validate DeviceIdentity construction, validation, and match logic."""

    def test_valid_device_identity(self, sample_sha256: str) -> None:
        ident = DeviceIdentity(
            vendor="SanDisk",
            product="Ultra USB 3.0",
            serial="4C530001",
            capacity_bytes=32_000_000_000,
            logical_sector_size=512,
            physical_sector_size=4096,
            disk_identifier="0x1234abcd",
            sector0_hash=sample_sha256,
        )
        assert ident.vendor == "SanDisk"
        assert ident.capacity_bytes == 32_000_000_000
        assert ident.total_sectors == 32_000_000_000 // 512
        assert not ident.is_serial_synthetic_or_generic

    def test_negative_capacity_rejected(self) -> None:
        with pytest.raises(ValueError, match="capacity_bytes cannot be negative"):
            DeviceIdentity(
                vendor="Test",
                product="Drive",
                serial="123",
                capacity_bytes=-1,
                logical_sector_size=512,
                physical_sector_size=512,
                disk_identifier="0x1",
                sector0_hash="",
            )

    def test_non_power_of_two_sector_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="logical_sector_size must be a power of two"):
            DeviceIdentity(
                vendor="Test",
                product="Drive",
                serial="123",
                capacity_bytes=10000,
                logical_sector_size=500,  # Not power of two
                physical_sector_size=512,
                disk_identifier="0x1",
                sector0_hash="",
            )

    def test_physical_smaller_than_logical_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot be smaller than logical_sector_size"):
            DeviceIdentity(
                vendor="Test",
                product="Drive",
                serial="123",
                capacity_bytes=10000,
                logical_sector_size=4096,
                physical_sector_size=512,
                disk_identifier="0x1",
                sector0_hash="",
            )

    def test_invalid_sector0_hash_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be a 64-character hexadecimal"):
            DeviceIdentity(
                vendor="Test",
                product="Drive",
                serial="123",
                capacity_bytes=10000,
                logical_sector_size=512,
                physical_sector_size=512,
                disk_identifier="0x1",
                sector0_hash="invalid_hash_string",
            )

    def test_matches_logic(self, sample_sha256: str) -> None:
        d1 = DeviceIdentity(
            vendor="Kingston",
            product="DataTraveler",
            serial="A1B2",
            capacity_bytes=16_000_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0xABCD1234",
            sector0_hash=sample_sha256,
        )
        # Identical parameters except serial string variation
        d2 = DeviceIdentity(
            vendor="Kingston",
            product="DataTraveler",
            serial="A1B2_alt",
            capacity_bytes=16_000_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0xABCD1234",
            sector0_hash=sample_sha256,
        )
        assert d1.matches(d2)

        # Mismatched capacity
        d3 = DeviceIdentity(
            vendor="Kingston",
            product="DataTraveler",
            serial="A1B2",
            capacity_bytes=32_000_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0xABCD1234",
            sector0_hash=sample_sha256,
        )
        assert not d1.matches(d3)


class TestStorageDevice:
    """Validate StorageDevice model."""

    def test_valid_storage_device(self, sample_sha256: str) -> None:
        ident = DeviceIdentity(
            vendor="Samsung",
            product="EVO",
            serial="S123",
            capacity_bytes=64_000_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0x11223344",
            sector0_hash=sample_sha256,
        )
        dev = StorageDevice(
            identity=ident,
            bus_type="USB",
            physical_disk_number=1,
            drive_letters=("F:",),
            is_removable=True,
            is_read_only=True,
            triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            source_path=r"\\.\PhysicalDrive1",
        )
        assert dev.physical_disk_number == 1
        assert dev.drive_letters == ("F:",)
        assert dev.triage_status == DeviceTriageStatus.SUPPORTED_FILESYSTEM

    def test_negative_physical_disk_number_rejected(self, sample_sha256: str) -> None:
        ident = DeviceIdentity(
            vendor="Samsung",
            product="EVO",
            serial="S123",
            capacity_bytes=64_000_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0x11223344",
            sector0_hash=sample_sha256,
        )
        with pytest.raises(ValueError, match="physical_disk_number must be non-negative"):
            StorageDevice(
                identity=ident,
                bus_type="USB",
                physical_disk_number=-1,
                drive_letters=(),
                is_removable=True,
                is_read_only=True,
                triage_status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
            )


class TestPartitionInfo:
    """Validate PartitionInfo calculations and bounds checks."""

    def test_valid_partition(self) -> None:
        part = PartitionInfo(
            partition_number=1,
            start_sector=2048,
            sector_count=1000,
            sector_size=512,
            partition_type_or_guid="0x0C",
            name="Primary",
            is_bootable=False,
        )
        assert part.start_offset_bytes == 2048 * 512
        assert part.size_bytes == 1000 * 512
        assert part.end_sector == 2048 + 1000 - 1

    def test_negative_values_rejected(self) -> None:
        with pytest.raises(ValueError, match="start_sector must be non-negative"):
            PartitionInfo(partition_number=0, start_sector=-1, sector_count=100)

        with pytest.raises(ValueError, match="sector_count must be non-negative"):
            PartitionInfo(partition_number=0, start_sector=100, sector_count=-1)


class TestFileSystemInfo:
    """Validate FileSystemInfo validation."""

    def test_valid_filesystem(self) -> None:
        fs = FileSystemInfo(
            fs_type=FileSystemType.FAT32,
            volume_label="RECOVERY_USB",
            cluster_size_bytes=4096,
            total_clusters=100_000,
            free_clusters=50_000,
            serial_number="1234-ABCD",
            root_directory_offset_bytes=1048576,
        )
        assert fs.fs_type == FileSystemType.FAT32
        assert fs.cluster_size_bytes == 4096

    def test_free_clusters_exceeding_total_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed total_clusters"):
            FileSystemInfo(
                fs_type=FileSystemType.FAT32,
                total_clusters=100,
                free_clusters=101,
            )


class TestScanAndSectorModels:
    """Validate BadSectorRange, SectorReadResult, and ScanProgress."""

    def test_bad_sector_range(self) -> None:
        bs = BadSectorRange(start_sector=100, sector_count=16, status="bad")
        assert bs.end_sector == 115
        assert bs.sector_count == 16

    def test_bad_sector_zero_count_rejected(self) -> None:
        with pytest.raises(ValueError, match="sector_count must be positive"):
            BadSectorRange(start_sector=100, sector_count=0)

    def test_sector_read_result_overflow_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed requested_length"):
            SectorReadResult(
                offset=0,
                requested_length=512,
                data=b"x" * 513,
                is_bad=False,
            )

    def test_scan_progress_fractions(self) -> None:
        sp = ScanProgress(
            phase="carving",
            bytes_scanned=500,
            total_bytes=1000,
            elapsed_seconds=10.0,
            candidates_found=5,
            bad_sectors_found=0,
            current_sector=1,
        )
        assert sp.progress_fraction == 0.5
        assert sp.progress_percent == 50.0

    def test_scan_progress_zero_total(self) -> None:
        sp = ScanProgress(
            phase="starting",
            bytes_scanned=0,
            total_bytes=0,
            elapsed_seconds=0.0,
            candidates_found=0,
            bad_sectors_found=0,
            current_sector=0,
        )
        assert sp.progress_fraction == 0.0
        assert sp.progress_percent == 0.0


class TestRecoveryCandidate:
    """Validate RecoveryCandidate model and constraints."""

    def test_valid_candidate(self, sample_sha256: str) -> None:
        cand = RecoveryCandidate(
            candidate_id="cand-001",
            filename="document.docx",
            relative_path="Documents/document.docx",
            extension="docx",
            size_bytes=15000,
            source_offset=1048576,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.METADATA_RECOVERED,
            sha256_hash=sample_sha256,
        )
        assert cand.filename == "document.docx"
        assert cand.status == CandidateStatus.METADATA_RECOVERED

    def test_invalid_status_type_rejected(self) -> None:
        with pytest.raises(TypeError, match="status must be an instance of CandidateStatus"):
            RecoveryCandidate(
                candidate_id="cand-001",
                filename="document.docx",
                relative_path="doc.docx",
                extension="docx",
                size_bytes=15000,
                source_offset=1048576,
                source_method=RecoverySourceMethod.METADATA,
                status="Metadata recovered",  # type: ignore[arg-type] # String instead of enum
            )

    def test_negative_size_rejected(self) -> None:
        with pytest.raises(ValueError, match="size_bytes cannot be negative"):
            RecoveryCandidate(
                candidate_id="cand-001",
                filename="doc.docx",
                relative_path="doc.docx",
                extension="docx",
                size_bytes=-10,
                source_offset=0,
                source_method=RecoverySourceMethod.CARVED,
                status=CandidateStatus.SIGNATURE_MATCHED,
            )


class TestRecoveryResultAndReport:
    """Validate RecoveryResult and RecoveryReport."""

    def test_recovery_result_success(self) -> None:
        res = RecoveryResult(
            candidate_id="cand-001",
            destination_path=r"D:\Recovered\doc.docx",
            bytes_written=15000,
            status="success",
            hash_verified=True,
        )
        assert res.is_successful

    def test_recovery_report_creation(self, sample_sha256: str) -> None:
        ident = DeviceIdentity(
            vendor="Generic",
            product="FlashDisk",
            serial="111",
            capacity_bytes=1_000_000,
            logical_sector_size=512,
            physical_sector_size=512,
            disk_identifier="0x123",
            sector0_hash=sample_sha256,
        )
        rep = RecoveryReport(
            report_id="rep-001",
            session_id="sess-001",
            created_at=1700000000.0,
            device_identity=ident,
            scan_duration_seconds=12.5,
            total_candidates=10,
            status_counts={CandidateStatus.METADATA_RECOVERED: 10},
            recovered_count=10,
            failed_count=0,
            total_bytes_recovered=50000,
            bad_sectors_total=0,
        )
        assert rep.report_id == "rep-001"
        assert rep.recovered_count == 10


class TestScanJob:
    """Validate ScanJob lifecycle tracking."""

    def test_scan_job_lifecycle(self) -> None:
        job = ScanJob(
            job_id="job-1",
            session_id="sess-1",
            source_identifier="drive-1",
            scan_type="quick",
            created_timestamp=1700000000.0,
            status=JobStatus.PENDING,
        )
        assert job.status == JobStatus.PENDING
