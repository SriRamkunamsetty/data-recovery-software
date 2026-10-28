"""Application settings page with theme selection, capability matrix, and demo mode toggle."""

import logging
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from recoverx import __version__
from recoverx.presentation.theme import apply_theme

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    """Settings page for configuring themes, demo mode, and inspecting engine capabilities.

    Section 13 of MASTER_PROMPT.md:
    Explicit capability matrix showing verified scope vs pending formats.
    Demo mode is OFF by default and clearly marked as simulation only when enabled.
    """

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
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Application Settings & Engine Capabilities")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Settings Page Title")
        layout.addWidget(title)

        # Theme Selector Group
        theme_group = QGroupBox("User Interface Appearance")
        theme_group.setAccessibleName("UI Theme Selector Group")
        theme_layout = QHBoxLayout(theme_group)

        self.theme_btn_group = QButtonGroup(self)
        self.light_rb = QRadioButton("Light Mode (Default)")
        self.light_rb.setAccessibleName("Light Mode Theme Option")
        self.light_rb.setChecked(True)
        self.theme_btn_group.addButton(self.light_rb, 0)
        theme_layout.addWidget(self.light_rb)

        self.dark_rb = QRadioButton("Dark Mode")
        self.dark_rb.setAccessibleName("Dark Mode Theme Option")
        self.theme_btn_group.addButton(self.dark_rb, 1)
        theme_layout.addWidget(self.dark_rb)

        theme_layout.addStretch(1)
        self.theme_btn_group.idClicked.connect(self._on_theme_selected)
        layout.addWidget(theme_group)

        # Demo Mode Simulation (OFF by default)
        demo_group = QGroupBox("Testing & Simulation (Demo Mode)")
        demo_group.setAccessibleName("Demo Mode Simulation Group")
        demo_layout = QVBoxLayout(demo_group)

        self.demo_cb = QCheckBox("Enable Demo Mode (Synthetic In-Memory Devices)")
        self.demo_cb.setChecked(False)
        self.demo_cb.setAccessibleName("Enable Demo Mode Simulation Checkbox")
        self.demo_cb.toggled.connect(self._on_demo_toggled)
        demo_layout.addWidget(self.demo_cb)

        demo_desc = QLabel(
            "When enabled, RecoverX creates synthetic FAT/exFAT test images with "
            "known deleted files for training and verification purposes. Real physical "
            "media is not accessed. <strong>Demo mode is disabled by default.</strong>"
        )
        demo_desc.setWordWrap(True)
        demo_desc.setStyleSheet("color: #64748b; font-size: 12px;")
        demo_layout.addWidget(demo_desc)

        layout.addWidget(demo_group)

        # Engine Capability Matrix (Section 13 of MASTER_PROMPT.md)
        cap_group = QGroupBox("Engine Verified Scope & Capability Matrix")
        cap_group.setAccessibleName("Engine Capability Matrix Group")
        cap_layout = QGridLayout(cap_group)
        cap_layout.setSpacing(10)

        cap_layout.addWidget(QLabel("<strong>Filesystem Recovery:</strong>"), 0, 0)
        cap_layout.addWidget(QLabel("FAT12, FAT16, FAT32, exFAT"), 0, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Verified & Supported</span>"),
            0,
            2,
        )

        cap_layout.addWidget(QLabel("<strong>Filesystem Recovery (NTFS):</strong>"), 1, 0)
        cap_layout.addWidget(QLabel("NTFS ($MFT parsing)"), 1, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #ca8a04; font-weight: 600;'>Pending Milestone M12</span>"),
            1,
            2,
        )

        cap_layout.addWidget(QLabel("<strong>Signature Carving (Document/Image):</strong>"), 2, 0)
        cap_layout.addWidget(QLabel("JPEG, PNG, PDF, ZIP/DOCX/XLSX"), 2, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Verified & Supported</span>"),
            2,
            2,
        )

        cap_layout.addWidget(QLabel("<strong>Signature Carving (Media/AV):</strong>"), 3, 0)
        cap_layout.addWidget(QLabel("MP4, MOV, WAV, AVI, Camera RAW"), 3, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #ca8a04; font-weight: 600;'>Pending Milestone M11</span>"),
            3,
            2,
        )

        cap_layout.addWidget(QLabel("<strong>Multi-Pass Disk Imaging:</strong>"), 4, 0)
        cap_layout.addWidget(QLabel("Copy, Trim, Scrape + ddrescue export"), 4, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Verified & Supported</span>"),
            4,
            2,
        )

        cap_layout.addWidget(QLabel("<strong>Forensic Write Safety:</strong>"), 5, 0)
        cap_layout.addWidget(QLabel("Strict Read-Only Block Handles & Volume Separation"), 5, 1)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Verified & Enforced</span>"),
            5,
            2,
        )

        layout.addWidget(cap_group)

        # Version and build info
        info_frame = QFrame()
        info_frame.setProperty("class", "CardFrame")
        info_layout = QHBoxLayout(info_frame)
        ver_lbl = QLabel(
            f"RecoverX Version: <strong>{__version__}</strong> &bull; "
            "Engine: <strong>Forensic x64</strong>"
        )
        ver_lbl.setAccessibleName("Application version label")
        info_layout.addWidget(ver_lbl)
        layout.addWidget(info_frame)

        layout.addStretch(1)

    def _on_theme_selected(self, btn_id: int) -> None:
        theme_name = "dark" if btn_id == 1 else "light"
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme_name)
        self.theme_changed.emit(theme_name)

    def _on_demo_toggled(self, checked: bool) -> None:
        self.is_demo_mode = checked
        self.demo_mode_toggled.emit(checked)
