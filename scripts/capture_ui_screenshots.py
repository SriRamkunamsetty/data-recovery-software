"""Render and capture pixel-perfect PNG screenshots of all RecoverX UI pages and dialogs."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

# Support headless / offscreen rendering if required
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, DeviceTriageStatus, RecoverySourceMethod
from recoverx.domain.scan import ScanProgress
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.fixtures import SyntheticImageBuilder
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.infrastructure.storage.resolver import FakeVolumeIdentityResolver
from recoverx.presentation.dialogs.destination_dialog import RecoveryDestinationDialog
from recoverx.presentation.dialogs.preview_dialog import FilePreviewDialog
from recoverx.presentation.main_window import MainWindow
from recoverx.presentation.theme import DARK_THEME_QSS, LIGHT_THEME_QSS, apply_theme
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.report_service import ReportService
from recoverx.services.session_service import SessionService
from tests.fixtures.sample_files import create_minimal_png


def capture_screenshots(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)

    # Preload Windows TrueType fonts so offscreen platform renders real text
    for fp in [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\segoeuii.ttf",
        r"C:\Windows\Fonts\segoeuiz.ttf",
        r"C:\Windows\Fonts\seguiemj.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
    ]:
        if os.path.exists(fp):
            QFontDatabase.addApplicationFont(fp)

    app.setFont(QFont("Segoe UI", 10))

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp_path = Path(tmp_str)
        db_path = tmp_path / "ui_demo.db"
        db_mgr = DatabaseManager(db_path)
        resolver = FakeVolumeIdentityResolver()
        session_service = SessionService(db_mgr, resolver)
        triage_service = DeviceTriageService()
        report_service = ReportService()

        # Build sample disk image
        builder = SyntheticImageBuilder(total_size_bytes=2 * 1024 * 1024)
        sample_img = tmp_path / "sample_usb.raw"
        builder.build(sample_img)

        apply_theme(app, "dark")
        win = MainWindow(
            session_service=session_service,
            triage_service=triage_service,
            report_service=report_service,
            resolver=resolver,
        )
        win.resize(1280, 820)
        win.show()
        app.processEvents()

        captured_files: list[Path] = []

        def save_window(name: str) -> Path:
            app.processEvents()
            pix = win.grab()
            dest = output_dir / f"{name}.png"
            pix.save(str(dest), "PNG")
            web_dest = Path("website/assets") / f"{name}.png"
            if web_dest.parent.exists():
                pix.save(str(web_dest), "PNG")
            print(f"Captured {dest.name}")
            captured_files.append(dest)
            return dest

        # 1. Dashboard
        win._navigate_to(0)
        save_window("01_dashboard")

        # 2. Devices page with sample loaded
        win._navigate_to(1)
        win.device_page.load_image(str(sample_img))
        app.processEvents()
        save_window("02_device_selection")

        # 3. Scan Configuration
        win._navigate_to(2)
        save_window("03_scan_configuration")

        # 4. Scan Progress (Simulated active scan)
        win._navigate_to(3)
        win.scan_progress_page.reset()
        win.scan_progress_page.update_progress(
            ScanProgress(
                phase="Carving: Scanning clusters for file signatures...",
                bytes_scanned=1024 * 1024 * 42,
                total_bytes=1024 * 1024 * 64,
                elapsed_seconds=4.2,
                candidates_found=18,
                bad_sectors_found=3,
                current_sector=86016,
                estimated_remaining_seconds=2.2,
            )
        )
        save_window("04_scan_progress")

        # 5. Recovery Results with candidates
        win._navigate_to(4)
        cands = [
            RecoveryCandidate(
                candidate_id="cand-001",
                source_offset=2048,
                size_bytes=142850,
                filename="DCIM_0042.JPG",
                extension="jpg",
                status=CandidateStatus.PREVIEW_VALIDATED,
                relative_path="Photos/DCIM_0042.JPG",
                source_method=RecoverySourceMethod.METADATA,
                sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                notes="Recovered via exFAT entry set; valid JPEG markers",
            ),
            RecoveryCandidate(
                candidate_id="cand-002",
                source_offset=163840,
                size_bytes=245910,
                filename="Quarterly_Financials.xlsx",
                extension="xlsx",
                status=CandidateStatus.METADATA_RECOVERED,
                relative_path="Documents/Quarterly_Financials.xlsx",
                source_method=RecoverySourceMethod.METADATA,
                sha256_hash="a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef0",
                notes="Recovered via FAT32 LFN; unallocated contiguous chain",
            ),
            RecoveryCandidate(
                candidate_id="cand-003",
                source_offset=409600,
                size_bytes=521040,
                filename="carved_00006400.pdf",
                extension="pdf",
                status=CandidateStatus.SIGNATURE_MATCHED,
                relative_path="",
                source_method=RecoverySourceMethod.CARVED,
                sha256_hash="5e884898da28047151d0e56f8dc6292773603d0d6aabbdd62a11ef721d1542d8",
                notes="Carved PDF (%PDF-1.4); startxref and %%EOF verified",
            ),
            RecoveryCandidate(
                candidate_id="cand-004",
                source_offset=950000,
                size_bytes=81920,
                filename="customers.sqlite",
                extension="sqlite",
                status=CandidateStatus.PREVIEW_VALIDATED,
                relative_path="Databases/customers.sqlite",
                source_method=RecoverySourceMethod.METADATA,
                sha256_hash="4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
                notes="SQLite 3 database; schema verified",
            ),
            RecoveryCandidate(
                candidate_id="cand-005",
                source_offset=1200000,
                size_bytes=4096,
                filename="Notes_Corrupt.txt",
                extension="txt",
                status=CandidateStatus.OVERWRITTEN,
                relative_path="Notes_Corrupt.txt",
                source_method=RecoverySourceMethod.METADATA,
                sha256_hash=None,
                notes="Clusters reallocated in allocation bitmap; marked overwritten",
            ),
        ]
        win.results_page.set_candidates(cands)
        save_window("05_recovery_results")

        # 6. Reports Page
        win._navigate_to(5)
        sess = session_service.create_session(
            source_path=str(sample_img),
            source_device=win.device_page.current_reader,
            name="SanDisk Ultra USB 3.0",
            notes="Intact FAT32/exFAT filesystems identified with recoverable deleted files.",
        )
        session_service.candidate_repo.save_batch(sess.session_id, cands)
        win.report_page.load_session(sess.session_id)
        save_window("06_forensic_report")

        # 7. Settings Page (Dark Mode)
        apply_theme(app, "dark")
        win._navigate_to(6)
        save_window("07_application_settings")
        save_window("07_settings_dark")

        # 8. Settings Page (Light Mode)
        apply_theme(app, "light")
        win._navigate_to(6)
        save_window("08_settings_light")

        # Restore dark mode
        apply_theme(app, "dark")
        win._navigate_to(6)

        # 9. Preview Dialog
        assert win.device_page.current_reader is not None
        preview_dlg = FilePreviewDialog(
            candidate=cands[0],
            device=win.device_page.current_reader,
            parent=win,
        )
        preview_dlg.resize(750, 600)
        preview_dlg.show()
        app.processEvents()
        pix_dlg = preview_dlg.grab()
        dlg_dest = output_dir / "09_preview_dialog.png"
        pix_dlg.save(str(dlg_dest), "PNG")
        print(f"Captured {dlg_dest.name}")
        captured_files.append(dlg_dest)
        preview_dlg.close()
        try:
            if win.device_page.current_reader is not None:
                win.device_page.current_reader.close()
                win.device_page.current_reader = None
        except Exception:
            pass
        win.close()
        try:
            db_mgr.close()
        except Exception:
            pass
        app.processEvents()

    return captured_files


if __name__ == "__main__":
    out = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(r"C:\Users\moksh\.gemini\antigravity\brain\a5540785-9d40-49c1-941d-f867b1a68544\ui_screenshots")
    )
    capture_screenshots(out)
