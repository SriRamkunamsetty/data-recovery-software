"""Integration tests for MainWindow shell, navigation, demo mode, and end-to-end UI flow."""

from collections.abc import Generator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.presentation.demo import create_demo_fat16_image
from recoverx.presentation.main_window import MainWindow
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.report_service import ReportService
from recoverx.services.session_service import SessionService


@pytest.fixture
def window(tmp_path: Path, qapp: QApplication) -> Generator[MainWindow, None, None]:
    """Fixture providing a fresh MainWindow with clean teardown."""
    db_mgr = DatabaseManager(tmp_path / "test.db")
    resolver = FakeVolumeIdentityResolver()
    session_service = SessionService(db_mgr, resolver)
    triage_service = DeviceTriageService()
    report_service = ReportService()

    win = MainWindow(
        session_service=session_service,
        triage_service=triage_service,
        report_service=report_service,
        resolver=resolver,
    )
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()


def test_main_window_init_and_navigation(window: MainWindow) -> None:
    """Test MainWindow starts cleanly, selects Dashboard, and allows page navigation."""
    assert window.accessibleName() == "RecoverX Main Window"
    assert window.stack.currentIndex() == 0  # Dashboard

    # Navigate to Settings (page index 6)
    window._navigate_to(6)
    assert window.stack.currentIndex() == 6
    assert window.sidebar.currentRow() == 6

    # Navigate back to Dashboard (page index 0)
    window._navigate_to(0)
    assert window.stack.currentIndex() == 0


def test_main_window_demo_mode_toggle(window: MainWindow) -> None:
    """Test demo mode simulation toggle shows warning banner and loads synthetic image."""
    # Demo mode is OFF by default (Section 13)
    assert not window.demo_banner.isVisible()
    assert not window.settings_page.demo_cb.isChecked()

    # Enable demo mode
    window.settings_page.demo_cb.setChecked(True)
    assert not window.demo_banner.isHidden()
    assert window.stack.currentIndex() == 1  # Navigates to device selection page
    assert window.device_page.current_reader is not None
    assert "synthetic" in window.device_page.current_path.lower()

    # Disable demo mode
    window.settings_page.demo_cb.setChecked(False)
    assert window.demo_banner.isHidden()


def test_main_window_scan_workflow(window: MainWindow, tmp_path: Path, qapp: QApplication) -> None:
    """Test full UI scan flow: device load -> options -> scan worker -> results -> report."""
    img_path = tmp_path / "test_flow.raw"
    create_demo_fat16_image(img_path)

    # 1. Load image in device page
    window.device_page.load_image(str(img_path))
    assert window.device_page.confirm_btn.isEnabled()

    # 2. Confirm device -> transitions to scan options (page 2)
    window.device_page.confirm_btn.click()
    assert window.stack.currentIndex() == 2
    assert window.current_session is not None

    # 3. Request scan
    window.scan_config_page.carving_cb.setChecked(False)
    window.scan_config_page.start_scan_btn.click()

    # 4. Progress page active, wait for worker execution
    assert window.stack.currentIndex() == 3
    worker = window.active_scan_worker
    if worker is not None:
        worker.wait(5000)
        qapp.processEvents()

    # 5. Result page populated
    assert window.stack.currentIndex() == 4
    assert len(window.results_page.all_candidates) >= 1

    # 6. Navigate to report page
    window.results_page.report_btn.click()
    qapp.processEvents()
    assert window.stack.currentIndex() == 5
    assert window.report_page.current_report_data is not None
    assert window.report_page.fingerprint_lbl.text() != "-"
