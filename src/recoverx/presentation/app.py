"""Application factory and launcher for RecoverX PySide6 GUI."""

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from recoverx.config import AppConfig
from recoverx.infrastructure.persistence.db import DatabaseManager
from recoverx.infrastructure.storage.resolver import (
    FakeVolumeIdentityResolver,
    VolumeIdentityResolver,
)
from recoverx.infrastructure.storage.win32.resolver import WindowsVolumeIdentityResolver
from recoverx.presentation.main_window import MainWindow
from recoverx.presentation.theme import apply_theme
from recoverx.services.device_triage_service import DeviceTriageService
from recoverx.services.report_service import ReportService
from recoverx.services.session_service import SessionService

logger = logging.getLogger(__name__)


def create_application(
    db_path: Path | None = None,
    theme: str = "light",
    resolver: VolumeIdentityResolver | None = None,
) -> tuple[QApplication, MainWindow]:
    """Initialize and construct the RecoverX desktop application and services."""
    config = AppConfig()
    if db_path is None:
        db_path = config.work_directory / "recoverx.db"

    # Ensure application directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize persistence and services
    db_manager = DatabaseManager(db_path)
    if resolver is None:
        if sys.platform == "win32":
            resolver = WindowsVolumeIdentityResolver()
        else:
            resolver = FakeVolumeIdentityResolver()

    session_service = SessionService(db_manager=db_manager, resolver=resolver)
    triage_service = DeviceTriageService()
    report_service = ReportService()

    # Create Qt App
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
        app.setApplicationName("RecoverX")
        app.setOrganizationName("RecoverX Forensic Data Recovery")

    apply_theme(app, theme)

    window = MainWindow(
        session_service=session_service,
        triage_service=triage_service,
        report_service=report_service,
        resolver=resolver,
    )

    return app, window


def main() -> int:
    """Entry point for GUI execution."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app, window = create_application()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
