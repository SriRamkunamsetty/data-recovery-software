"""Scan configuration page allowing users to configure scan scope and carving options."""

import logging
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ScanConfigurationPage(QWidget):
    """Scan configuration page to select filesystem metadata sweep and signature carving.

    Section 12 of MASTER_PROMPT.md:
    Deep scan / carving must never start silently without an explicit user request.
    UI makes this choice explicit with realistic time warnings.
    """

    scan_requested = Signal(bool, bool)  # enable_carving, scan_lost_volumes
    back_requested = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.device_summary_text: str = ""

        self.setAccessibleName("Scan Configuration Page")
        self.setAccessibleDescription(
            "Configure scan parameters: quick metadata scan, "
            "lost volume sweep, or deep signature carving"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Configure Recovery Scan")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Scan Configuration Page Title")
        layout.addWidget(title)

        # Selected media overview
        self.media_banner = QFrame()
        self.media_banner.setProperty("class", "CardFrame")
        media_layout = QHBoxLayout(self.media_banner)
        self.media_info_lbl = QLabel("<strong>Target Storage:</strong> No device selected.")
        self.media_info_lbl.setAccessibleName("Selected Media Target")
        media_layout.addWidget(self.media_info_lbl, stretch=1)

        change_btn = QPushButton("Change Media")
        change_btn.setAccessibleName("Change Selected Media Button")
        change_btn.clicked.connect(self.back_requested.emit)
        media_layout.addWidget(change_btn)
        layout.addWidget(self.media_banner)

        # Scan mode options group
        options_group = QGroupBox("Scan Mode & Engine Options")
        options_group.setAccessibleName("Scan Options Group")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(12)

        # Quick Metadata Scan (Always enabled)
        meta_label = QLabel(
            "<strong>1. Filesystem Metadata Scan (Recommended, Fast)</strong><br>"
            "<span style='color: #64748b;'>Analyzes partition tables (MBR/GPT) "
            "and traverses directory trees on supported filesystems (FAT12/16/32, exFAT). "
            "Restores original filenames, directory paths, timestamps, "
            "and cluster chains. Completes in seconds to minutes.</span>"
        )
        meta_label.setWordWrap(True)
        options_layout.addWidget(meta_label)

        # Lost volume sweep checkbox
        self.lost_vol_cb = QCheckBox(
            "Scan for Lost / Formatted Partition Boot Sectors (Recommended)"
        )
        self.lost_vol_cb.setChecked(True)
        self.lost_vol_cb.setAccessibleName("Scan for Lost Partition Volumes Checkbox")
        self.lost_vol_cb.setAccessibleDescription(
            "Searches unallocated blocks and sector boundaries for VBR headers "
            "of previously formatted or deleted partitions"
        )
        options_layout.addWidget(self.lost_vol_cb)

        options_layout.addSpacing(8)

        # Signature Carving Checkbox (CLAUDE.md / MASTER_PROMPT.md: Never start silently)
        self.carving_cb = QCheckBox("Enable Deep Signature Carving (Raw Block Scan)")
        self.carving_cb.setChecked(False)
        self.carving_cb.setAccessibleName("Enable Deep Signature Carving Checkbox")
        self.carving_cb.setAccessibleDescription(
            "Scans every raw sector for known file magic signatures and structural markers "
            "(JPEG, PNG, PDF, ZIP)"
        )
        self.carving_cb.toggled.connect(self._on_carving_toggled)
        options_layout.addWidget(self.carving_cb)

        # Deep carving warning box (initially hidden or muted)
        self.carving_warning = QFrame()
        self.carving_warning.setProperty("class", "WarningBox")
        self.carving_warning.setAccessibleName("Deep Carving Warning Box")
        warn_layout = QVBoxLayout(self.carving_warning)
        warn_title = QLabel("<strong>Notice: Deep Signature Carving Duration</strong>")
        warn_text = QLabel(
            "Deep carving reads every single sector sequentially across the entire storage "
            "capacity. On high-capacity flash drives, SD cards, or damaged media, carving "
            "may take hours to complete. Files discovered via carving may lack original "
            "filenames and directory hierarchy. Enable carving only if metadata recovery "
            "did not recover the desired files."
        )
        warn_text.setWordWrap(True)
        warn_layout.addWidget(warn_title)
        warn_layout.addWidget(warn_text)
        self.carving_warning.setVisible(False)
        options_layout.addWidget(self.carving_warning)

        layout.addWidget(options_group)

        layout.addStretch(1)

        # Navigation action buttons
        nav_layout = QHBoxLayout()
        back_btn = QPushButton("&larr; Back")
        back_btn.setAccessibleName("Back to Media Selection Button")
        back_btn.clicked.connect(self.back_requested.emit)
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch(1)

        self.start_scan_btn = QPushButton("Start Recovery Scan &rarr;")
        self.start_scan_btn.setProperty("class", "PrimaryButton")
        self.start_scan_btn.setAccessibleName("Start Recovery Scan Button")
        self.start_scan_btn.clicked.connect(self._on_start_scan)
        nav_layout.addWidget(self.start_scan_btn)

        layout.addLayout(nav_layout)

    def set_target_info(self, summary: str) -> None:
        """Update target device summary text."""
        self.device_summary_text = summary
        self.media_info_lbl.setText(f"<strong>Target Storage:</strong> {summary}")

    def _on_carving_toggled(self, checked: bool) -> None:
        self.carving_warning.setVisible(checked)

    def _on_start_scan(self) -> None:
        enable_carving = self.carving_cb.isChecked()
        scan_lost_volumes = self.lost_vol_cb.isChecked()
        self.scan_requested.emit(enable_carving, scan_lost_volumes)
