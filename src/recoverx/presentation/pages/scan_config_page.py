"""Scan configuration page allowing users to configure scan scope and carving options."""

import logging
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ScanConfigurationPage(QWidget):
    """Scan configuration page to select filesystem metadata sweep and signature carving."""

    scan_requested = Signal(bool, bool)  # enable_carving, scan_lost_volumes
    back_requested = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.device_summary_text: str = ""
        self._selected_mode: int = 1  # 0: Quick, 1: Deep, 2: Full (Hybrid)

        self.setAccessibleName("Scan Configuration Page")
        self.setAccessibleDescription(
            "Configure scan parameters: quick metadata scan, "
            "lost volume sweep, or deep signature carving"
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

        title = QLabel("Configure Recovery Scan")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Scan Configuration Page Title")
        header_text.addWidget(title)

        self.subtitle = QLabel("Select scan depth, filesystem analysis, and target file signatures")
        self.subtitle.setProperty("class", "PageSubtitle")
        header_text.addWidget(self.subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)

        change_btn = QPushButton("Change Media")
        change_btn.setProperty("class", "SecondaryButton")
        change_btn.clicked.connect(self.back_requested.emit)
        header_layout.addWidget(change_btn)
        layout.addLayout(header_layout)

        # Selected Media Banner (Kept for compatibility and clear target display)
        self.media_banner = QFrame()
        self.media_banner.setProperty("class", "CardFrame")
        media_layout = QHBoxLayout(self.media_banner)
        media_layout.setContentsMargins(14, 8, 14, 8)
        self.media_info_lbl = QLabel("<strong>Target Storage:</strong> No device selected.")
        self.media_info_lbl.setAccessibleName("Selected Media Target")
        media_layout.addWidget(self.media_info_lbl)
        media_layout.addStretch(1)
        layout.addWidget(self.media_banner)

        # 2. Scan Mode Cards (Screenshot 3: Quick Scan, Deep Scan, Full Scan)
        mode_header = QLabel("<strong>Scan Mode & Scope</strong>")
        mode_header.setStyleSheet("font-size: 14px; color: #f8fafc;")
        layout.addWidget(mode_header)

        self.mode_cards_layout = QHBoxLayout()
        self.mode_cards_layout.setSpacing(14)

        # Card 0: Quick Scan
        self.card_quick = self._build_mode_card(
            index=0,
            icon="⚡",
            title="Quick Scan",
            badge="Recommended",
            badge_class="BadgeReady",
            desc=(
                "Scans filesystem metadata (MFT, FAT, Directory tables) to find "
                "recently deleted files and intact folder trees."
            ),
            bullets=[
                "✓ Very fast (1-5 minutes)",
                "✓ Preserves original file paths and names",
                "✓ Recovers folder hierarchy and timestamps",
            ],
            est_time="~2 - 5 minutes",
        )
        self.mode_cards_layout.addWidget(self.card_quick)

        # Card 1: Deep Scan (Selected by default)
        self.card_deep = self._build_mode_card(
            index=1,
            icon="🔍",
            title="Deep Scan",
            badge="Thorough",
            badge_class="BadgeBlue",
            desc=(
                "Sector-by-sector signature carving scanning unallocated space for "
                "file headers and footers across all raw blocks."
            ),
            bullets=[
                "✓ Recovers files from formatted or corrupt drives",
                "✓ Detects 50+ file types by binary signature",
                "✓ Recovers fragments without filesystem metadata",
            ],
            est_time="~45 - 90 minutes",
        )
        self.mode_cards_layout.addWidget(self.card_deep)

        # Card 2: Full Scan (Hybrid)
        self.card_hybrid = self._build_mode_card(
            index=2,
            icon="📚",
            title="Full Scan (Hybrid)",
            badge="Maximum",
            badge_class="BadgeSlate",
            desc=(
                "Combines quick metadata parsing with deep signature carving "
                "for maximum file recovery potential."
            ),
            bullets=[
                "✓ Complete forensic recovery pass",
                "✓ Resolves both directory files and carved fragments",
                "✓ Cross-validates metadata against signatures",
            ],
            est_time="~1 - 2 hours",
        )
        self.mode_cards_layout.addWidget(self.card_hybrid)

        layout.addLayout(self.mode_cards_layout)

        # 3. File Types to Search (Deep Scan) Section
        types_header = QLabel("<strong>File Types to Search (Deep Scan)</strong>")
        types_header.setStyleSheet("font-size: 14px; color: #f8fafc; margin-top: 6px;")
        layout.addWidget(types_header)

        types_grid = QGridLayout()
        types_grid.setSpacing(10)

        # Type cards
        self.type_images_cb = self._build_type_card(
            "📷", "Images", "JPG, PNG, GIF, BMP, TIFF, SVG, RAW (24 formats)"
        )
        types_grid.addWidget(self.type_images_cb, 0, 0)

        self.type_docs_cb = self._build_type_card(
            "📄", "Documents", "PDF, DOCX, XLSX, PPTX, TXT, CSV, RTF (18 formats)"
        )
        types_grid.addWidget(self.type_docs_cb, 0, 1)

        self.type_videos_cb = self._build_type_card(
            "🎬", "Videos", "MP4, MKV, AVI, MOV, WMV, FLV, WebM (12 formats)"
        )
        types_grid.addWidget(self.type_videos_cb, 0, 2)

        self.type_archives_cb = self._build_type_card(
            "📦", "Archives", "ZIP, RAR, 7Z, TAR, GZ, ISO, CAB (8 formats)"
        )
        types_grid.addWidget(self.type_archives_cb, 0, 3)

        self.type_others_cb = self._build_type_card(
            "📁", "Other Files", "Audio (MP3, WAV), Code, Database, Custom"
        )
        types_grid.addWidget(self.type_others_cb, 0, 4)

        layout.addLayout(types_grid)

        # Backward compatibility checkboxes (hidden or synchronized)
        self.lost_vol_cb = QCheckBox("Scan for Lost Partition Boot Sectors")
        self.lost_vol_cb.setChecked(True)
        self.lost_vol_cb.setVisible(False)
        layout.addWidget(self.lost_vol_cb)

        self.carving_cb = QCheckBox("Enable Deep Signature Carving")
        self.carving_cb.setChecked(False)
        self.carving_cb.setVisible(False)
        self.carving_cb.toggled.connect(self._on_carving_toggled)
        layout.addWidget(self.carving_cb)

        # Deep carving warning box (initially hidden or shown when carving is active)
        self.carving_warning = QFrame()
        self.carving_warning.setProperty("class", "WarningBox")
        self.carving_warning.setAccessibleName("Deep Carving Warning Box")
        warn_layout = QVBoxLayout(self.carving_warning)
        warn_layout.setContentsMargins(14, 10, 14, 10)
        warn_title = QLabel("<strong>Notice: Deep Signature Carving Duration</strong>")
        warn_title.setStyleSheet("color: #facc15; font-size: 13px;")
        warn_text = QLabel(
            "Deep carving reads every single sector sequentially across the entire storage "
            "capacity. On high-capacity media, carving may take 45+ minutes."
        )
        warn_text.setWordWrap(True)
        warn_layout.addWidget(warn_title)
        warn_layout.addWidget(warn_text)
        self.carving_warning.setVisible(False)
        layout.addWidget(self.carving_warning)

        layout.addStretch(1)

        # 4. Bottom Action Bar
        bottom_bar = QHBoxLayout()
        back_btn = QPushButton("← Back to Media Selection")
        back_btn.setProperty("class", "SecondaryButton")
        back_btn.setAccessibleName("Back to Media Selection Button")
        back_btn.clicked.connect(self.back_requested.emit)
        bottom_bar.addWidget(back_btn)

        bottom_bar.addStretch(1)

        adv_btn = QPushButton("Advanced Options...")
        adv_btn.setProperty("class", "SecondaryButton")
        bottom_bar.addWidget(adv_btn)

        self.start_scan_btn = QPushButton("Start Scan →")
        self.start_scan_btn.setProperty("class", "PrimaryButton")
        self.start_scan_btn.setAccessibleName("Start Recovery Scan Button")
        self.start_scan_btn.clicked.connect(self._on_start_scan_clicked)
        bottom_bar.addWidget(self.start_scan_btn)

        layout.addLayout(bottom_bar)

        # Set initial visual selection
        self._select_mode(0)

    def _build_mode_card(
        self,
        index: int,
        icon: str,
        title: str,
        badge: str,
        badge_class: str,
        desc: str,
        bullets: list[str],
        est_time: str,
    ) -> QFrame:
        card = QFrame()
        card.setProperty("class", "CardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        # Header: Icon, Title, Badge
        header = QHBoxLayout()
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 20px;")
        header.addWidget(icon_lbl)

        title_lbl = QLabel(f"<strong>{title}</strong>")
        title_lbl.setStyleSheet("font-size: 15px; color: #f8fafc;")
        header.addWidget(title_lbl)
        header.addStretch(1)

        badge_lbl = QLabel(badge)
        badge_lbl.setProperty("class", badge_class)
        header.addWidget(badge_lbl)
        card_layout.addLayout(header)

        # Description
        desc_lbl = QLabel(desc)
        desc_lbl.setProperty("class", "MutedText")
        desc_lbl.setWordWrap(True)
        desc_lbl.setMinimumHeight(38)
        card_layout.addWidget(desc_lbl)

        # Bullets
        bullets_layout = QVBoxLayout()
        bullets_layout.setSpacing(4)
        for b in bullets:
            b_lbl = QLabel(b)
            b_lbl.setStyleSheet("color: #cbd5e1; font-size: 12px;")
            bullets_layout.addWidget(b_lbl)
        card_layout.addLayout(bullets_layout)

        card_layout.addStretch(1)

        # Footer: Estimated time & Select button
        footer = QHBoxLayout()
        time_lbl = QLabel(est_time)
        time_lbl.setProperty("class", "MutedText")
        footer.addWidget(time_lbl)
        footer.addStretch(1)

        sel_btn = QPushButton("Select")
        sel_btn.clicked.connect(lambda idx=index: self._select_mode(idx))
        footer.addWidget(sel_btn)
        card_layout.addLayout(footer)

        return card

    def _build_type_card(self, icon: str, title: str, sub: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "CardFrame")
        inner = QVBoxLayout(frame)
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(4)

        top = QHBoxLayout()
        cb = QCheckBox()
        cb.setChecked(True)
        top.addWidget(cb)

        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 14px;")
        top.addWidget(ic)

        tl = QLabel(f"<strong>{title}</strong>")
        tl.setStyleSheet("color: #f8fafc; font-size: 13px;")
        top.addWidget(tl)
        top.addStretch(1)
        inner.addLayout(top)

        sub_lbl = QLabel(sub)
        sub_lbl.setProperty("class", "MutedText")
        sub_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
        sub_lbl.setWordWrap(True)
        inner.addWidget(sub_lbl)

        return frame

    def _select_mode(self, index: int) -> None:
        self._selected_mode = index

        self.card_quick.setProperty("class", "CardFrameSelected" if index == 0 else "CardFrame")
        self.card_deep.setProperty("class", "CardFrameSelected" if index == 1 else "CardFrame")
        self.card_hybrid.setProperty("class", "CardFrameSelected" if index == 2 else "CardFrame")

        self.card_quick.style().unpolish(self.card_quick)
        self.card_quick.style().polish(self.card_quick)
        self.card_deep.style().unpolish(self.card_deep)
        self.card_deep.style().polish(self.card_deep)
        self.card_hybrid.style().unpolish(self.card_hybrid)
        self.card_hybrid.style().polish(self.card_hybrid)

        # Update carving_cb logic
        carving_active = index in (1, 2)
        self.carving_cb.setChecked(carving_active)
        self.lost_vol_cb.setChecked(index in (0, 1, 2))

    def _on_carving_toggled(self, checked: bool) -> None:
        self.carving_warning.setVisible(checked)

    def set_target_info(self, summary_text: str) -> None:
        """Set summary information about the target storage device."""
        self.device_summary_text = summary_text
        self.media_info_lbl.setText(f"<strong>Target Storage:</strong> {summary_text}")
        self.subtitle.setText(
            f"Select scan depth, filesystem analysis, and target file signatures for {summary_text}"
        )

    def _on_start_scan_clicked(self) -> None:
        enable_carving = self.carving_cb.isChecked()
        scan_lost_volumes = self.lost_vol_cb.isChecked()
        self.scan_requested.emit(enable_carving, scan_lost_volumes)
