"""Unit tests for ReportService JSON and HTML export generation."""

import json
from pathlib import Path

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.device import DeviceIdentity
from recoverx.domain.enums import CandidateStatus, DeviceTriageStatus, RecoverySourceMethod
from recoverx.domain.partition import PartitionInfo
from recoverx.domain.recovery import RecoveryResult
from recoverx.domain.session import DeviceTriageResult
from recoverx.services.report_service import ForensicReportData, ReportService


def test_report_service_export_json_and_html(tmp_path: Path) -> None:
    """Test generating JSON and HTML forensic reports."""
    identity = DeviceIdentity(
        vendor="Kingston",
        product="DataTraveler 3.0",
        serial="0014D118",
        capacity_bytes=32 * 1024 * 1024,
        logical_sector_size=512,
        physical_sector_size=512,
        disk_identifier="0xABCDEF12",
        sector0_hash="d" * 64,
    )

    triage = DeviceTriageResult(
        status=DeviceTriageStatus.SUPPORTED_FILESYSTEM,
        explanation="Healthy FAT32 filesystem",
        recommended_action="Recover deleted files",
        can_scan=True,
        recommend_imaging=False,
    )

    partitions = [
        PartitionInfo(
            partition_number=1,
            start_sector=2048,
            sector_count=63488,
            sector_size=512,
            partition_type_or_guid="FAT32",
            name="USB_DATA",
            is_bootable=True,
        )
    ]

    candidates = [
        RecoveryCandidate(
            candidate_id="cand_1",
            filename="REPORT.PDF",
            relative_path="Documents/REPORT.PDF",
            extension=".pdf",
            size_bytes=40960,
            source_offset=1048576,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.PREVIEW_VALIDATED,
            sha256_hash="e" * 64,
        )
    ]

    recovery_results = [
        RecoveryResult(
            candidate_id="cand_1",
            destination_path="/safe/dest/REPORT.PDF",
            bytes_written=40960,
            status="success",
            hash_verified=True,
            actual_sha256="e" * 64,
        )
    ]

    report_data = ForensicReportData(
        report_id="rep_001",
        session_id="sess_001",
        generated_at=1700000000.0,
        source_identity=identity,
        triage_result=triage,
        partitions=partitions,
        candidates=candidates,
        recovery_results=recovery_results,
        scan_duration_seconds=12.5,
        carving_executed=True,
        app_version="0.1.0",
    )

    service = ReportService()

    # 1. Test JSON Export
    json_path = tmp_path / "report.json"
    service.export_json(report_data, json_path)
    assert json_path.exists()

    with open(json_path, encoding="utf-8") as f:
        loaded = json.load(f)

    assert loaded["report_id"] == "rep_001"
    assert loaded["source_device"]["vendor"] == "Kingston"
    assert loaded["source_device"]["capacity_bytes"] == 32 * 1024 * 1024
    assert loaded["triage"]["status"] == DeviceTriageStatus.SUPPORTED_FILESYSTEM.value
    assert len(loaded["partitions"]) == 1
    assert loaded["recovery_summary"]["total_files_recovered"] == 1
    assert loaded["recovery_summary"]["total_bytes_recovered"] == 40960
    assert "strictly implements read-only access" in loaded["forensic_integrity_statement"]

    # 2. Test HTML Export
    html_path = tmp_path / "report.html"
    service.export_html(report_data, html_path)
    assert html_path.exists()

    html_text = html_path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "RecoverX Forensic Recovery Report" in html_text
    assert "Kingston DataTraveler 3.0" in html_text
    assert "REPORT.PDF" in html_text
    assert "Preview validated" in html_text
    assert "Forensic Integrity Assurance" in html_text
