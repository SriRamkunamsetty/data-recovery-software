"""Application settings page with theme selection, capability matrix, and demo mode toggle."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from recoverx import __version__
from recoverx.presentation.theme import apply_theme
from recoverx.presentation.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """Settings page for configuring themes, demo mode, and inspecting engine capabilities."""

    theme_changed = Signal(str)
    demo_mode_toggled = Signal(bool)

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.is_demo_mode: bool = False

        self.setAccessibleName("Settings Page")
        self.setAccessibleDescription(
            "Configure application preferences: light/dark theme, "
            "demo mode simulation, and engine capabilities"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 1. Header
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("Application Settings")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Settings Page Title")
        header_text.addWidget(title)

        subtitle = QLabel("Configure recovery engine parameters, appearance, and sandbox behavior")
        subtitle.setProperty("class", "PageSubtitle")
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)

        version_pill = QLabel(f"v{__version__} • Forensic x64")
        version_pill.setProperty("class", "BadgeSlate")
        header_layout.addWidget(version_pill)
        layout.addLayout(header_layout)

        # 2. Tabs: General, Scanning, File Types, Advanced (Screenshot 7)
        self.tabs = QTabWidget()

        # Tab 1: General Settings
        self.gen_tab = QWidget()
        gen_layout = QVBoxLayout(self.gen_tab)
        gen_layout.setContentsMargins(14, 14, 14, 14)
        gen_layout.setSpacing(16)

        # Appearance Card
        app_card = QFrame()
        app_card.setProperty("class", "CardFrame")
        app_layout = QVBoxLayout(app_card)
        app_layout.setSpacing(12)

        app_title = QLabel("<strong>Appearance & Theme</strong>")
        app_title.setStyleSheet("font-size: 14px; color: #f8fafc;")
        app_layout.addWidget(app_title)

        # Visual Theme Cards (Light vs Dark)
        theme_cards_row = QHBoxLayout()
        theme_cards_row.setSpacing(16)

        self.theme_btn_group = QButtonGroup(self)

        # Light Preview Card
        self.light_card = QFrame()
        self.light_card.setProperty("class", "CardFrame")
        self.light_card.setCursor(Qt.CursorShape.PointingHandCursor)
        lc_layout = QVBoxLayout(self.light_card)
        lc_layout.setSpacing(6)

        self.light_rb = QRadioButton("Light Mode")
        self.light_rb.setAccessibleName("Light Mode Theme Option")
        self.theme_btn_group.addButton(self.light_rb, 0)
        lc_layout.addWidget(self.light_rb)

        light_preview = QFrame()
        light_preview.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #cbd5e1; "
            "border-radius: 6px; min-height: 40px;"
        )
        lp_layout = QHBoxLayout(light_preview)
        lp_lbl = QLabel("<span style='color: #0f172a;'>Clean Light Theme</span>")
        lp_layout.addWidget(lp_lbl)
        lc_layout.addWidget(light_preview)
        theme_cards_row.addWidget(self.light_card)

        # Dark Preview Card (Default active)
        self.dark_card = QFrame()
        self.dark_card.setProperty("class", "CardFrameSelected")
        self.dark_card.setCursor(Qt.CursorShape.PointingHandCursor)
        dc_layout = QVBoxLayout(self.dark_card)
        dc_layout.setSpacing(6)

        self.dark_rb = QRadioButton("Dark Mode (Default)")
        self.dark_rb.setAccessibleName("Dark Mode Theme Option")
        self.dark_rb.setChecked(True)
        self.theme_btn_group.addButton(self.dark_rb, 1)
        dc_layout.addWidget(self.dark_rb)

        dark_preview = QFrame()
        dark_preview.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #334155; "
            "border-radius: 6px; min-height: 40px;"
        )
        dp_layout = QHBoxLayout(dark_preview)
        dp_lbl = QLabel("<span style='color: #60a5fa;'>Forensic Slate Dark Theme</span>")
        dp_layout.addWidget(dp_lbl)
        dc_layout.addWidget(dark_preview)
        theme_cards_row.addWidget(self.dark_card)

        self.theme_btn_group.idClicked.connect(self._on_theme_selected)
        app_layout.addLayout(theme_cards_row)

        # Toggle switches row
        toggles_layout = QVBoxLayout()
        toggles_layout.setSpacing(10)

        # Toggle 1: System theme
        t1_row = QHBoxLayout()
        sw1 = ToggleSwitch()
        t1_row.addWidget(sw1)
        t1_lbl = QLabel("Use operating system theme preference automatically")
        t1_lbl.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        t1_row.addWidget(t1_lbl)
        t1_row.addStretch(1)
        toggles_layout.addLayout(t1_row)

        # Toggle 2: Preview thumbnails
        t2_row = QHBoxLayout()
        sw2 = ToggleSwitch()
        sw2.setChecked(True)
        t2_row.addWidget(sw2)
        t2_lbl = QLabel("Show preview thumbnails in discovered files table")
        t2_lbl.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        t2_row.addWidget(t2_lbl)
        t2_row.addStretch(1)
        toggles_layout.addLayout(t2_row)

        # Toggle 3: Notifications
        t3_row = QHBoxLayout()
        sw3 = ToggleSwitch()
        sw3.setChecked(True)
        t3_row.addWidget(sw3)
        t3_lbl = QLabel("Enable desktop notifications upon scan completion")
        t3_lbl.setStyleSheet("color: #cbd5e1; font-size: 13px;")
        t3_row.addWidget(t3_lbl)
        t3_row.addStretch(1)
        toggles_layout.addLayout(t3_row)

        app_layout.addLayout(toggles_layout)
        gen_layout.addWidget(app_card)

        # Testing & Simulation Mode Card (Demo Mode)
        demo_card = QFrame()
        demo_card.setProperty("class", "CardFrame")
        demo_layout = QVBoxLayout(demo_card)
        demo_layout.setSpacing(8)

        demo_title = QLabel("<strong>Testing & Simulation Mode</strong>")
        demo_title.setStyleSheet("font-size: 14px; color: #f8fafc;")
        demo_layout.addWidget(demo_title)

        demo_row = QHBoxLayout()
        self.demo_cb = QCheckBox("Enable Demo Mode (Synthetic In-Memory Devices)")
        self.demo_cb.setChecked(False)
        self.demo_cb.setAccessibleName("Enable Demo Mode Simulation Checkbox")
        self.demo_cb.toggled.connect(self._on_demo_toggled)
        demo_row.addWidget(self.demo_cb)
        demo_layout.addLayout(demo_row)

        demo_desc = QLabel(
            "When enabled, RecoverX creates synthetic FAT/exFAT test images with "
            "known deleted files for training and verification purposes. Real physical "
            "media is not accessed. <strong>Demo mode is disabled by default.</strong>"
        )
        demo_desc.setWordWrap(True)
        demo_desc.setProperty("class", "MutedText")
        demo_layout.addWidget(demo_desc)
        gen_layout.addWidget(demo_card)

        # Engine Capabilities (Detected) Table Card (Screenshot 7)
        cap_card = QFrame()
        cap_card.setProperty("class", "CardFrame")
        cap_card_layout = QVBoxLayout(cap_card)
        cap_card_layout.setSpacing(10)

        cap_title = QLabel("<strong>Engine Capabilities (Detected Subsystems)</strong>")
        cap_title.setStyleSheet("font-size: 14px; color: #f8fafc;")
        cap_card_layout.addWidget(cap_title)

        self.cap_table = QTableWidget()
        self.cap_table.setColumnCount(3)
        self.cap_table.setHorizontalHeaderLabels(
            ["Subsystem / Engine", "Scope & Protocols", "Status"]
        )
        self.cap_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.cap_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.cap_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.cap_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cap_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cap_table.setMinimumHeight(160)

        capabilities = [
            (
                "FAT12 / FAT16 / FAT32 Driver",
                "FAT directory tables, short/long filenames, cluster chains",
                "Verified",
            ),
            (
                "exFAT Filesystem Driver",
                "Stream extensions, cluster allocation bitmap, directory entries",
                "Verified",
            ),
            ("NTFS Directory Parser", "NTFS $MFT & $LogFile parsing", "Pending (M12)"),
            (
                "Document & Archive Carver",
                "PDF, ZIP, DOCX, XLSX structural headers & EOF markers",
                "Verified",
            ),
            ("Image Signature Carver", "JPEG (EXIF), PNG, GIF, BMP magic signatures", "Verified"),
            ("Media / AV Stream Carver", "MP4, MOV, WAV, AVI container parsing", "Pending (M11)"),
            (
                "Win32 Physical Direct Access",
                "Direct IOCTL & sector read barrier without Win32 caching",
                "Verified",
            ),
            (
                "Win32 UAC Elevation Helper",
                "Named pipe IPC with isolated elevated child process",
                "Verified",
            ),
            ("Preview Isolation Sandbox", "Out-of-process sandboxed rendering worker", "Verified"),
        ]

        self.cap_table.setRowCount(len(capabilities))
        for row, (name, scope, status) in enumerate(capabilities):
            self.cap_table.setItem(row, 0, QTableWidgetItem(name))
            self.cap_table.setItem(row, 1, QTableWidgetItem(scope))

            status_item = QTableWidgetItem(status)
            if "Verified" in status:
                status_item.setForeground(Qt.GlobalColor.green)
            else:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self.cap_table.setItem(row, 2, status_item)

        cap_card_layout.addWidget(self.cap_table)
        gen_layout.addWidget(cap_card)

        self.tabs.addTab(self.gen_tab, "General")

        # Tab 2: Scanning
        scan_tab = QWidget()
        s_layout = QVBoxLayout(scan_tab)
        s_layout.addWidget(
            QLabel("Sector read timeout: 2000 ms • Retries: 3 • Hardware read-blocker support")
        )
        s_layout.addStretch(1)
        self.tabs.addTab(scan_tab, "Scanning")

        # Tab 3: File Types
        types_tab = QWidget()
        t_layout = QVBoxLayout(types_tab)
        t_layout.addWidget(
            QLabel("Manage known file magic signatures and custom regex definitions.")
        )
        t_layout.addStretch(1)
        self.tabs.addTab(types_tab, "File Types")

        # Tab 4: Advanced
        adv_tab = QWidget()
        a_layout = QVBoxLayout(adv_tab)
        a_layout.addWidget(
            QLabel("Audit logging level: DEBUG • Hash algorithm: SHA-256 • Database: SQLite WAL")
        )
        a_layout.addStretch(1)
        self.tabs.addTab(adv_tab, "Advanced")

        layout.addWidget(self.tabs)

    def _on_theme_selected(self, btn_id: int) -> None:
        theme_name = "dark" if btn_id == 1 else "light"
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme_name)
        self.theme_changed.emit(theme_name)

    def _on_demo_toggled(self, checked: bool) -> None:
        self.is_demo_mode = checked
        self.demo_mode_toggled.emit(checked)
