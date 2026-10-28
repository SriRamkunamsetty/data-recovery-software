"""Unit tests for UI pages: Dashboard, Device, Config, Progress, Results, Report, Settings."""

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QApplication

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod
from recoverx.domain.scan import ScanProgress
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.presentation.demo import create_demo_fat16_image
from recoverx.presentation.pages import (
    DashboardPage,
    DeviceSelectionPage,
    RecoveryResultsPage,
    ScanConfigurationPage,
    ScanProgressPage,
    SettingsPage,
)
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.session_service import SessionService


def test_dashboard_page(qapp: QApplication, tmp_path: Path) -> None:
    """Test dashboard page displays recent sessions and handles start button."""
    db_mgr = DatabaseManager(tmp_path / "test.db")
    service = SessionService(db_mgr, FakeVolumeIdentityResolver())

    page = DashboardPage(service)
    assert page.accessibleName() == "Dashboard Page"
    assert page.session_table.rowCount() == 0

    # Create dummy session
    img_path = tmp_path / "test.raw"
    create_demo_fat16_image(img_path)
    reader = DiskImageReader(img_path)
    try:
        service.create_session(str(img_path), reader, name="TestSession")
        page.refresh_sessions()
        assert page.session_table.rowCount() == 1
    finally:
        reader.close()

    signals: list[bool] = []
    page.start_recovery_requested.connect(lambda: signals.append(True))
    page.start_recovery_requested.emit()
    assert len(signals) == 1
    page.close()


def test_device_selection_page(qapp: QApplication, tmp_path: Path) -> None:
    """Test device selection page loads image, runs triage, and emits selection."""
    img_path = tmp_path / "test_demo.raw"
    create_demo_fat16_image(img_path)

    triage_service = DeviceTriageService()
    page = DeviceSelectionPage(triage_service)
    assert page.accessibleName() == "Device Selection Page"

    page.load_image(str(img_path))
    assert page.confirm_btn.isEnabled()
    assert "supported" in page.triage_status_lbl.text().lower()

    selected_data: list[tuple[str, Any]] = []
    page.device_selected.connect(lambda path, dev: selected_data.append((path, dev)))
    page.confirm_btn.click()

    assert len(selected_data) == 1
    assert selected_data[0][0] == str(img_path)
    page.close()


def test_scan_config_page(qapp: QApplication) -> None:
    """Test scan configuration page toggles carving warning and emits scan request."""
    page = ScanConfigurationPage()
    assert page.accessibleName() == "Scan Configuration Page"
    assert page.carving_warning.isHidden()

    page.carving_cb.setChecked(True)
    assert not page.carving_warning.isHidden()

    requested_args: list[tuple[bool, bool]] = []
    page.scan_requested.connect(
        lambda carving, lost_vols: requested_args.append((carving, lost_vols))
    )
    page.start_scan_btn.click()

    assert len(requested_args) == 1
    assert requested_args[0] == (True, True)  # carving=True, lost_vol=True
    page.close()


def test_scan_progress_page(qapp: QApplication) -> None:
    """Test scan progress page updates UI counters accurately and handles cancel."""
    page = ScanProgressPage()
    assert page.accessibleName() == "Scan Progress Page"

    prog = ScanProgress(
        phase="carving",
        bytes_scanned=512 * 1024,
        total_bytes=1024 * 1024,
        elapsed_seconds=10.0,
        candidates_found=3,
        bad_sectors_found=0,
        current_sector=1024,
    )
    page.update_progress(prog)

    assert page.progress_bar.value() == 50
    assert "50.0%" in page.bytes_lbl.text()
    assert "3 candidates" in page.candidates_lbl.text()

    cancelled: list[bool] = []
    page.cancel_requested.connect(lambda: cancelled.append(True))
    page.cancel_btn.click()
    assert len(cancelled) == 1
    page.close()


def test_recovery_results_page(qapp: QApplication) -> None:
    """Test candidate results page displays, searches, filters, and selects candidates."""
    page = RecoveryResultsPage()
    assert page.accessibleName() == "Recovery Results Page"

    candidates = [
        RecoveryCandidate(
            candidate_id="c1",
            filename="PHOTO.JPG",
            relative_path="DCIM/PHOTO.JPG",
            extension=".jpg",
            size_bytes=1000,
            source_offset=1024,
            source_method=RecoverySourceMethod.METADATA,
            status=CandidateStatus.PREVIEW_VALIDATED,
        ),
        RecoveryCandidate(
            candidate_id="c2",
            filename="NOTES.TXT",
            relative_path="NOTES.TXT",
            extension=".txt",
            size_bytes=500,
            source_offset=2048,
            source_method=RecoverySourceMethod.CARVED,
            status=CandidateStatus.CORRUPTED,
        ),
    ]

    page.set_candidates(candidates)
    assert page.table.rowCount() == 2

    # Test filename search
    page.search_edit.setText("PHOTO")
    assert page.table.rowCount() == 1
    page.search_edit.clear()
    assert page.table.rowCount() == 2

    # Test Select Validated Only
    page._select_validated_only()
    selected_ids = page._get_selected_candidate_ids()
    assert selected_ids == ["c1"]

    # Test Select All
    page._select_all()
    assert page._get_selected_candidate_ids() == ["c1", "c2"]

    # Test Deselect All
    page._deselect_all()
    assert page._get_selected_candidate_ids() == []

    page.close()


def test_settings_page(qapp: QApplication) -> None:
    """Test settings page theme and demo mode toggling."""
    page = SettingsPage()
    assert page.accessibleName() == "Settings Page"
    assert page.demo_cb.isChecked() is False

    demo_signals: list[bool] = []
    page.demo_mode_toggled.connect(demo_signals.append)
    page.demo_cb.setChecked(True)

    assert len(demo_signals) == 1
    assert demo_signals[0] is True
    assert page.demo_cb.isChecked() is True

    theme_signals: list[str] = []
    page.theme_changed.connect(theme_signals.append)
    page.dark_rb.click()

    assert len(theme_signals) == 1
    assert theme_signals[0] == "dark"
    page.close()
