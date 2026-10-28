"""Dashboard home page displaying recent sessions, recovery actions, and safety guidance."""

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from recoverx.services.session_service import SessionService


class DashboardPage(QWidget):
    """Main dashboard page for launching recovery and managing historical sessions."""

    start_recovery_requested = Signal()
    resume_session_requested = Signal(str)  # session_id

    def __init__(self, session_service: SessionService, parent: Any = None) -> None:
        super().__init__(parent)
        self.session_service = session_service

        self.setAccessibleName("Dashboard Page")
        self.setAccessibleDescription(
            "Overview dashboard with quick start recovery actions, "
            "safety guidance, and recent sessions"
        )

        self._setup_ui()
        self.refresh_sessions()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header title
        title = QLabel("Dashboard")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Dashboard Page Title")
        layout.addWidget(title)

        # Safety Guidance Banner (CLAUDE.md Rule 1)
        safety_banner = QFrame()
        safety_banner.setProperty("class", "NoticeBox")
        safety_banner.setAccessibleName("Forensic Safety Notice")
        banner_layout = QVBoxLayout(safety_banner)
        banner_title = QLabel("<strong>Forensic Non-Destructive Storage Safety</strong>")
        banner_desc = QLabel(
            "RecoverX operates strictly in read-only mode on the source storage medium. "
            "To prevent Windows background indexing or thumbnail writing on removable media, "
            "using a hardware write-blocker is strongly recommended for "
            "forensic investigations."
        )
        banner_desc.setWordWrap(True)
        banner_layout.addWidget(banner_title)
        banner_layout.addWidget(banner_desc)
        layout.addWidget(safety_banner)

        # Action bar
        action_card = QFrame()
        action_card.setProperty("class", "CardFrame")
        action_card_layout = QHBoxLayout(action_card)

        action_desc = QLabel(
            "<strong>Ready to recover data?</strong><br>"
            "<span style='color: #64748b;'>Select a storage device or disk image "
            "to begin triage and scanning.</span>"
        )
        action_desc.setAccessibleName("Start recovery action description")
        action_card_layout.addWidget(action_desc)

        start_btn = QPushButton("Start New Recovery")
        start_btn.setProperty("class", "PrimaryButton")
        start_btn.setAccessibleName("Start New Recovery Button")
        start_btn.clicked.connect(self.start_recovery_requested.emit)
        action_card_layout.addWidget(start_btn)
        layout.addWidget(action_card)

        # Recent sessions table
        table_label = QLabel("Recent Recovery Sessions")
        table_label.setProperty("class", "SectionHeader")
        table_label.setAccessibleName("Recent recovery sessions header")
        layout.addWidget(table_label)

        self.session_table = QTableWidget()
        self.session_table.setAccessibleName("Recent Sessions Table")
        self.session_table.setColumnCount(5)
        self.session_table.setHorizontalHeaderLabels(
            ["Session ID", "Name", "Source Device / Image", "Triage Health", "Status"]
        )
        self.session_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.session_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.session_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.session_table)

    def refresh_sessions(self) -> None:
        """Reload historical sessions from the persistent SQLite database."""
        sessions = self.session_service.list_sessions()
        self.session_table.setRowCount(len(sessions))

        for row, s in enumerate(sessions):
            self.session_table.setItem(row, 0, QTableWidgetItem(s.session_id))
            self.session_table.setItem(row, 1, QTableWidgetItem(s.name))
            self.session_table.setItem(row, 2, QTableWidgetItem(s.source_path))
            self.session_table.setItem(row, 3, QTableWidgetItem(s.triage_status.value))
            self.session_table.setItem(row, 4, QTableWidgetItem(s.status.capitalize()))
