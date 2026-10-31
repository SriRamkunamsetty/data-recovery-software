"""Main window application shell with sidebar navigation, page routing, and worker orchestration."""

import contextlib
import logging
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.session import RecoverySession
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import VolumeIdentityResolver
from recoverx.presentation.demo import create_demo_fat16_image
from recoverx.presentation.dialogs.destination_dialog import RecoveryDestinationDialog
from recoverx.presentation.dialogs.preview_dialog import FilePreviewDialog
from recoverx.presentation.pages.dashboard_page import DashboardPage
from recoverx.presentation.pages.device_page import DeviceSelectionPage
from recoverx.presentation.pages.report_page import RecoveryReportPage
from recoverx.presentation.pages.results_page import RecoveryResultsPage
from recoverx.presentation.pages.scan_config_page import ScanConfigurationPage
from recoverx.presentation.pages.scan_progress_page import ScanProgressPage
from recoverx.presentation.pages.settings_page import SettingsPage
from recoverx.presentation.workers import RecoveryWorker, ScanWorker
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.report_service import ReportService
from recoverx.services.session_service import SessionService

logger = logging.getLogger(__name__)


class SidebarItemDelegate(QStyledItemDelegate):
    """Custom item delegate suppressing Qt default dotted focus rectangle around sidebar items."""

    def paint(self, painter: Any, option: QStyleOptionViewItem, index: Any) -> None:
        opt = QStyleOptionViewItem(option)
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, index)


class MainWindow(QMainWindow):
    """Main application shell coordinating pages, workers, and safety constraints.

    Section 14 of MASTER_PROMPT.md:
    Asynchronous architecture: scans and recovery run in QThread workers with signals/slots.
    UI never freezes and never touches devices directly from UI threads.
    """

    def __init__(
        self,
        session_service: SessionService,
        triage_service: DeviceTriageService,
        report_service: ReportService,
        resolver: VolumeIdentityResolver,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.session_service = session_service
        self.triage_service = triage_service
        self.report_service = report_service
        self.resolver = resolver

        self.current_session: RecoverySession | None = None
        self.current_device: ReadOnlyBlockDevice | None = None
        self.current_source_path: str = ""

        self.active_scan_worker: ScanWorker | None = None
        self.active_recovery_worker: RecoveryWorker | None = None
        self._demo_temp_dir: tempfile.TemporaryDirectory[str] | None = None

        self.setWindowTitle("RecoverX - Forensic Removable Storage Data Recovery")
        self.resize(1100, 720)
        self.setMinimumSize(950, 600)
        self.setAccessibleName("RecoverX Main Window")

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Demo Mode Warning Banner (Hidden by default; Section 13)
        self.demo_banner = QFrame()
        self.demo_banner.setProperty("class", "DemoBanner")
        self.demo_banner.setAccessibleName("Demo Mode Simulation Banner")
        demo_layout = QHBoxLayout(self.demo_banner)
        demo_layout.setContentsMargins(16, 8, 16, 8)
        demo_lbl = QLabel(
            "&#9888; <strong>DEMO MODE ACTIVE:</strong> Running in simulated "
            "synthetic storage mode. Real physical disks are not accessed."
        )
        demo_lbl.setStyleSheet("color: #ffffff; font-weight: 600;")
        demo_layout.addWidget(demo_lbl)
        self.demo_banner.setVisible(False)
        root_layout.addWidget(self.demo_banner)

        # Main Split Body (Sidebar + Pages)
        body_layout = QHBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar Container with Logo Header & Status Footer
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("SidebarContainer")
        sidebar_frame.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 1. Top Logo Header
        logo_container = QFrame()
        logo_container.setStyleSheet(
            "background-color: transparent; border-bottom: 1px solid #1e293b; padding: 18px 16px;"
        )
        logo_layout = QHBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(12)

        logo_icon = QLabel("🛡")
        logo_icon.setStyleSheet(
            "font-size: 22px; background: #1e293b; border: 1px solid #334155; "
            "border-radius: 8px; padding: 6px;"
        )
        logo_layout.addWidget(logo_icon)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        app_title = QLabel("<strong>RecoverX</strong>")
        app_title.setStyleSheet("font-size: 16px; color: #f8fafc;")
        title_layout.addWidget(app_title)

        app_subtitle = QLabel("Forensic Data Recovery")
        app_subtitle.setStyleSheet("font-size: 10px; color: #94a3b8; font-weight: 500;")
        title_layout.addWidget(app_subtitle)
        logo_layout.addLayout(title_layout)
        logo_layout.addStretch(1)

        sidebar_layout.addWidget(logo_container)

        # 2. Navigation List
        self.sidebar = QListWidget()
        self.sidebar.setObjectName("SidebarList")
        self.sidebar.setAccessibleName("Sidebar Navigation List")
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sidebar.setItemDelegate(SidebarItemDelegate(self.sidebar))

        self._add_sidebar_item("🏠  Dashboard", 0)
        self._add_sidebar_item("🖴  Select Media", 1)
        self._add_sidebar_item("⚙  Scan Options", 2)
        self._add_sidebar_item("⏳  Scan Progress", 3)
        self._add_sidebar_item("📁  Recovery Results", 4)
        self._add_sidebar_item("📊  Forensic Report", 5)
        self._add_sidebar_item("🔧  Settings", 6)

        self.sidebar.currentRowChanged.connect(self._on_sidebar_row_changed)
        sidebar_layout.addWidget(self.sidebar, stretch=1)

        # 3. Bottom Status Footer
        footer_container = QFrame()
        footer_container.setStyleSheet(
            "background-color: #0b1120; border-top: 1px solid #1e293b; padding: 14px 16px;"
        )
        footer_layout = QVBoxLayout(footer_container)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(4)

        ver_lbl = QLabel("v0.1.0 • Forensic x64")
        ver_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
        footer_layout.addWidget(ver_lbl)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        dot_lbl = QLabel("●")
        dot_lbl.setStyleSheet("color: #34d399; font-size: 10px;")
        status_row.addWidget(dot_lbl)

        engine_lbl = QLabel("Engine Ready")
        engine_lbl.setStyleSheet("color: #34d399; font-size: 12px; font-weight: 600;")
        status_row.addWidget(engine_lbl)
        status_row.addStretch(1)
        footer_layout.addLayout(status_row)

        sidebar_layout.addWidget(footer_container)
        body_layout.addWidget(sidebar_frame)

        # Stacked Pages
        self.stack = QStackedWidget()
        self.stack.setAccessibleName("Main Content Stack")

        self.dashboard_page = DashboardPage(self.session_service)
        self.device_page = DeviceSelectionPage(self.triage_service)
        self.scan_config_page = ScanConfigurationPage()
        self.scan_progress_page = ScanProgressPage()
        self.results_page = RecoveryResultsPage()
        self.report_page = RecoveryReportPage(self.session_service, self.report_service)
        self.settings_page = SettingsPage()

        self.stack.addWidget(self.dashboard_page)  # 0
        self.stack.addWidget(self.device_page)  # 1
        self.stack.addWidget(self.scan_config_page)  # 2
        self.stack.addWidget(self.scan_progress_page)  # 3
        self.stack.addWidget(self.results_page)  # 4
        self.stack.addWidget(self.report_page)  # 5
        self.stack.addWidget(self.settings_page)  # 6

        body_layout.addWidget(self.stack, stretch=1)
        root_layout.addLayout(body_layout)

        # Status bar
        self.status_bar = self.statusBar()
        if self.status_bar:
            self.status_bar.showMessage("Engine Ready | Forensic Read-Only Active")

        # Initial selection
        self.sidebar.setCurrentRow(0)

    def _add_sidebar_item(self, text: str, index: int) -> None:
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, index)
        self.sidebar.addItem(item)

    def _on_sidebar_row_changed(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)

    def _navigate_to(self, page_index: int) -> None:
        self.sidebar.setCurrentRow(page_index)

    def _connect_signals(self) -> None:
        # Dashboard page
        self.dashboard_page.start_recovery_requested.connect(lambda: self._navigate_to(1))
        self.dashboard_page.resume_session_requested.connect(self._on_resume_session)
        self.dashboard_page.create_image_requested.connect(lambda: self._navigate_to(1))
        self.dashboard_page.view_reports_requested.connect(lambda: self._navigate_to(5))

        # Device selection page
        self.device_page.device_selected.connect(self._on_device_selected)

        # Scan config page
        self.scan_config_page.back_requested.connect(lambda: self._navigate_to(1))
        self.scan_config_page.scan_requested.connect(self._on_start_scan)

        # Scan progress page
        self.scan_progress_page.cancel_requested.connect(self._on_cancel_scan)

        # Results page
        self.results_page.preview_requested.connect(self._on_preview_candidate)
        self.results_page.recovery_requested.connect(self._on_recover_candidates)
        self.results_page.report_requested.connect(self._on_view_report)

        # Report page
        self.report_page.back_to_dashboard.connect(self._on_back_to_dashboard)

        # Settings page
        self.settings_page.demo_mode_toggled.connect(self._on_demo_mode_toggled)

    def _on_device_selected(self, path: str, device: ReadOnlyBlockDevice) -> None:
        self.current_source_path = path
        self.current_device = device

        # Create session in SQLite
        session = self.session_service.create_session(
            source_path=path,
            source_device=device,
            name=f"Recovery_{Path(path).stem}",
        )
        self.current_session = session

        # Update ScanConfigPage
        self.scan_config_page.set_target_info(f"{Path(path).name} ({device.size_bytes:,} bytes)")
        self._navigate_to(2)  # Go to Scan Options

    def _on_resume_session(self, session_id: str) -> None:
        session = self.session_service.get_session(session_id)
        if not session:
            return
        self.current_session = session
        cands = self.session_service.candidate_repo.get_by_session(session_id)
        self.results_page.set_candidates(cands)
        self._navigate_to(4)

    def _on_start_scan(self, enable_carving: bool, scan_lost_volumes: bool) -> None:
        if not self.current_session or not self.current_device:
            QMessageBox.warning(
                self, "No Device", "Please select a storage device or disk image first."
            )
            self._navigate_to(1)
            return

        # Prepare progress page
        self.scan_progress_page.reset()
        self._navigate_to(3)  # Go to progress page

        # Launch worker
        worker = ScanWorker(
            session_service=self.session_service,
            session_id=self.current_session.session_id,
            device=self.current_device,
            enable_carving=enable_carving,
            scan_lost_volumes=scan_lost_volumes,
            parent=self,
        )
        worker.progress_updated.connect(self.scan_progress_page.update_progress)
        worker.scan_completed.connect(self._on_scan_completed)
        worker.scan_failed.connect(self._on_scan_failed)
        worker.scan_cancelled.connect(self._on_scan_cancelled)
        worker.finished.connect(self._on_scan_worker_finished)
        worker.finished.connect(worker.deleteLater)

        self.active_scan_worker = worker
        if self.status_bar:
            self.status_bar.showMessage("Scan in progress (strictly read-only)...")
        worker.start()

    def _on_scan_worker_finished(self) -> None:
        self.active_scan_worker = None

    def _on_scan_completed(self, result: Any) -> None:
        if self.status_bar:
            self.status_bar.showMessage(
                f"Scan complete: {len(result.candidates)} candidates discovered."
            )

        self.results_page.set_candidates(result.candidates)
        self.dashboard_page.refresh_sessions()
        self._navigate_to(4)  # Navigate to Results page

    def _on_scan_failed(self, error_msg: str) -> None:
        if self.status_bar:
            self.status_bar.showMessage("Scan encountered an error.")
        QMessageBox.critical(
            self,
            "Scan Error",
            f"The recovery scan encountered an unexpected error:\n{error_msg}",
        )
        self._navigate_to(2)

    def _on_scan_cancelled(self) -> None:
        if self.status_bar:
            self.status_bar.showMessage("Scan was cancelled safely by user.")
        QMessageBox.information(
            self,
            "Scan Cancelled",
            "The scan was cleanly stopped. Any candidates discovered prior "
            "to cancellation are preserved.",
        )
        if self.current_session:
            cands = self.session_service.candidate_repo.get_by_session(
                self.current_session.session_id
            )
            self.results_page.set_candidates(cands)
        self._navigate_to(4)

    def _on_cancel_scan(self) -> None:
        if self.active_scan_worker:
            self.scan_progress_page.cancel_btn.setEnabled(False)
            self.active_scan_worker.cancel()

    def _on_preview_candidate(self, candidate: RecoveryCandidate) -> None:
        if not self.current_device:
            QMessageBox.warning(self, "No Device", "No active device loaded for preview.")
            return

        dialog = FilePreviewDialog(candidate, self.current_device, parent=self)
        dialog.exec()

    def _on_recover_candidates(self, candidate_ids: list[str]) -> None:
        if not self.current_session or not self.current_device:
            return

        total_bytes = 0
        cands_map = {c.candidate_id: c for c in self.results_page.all_candidates}
        for cid in candidate_ids:
            if cid in cands_map:
                total_bytes += cands_map[cid].size_bytes

        # Open destination separation dialog
        dialog = RecoveryDestinationDialog(
            source_device=self.current_device,
            resolver=self.resolver,
            total_files=len(candidate_ids),
            total_bytes=total_bytes,
            parent=self,
        )
        if dialog.exec() != RecoveryDestinationDialog.DialogCode.Accepted:
            return

        dest_dir = dialog.selected_destination
        if not dest_dir:
            return

        # Setup Progress Dialog for recovery
        progress_dlg = QProgressDialog(
            "Extracting recovered files to verified destination...",
            "Cancel",
            0,
            len(candidate_ids),
            self,
        )
        progress_dlg.setWindowTitle("Recovering Files")
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setValue(0)
        progress_dlg.show()

        worker = RecoveryWorker(
            session_service=self.session_service,
            session_id=self.current_session.session_id,
            device=self.current_device,
            candidate_ids=candidate_ids,
            destination_dir=dest_dir,
            collision_policy=dialog.selected_policy,
            parent=self,
        )

        def on_recovery_progress(current: int, total: int, fname: str) -> None:
            progress_dlg.setLabelText(f"Extracting ({current}/{total}): {fname}")
            progress_dlg.setValue(current)

        def on_recovery_done(results: list[Any]) -> None:
            progress_dlg.close()
            self.active_recovery_worker = None
            success_count = sum(1 for r in results if r.success)
            QMessageBox.information(
                self,
                "Recovery Complete",
                f"Successfully extracted {success_count} file(s) to:\n{dest_dir}",
            )
            self._on_view_report()

        def on_recovery_error(err: str) -> None:
            progress_dlg.close()
            self.active_recovery_worker = None
            QMessageBox.critical(self, "Recovery Failed", f"File extraction failed:\n{err}")

        worker.progress_updated.connect(on_recovery_progress)
        worker.recovery_completed.connect(on_recovery_done)
        worker.recovery_failed.connect(on_recovery_error)

        self.active_recovery_worker = worker
        worker.start()

    def _on_view_report(self) -> None:
        if self.current_session:
            self.report_page.load_session(self.current_session.session_id)
            self._navigate_to(5)  # Report Page

    def _on_back_to_dashboard(self) -> None:
        self.dashboard_page.refresh_sessions()
        self._navigate_to(0)

    def _on_demo_mode_toggled(self, enabled: bool) -> None:
        self.demo_banner.setVisible(enabled)
        if enabled:
            # Create synthetic demo image in temporary directory
            if self._demo_temp_dir is None:
                self._demo_temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
            demo_img = Path(self._demo_temp_dir.name) / "recoverx_demo_synthetic.raw"
            if not demo_img.exists():
                create_demo_fat16_image(demo_img)
            self.device_page.load_image(str(demo_img))
            if self.status_bar:
                self.status_bar.showMessage("Demo mode active: Synthetic test image loaded.")
            self._navigate_to(1)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Enforce graceful termination of worker threads upon exit."""
        is_scanning = self.active_scan_worker is not None and self.active_scan_worker.isRunning()
        is_recovering = (
            self.active_recovery_worker is not None and self.active_recovery_worker.isRunning()
        )

        if is_scanning or is_recovering:
            reply = QMessageBox.question(
                self,
                "Exit Confirmation",
                "A recovery operation is currently running in the background.\n"
                "Are you sure you want to cancel and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            if self.active_scan_worker:
                self.active_scan_worker.cancel()
                self.active_scan_worker.wait(2000)

            if self.active_recovery_worker:
                self.active_recovery_worker.wait(2000)

        if self.device_page.current_reader:
            with contextlib.suppress(Exception):
                self.device_page.current_reader.close()
                self.device_page.current_reader = None

        if self.current_device:
            with contextlib.suppress(Exception):
                self.current_device.close()
                self.current_device = None

        if self._demo_temp_dir:
            with contextlib.suppress(Exception):
                self._demo_temp_dir.cleanup()

        event.accept()
