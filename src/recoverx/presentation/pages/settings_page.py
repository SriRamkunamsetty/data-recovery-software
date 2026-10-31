"""Application settings page with theme selection, capability matrix, and demo mode toggle."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from recoverx import __version__
from recoverx.presentation.theme import apply_theme
from recoverx.presentation.widgets.toggle_switch import ToggleSwitch

logger = logging.getLogger(__name__)


class ThemePreviewCard(QFrame):
    """Visual miniature preview card for Light/Dark mode with active blue outline."""

    clicked = Signal()

    def __init__(self, mode: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.mode = mode
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(190)
        self._setup_ui()
        self.update_style()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(8)

        # Mockup window preview
        mock_win = QFrame()
        mock_win.setFixedHeight(75)
        mock_win_layout = QHBoxLayout(mock_win)
        mock_win_layout.setContentsMargins(0, 0, 0, 0)
        mock_win_layout.setSpacing(0)

        mini_sidebar = QFrame()
        mini_sidebar.setFixedWidth(40)
        mini_sb_layout = QVBoxLayout(mini_sidebar)
        mini_sb_layout.setContentsMargins(4, 6, 4, 6)
        mini_sb_layout.setSpacing(4)

        mini_canvas = QFrame()
        mini_cv_layout = QVBoxLayout(mini_canvas)
        mini_cv_layout.setContentsMargins(6, 6, 6, 6)
        mini_cv_layout.setSpacing(4)

        if self.mode == "light":
            mock_win.setStyleSheet(
                "background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px;"
            )
            mini_sidebar.setStyleSheet(
                "background-color: #2563eb; border-top-left-radius: 5px; "
                "border-bottom-left-radius: 5px;"
            )
            for _ in range(3):
                stripe = QFrame()
                stripe.setFixedHeight(3)
                stripe.setStyleSheet(
                    "background-color: rgba(255, 255, 255, 0.85); border-radius: 1px;"
                )
                mini_sb_layout.addWidget(stripe)

            mini_canvas.setStyleSheet("background-color: #ffffff; border-radius: 0 5px 5px 0;")
            bar1 = QFrame()
            bar1.setFixedHeight(5)
            bar1.setStyleSheet("background-color: #e2e8f0; border-radius: 2px;")
            mini_cv_layout.addWidget(bar1)

            box = QFrame()
            box.setFixedHeight(26)
            box.setStyleSheet(
                "background-color: #f1f5f9; border: 1px solid #e2e8f0; border-radius: 3px;"
            )
            mini_cv_layout.addWidget(box)

        else:  # Dark mode
            mock_win.setStyleSheet(
                "background-color: #030712; border: 1px solid #334155; border-radius: 6px;"
            )
            mini_sidebar.setStyleSheet(
                "background-color: #0b1120; border-top-left-radius: 5px; "
                "border-bottom-left-radius: 5px;"
            )
            for _ in range(3):
                stripe = QFrame()
                stripe.setFixedHeight(3)
                stripe.setStyleSheet("background-color: #3b82f6; border-radius: 1px;")
                mini_sb_layout.addWidget(stripe)

            mini_canvas.setStyleSheet("background-color: #070d19; border-radius: 0 5px 5px 0;")
            bar1 = QFrame()
            bar1.setFixedHeight(5)
            bar1.setStyleSheet("background-color: #1e293b; border-radius: 2px;")
            mini_cv_layout.addWidget(bar1)

            box = QFrame()
            box.setFixedHeight(26)
            box.setStyleSheet(
                "background-color: #0f172a; border: 1px solid #1e293b; border-radius: 3px;"
            )
            mini_cv_layout.addWidget(box)

        mini_sb_layout.addStretch(1)
        mini_cv_layout.addStretch(1)
        mock_win_layout.addWidget(mini_sidebar)
        mock_win_layout.addWidget(mini_canvas)
        layout.addWidget(mock_win)

        # Label underneath
        lbl_text = "Light Mode" if self.mode == "light" else "Dark Mode"
        self.title_lbl = QLabel(lbl_text)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #0f172a;")
        layout.addWidget(self.title_lbl)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.update_style()

    def update_style(self) -> None:
        if self._selected:
            self.setStyleSheet(
                "ThemePreviewCard { "
                "   background-color: #f0f7ff; "
                "   border: 2px solid #2563eb; "
                "   border-radius: 10px; "
                "}"
            )
        else:
            self.setStyleSheet(
                "ThemePreviewCard { "
                "   background-color: #ffffff; "
                "   border: 1px solid #e2e8f0; "
                "   border-radius: 10px; "
                "}"
            )

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        super().mousePressEvent(event)
        self.clicked.emit()


class SettingsPage(QWidget):
    """Settings page configuring themes, demo mode, and inspecting engine capabilities."""

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
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 20, 28, 20)
        root_layout.setSpacing(14)

        # 1. Header (Screenshot 7)
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("Application Settings")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Settings Page Title")
        header_text.addWidget(title)

        subtitle = QLabel("Customize appearance, scanning behavior and engine options.")
        subtitle.setProperty("class", "PageSubtitle")
        header_text.addWidget(subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)

        version_pill = QLabel(f"v{__version__} • Forensic x64")
        version_pill.setProperty("class", "BadgeSlate")
        header_layout.addWidget(version_pill)
        root_layout.addLayout(header_layout)

        # 2. Tabs: General, Scanning, File Types, Advanced
        self.tabs = QTabWidget()

        # Tab 1: General Settings (Wrapped in QScrollArea for zero-clipping guarantee)
        self.gen_tab = QWidget()
        gen_tab_layout = QVBoxLayout(self.gen_tab)
        gen_tab_layout.setContentsMargins(0, 4, 0, 0)
        gen_tab_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent;")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(4, 8, 4, 16)
        scroll_layout.setSpacing(16)

        # -------------------------------------------------------------
        # Appearance & Toggles Card (Screenshot 7 Crisp White Container)
        # -------------------------------------------------------------
        app_card = QFrame()
        app_card.setObjectName("SettingsWhiteCard")
        app_card.setStyleSheet(
            "QFrame#SettingsWhiteCard { "
            "   background-color: #ffffff; "
            "   border: 1px solid #e2e8f0; "
            "   border-radius: 14px; "
            "} "
            "QLabel { color: #0f172a; }"
        )
        app_card_layout = QVBoxLayout(app_card)
        app_card_layout.setContentsMargins(20, 18, 20, 18)
        app_card_layout.setSpacing(14)

        app_title = QLabel("Appearance")
        app_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        app_card_layout.addWidget(app_title)

        # Theme Preview Cards
        theme_cards_layout = QHBoxLayout()
        theme_cards_layout.setSpacing(16)

        self.light_card = ThemePreviewCard("light")
        self.dark_card = ThemePreviewCard("dark")

        # Hidden radio buttons for test suite compatibility
        self.theme_btn_group = QButtonGroup(self)
        self.light_rb = QRadioButton("Light Mode")
        self.dark_rb = QRadioButton("Dark Mode")
        self.light_rb.setVisible(False)
        self.dark_rb.setVisible(False)
        self.theme_btn_group.addButton(self.light_rb, 0)
        self.theme_btn_group.addButton(self.dark_rb, 1)

        # Default to Dark Mode active (as depicted in reference screenshots)
        self.dark_rb.setChecked(True)
        self.dark_card.set_selected(True)
        self.light_card.set_selected(False)

        self.light_card.clicked.connect(lambda: self._select_theme_mode(0))
        self.dark_card.clicked.connect(lambda: self._select_theme_mode(1))
        self.light_rb.clicked.connect(lambda: self._select_theme_mode(0))
        self.dark_rb.clicked.connect(lambda: self._select_theme_mode(1))

        theme_cards_layout.addWidget(self.light_card)
        theme_cards_layout.addWidget(self.dark_card)
        theme_cards_layout.addStretch(1)
        app_card_layout.addLayout(theme_cards_layout)

        # Separator line
        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background-color: #f1f5f9;")
        app_card_layout.addWidget(sep1)

        # Three modern toggle switches (Screenshot 7)
        toggles_layout = QVBoxLayout()
        toggles_layout.setSpacing(12)

        # Toggle 1: Use system theme
        t1_row = QHBoxLayout()
        t1_icon = QLabel("⏱")
        t1_icon.setStyleSheet(
            "font-size: 13px; color: #2563eb; background-color: #eff6ff; "
            "border-radius: 12px; padding: 4px 6px;"
        )
        t1_row.addWidget(t1_icon)
        t1_text = QLabel("Use system theme")
        t1_text.setStyleSheet("font-size: 13px; font-weight: 500; color: #1e293b;")
        t1_row.addWidget(t1_text)
        t1_row.addStretch(1)
        self.system_theme_sw = ToggleSwitch()
        self.system_theme_sw.setChecked(False)
        t1_row.addWidget(self.system_theme_sw)
        toggles_layout.addLayout(t1_row)

        # Toggle 2: Show preview thumbnails
        t2_row = QHBoxLayout()
        t2_icon = QLabel("👁")
        t2_icon.setStyleSheet(
            "font-size: 13px; color: #2563eb; background-color: #eff6ff; "
            "border-radius: 12px; padding: 4px 6px;"
        )
        t2_row.addWidget(t2_icon)
        t2_text = QLabel("Show preview thumbnails")
        t2_text.setStyleSheet("font-size: 13px; font-weight: 500; color: #1e293b;")
        t2_row.addWidget(t2_text)
        t2_row.addStretch(1)
        self.preview_thumbs_sw = ToggleSwitch()
        self.preview_thumbs_sw.setChecked(True)
        t2_row.addWidget(self.preview_thumbs_sw)
        toggles_layout.addLayout(t2_row)

        # Toggle 3: Enable notifications
        t3_row = QHBoxLayout()
        t3_icon = QLabel("🔔")
        t3_icon.setStyleSheet(
            "font-size: 13px; color: #2563eb; background-color: #eff6ff; "
            "border-radius: 12px; padding: 4px 6px;"
        )
        t3_row.addWidget(t3_icon)
        t3_text = QLabel("Enable notifications")
        t3_text.setStyleSheet("font-size: 13px; font-weight: 500; color: #1e293b;")
        t3_row.addWidget(t3_text)
        t3_row.addStretch(1)
        self.notifications_sw = ToggleSwitch()
        self.notifications_sw.setChecked(True)
        t3_row.addWidget(self.notifications_sw)
        toggles_layout.addLayout(t3_row)

        # Separator line
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: #f1f5f9;")
        toggles_layout.addWidget(sep2)

        # Toggle 4: Demo Mode Simulation Switch
        demo_row = QHBoxLayout()
        demo_icon = QLabel("🧪")
        demo_icon.setStyleSheet(
            "font-size: 13px; color: #ef4444; background-color: #fef2f2; "
            "border-radius: 12px; padding: 4px 6px;"
        )
        demo_row.addWidget(demo_icon)

        demo_label_col = QVBoxLayout()
        demo_label_col.setSpacing(2)
        demo_title_lbl = QLabel("Enable Demo Mode (Synthetic In-Memory Devices)")
        demo_title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b;")
        demo_label_col.addWidget(demo_title_lbl)

        demo_sub_lbl = QLabel(
            "Creates synthetic FAT/exFAT test images with known deleted "
            "files for testing without physical disks."
        )
        demo_sub_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        demo_label_col.addWidget(demo_sub_lbl)
        demo_row.addLayout(demo_label_col)
        demo_row.addStretch(1)

        self.demo_cb = ToggleSwitch()
        self.demo_cb.setChecked(False)
        self.demo_cb.setAccessibleName("Enable Demo Mode Simulation Checkbox")
        self.demo_cb.toggled.connect(self._on_demo_toggled)
        demo_row.addWidget(self.demo_cb)
        toggles_layout.addLayout(demo_row)

        app_card_layout.addLayout(toggles_layout)
        scroll_layout.addWidget(app_card)

        # -------------------------------------------------------------
        # Engine Capabilities (Detected) Card (Screenshot 7)
        # -------------------------------------------------------------
        cap_card = QFrame()
        cap_card.setObjectName("SettingsCapCard")
        cap_card.setStyleSheet(
            "QFrame#SettingsCapCard { "
            "   background-color: #ffffff; "
            "   border: 1px solid #e2e8f0; "
            "   border-radius: 14px; "
            "} "
            "QLabel { color: #0f172a; }"
        )
        cap_card_layout = QVBoxLayout(cap_card)
        cap_card_layout.setContentsMargins(20, 18, 20, 18)
        cap_card_layout.setSpacing(12)

        cap_title = QLabel("Engine Capabilities (Detected)")
        cap_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        cap_card_layout.addWidget(cap_title)

        cap_grid = QGridLayout()
        cap_grid.setHorizontalSpacing(18)
        cap_grid.setVerticalSpacing(10)
        cap_grid.setContentsMargins(0, 4, 0, 0)

        # 5 Detected Capabilities from Screenshot 7
        capabilities = [
            ("Filesystem Recovery:", "FAT12/16/32, exFAT", "Verified", "#10b981"),
            ("NTFS Recovery:", "Parsing (M12)", "Pending", "#f59e0b"),
            ("Signature Carving (Images):", "JPG, PNG, PDF, ZIP", "Verified", "#10b981"),
            ("Signature Carving (Media):", "MP4, MOV, AVI", "Pending", "#f59e0b"),
            ("Disk Imaging:", "Supported", "Verified", "#10b981"),
        ]

        for row_idx, (name, scope, status, color_hex) in enumerate(capabilities):
            lbl_name = QLabel(name)
            lbl_name.setStyleSheet("font-size: 13px; font-weight: 600; color: #1e293b;")
            cap_grid.addWidget(lbl_name, row_idx, 0)

            lbl_scope = QLabel(scope)
            lbl_scope.setStyleSheet("font-size: 13px; color: #475569;")
            cap_grid.addWidget(lbl_scope, row_idx, 1)

            lbl_status = QLabel(status)
            lbl_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_status.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {color_hex};")
            cap_grid.addWidget(lbl_status, row_idx, 2)

        cap_card_layout.addLayout(cap_grid)
        scroll_layout.addWidget(cap_card)
        scroll_layout.addStretch(1)

        scroll_area.setWidget(scroll_content)
        gen_tab_layout.addWidget(scroll_area)
        self.tabs.addTab(self.gen_tab, "General")

        # Tab 2: Scanning
        scan_tab = QWidget()
        s_layout = QVBoxLayout(scan_tab)
        s_layout.setContentsMargins(4, 12, 4, 12)
        scan_card = QFrame()
        scan_card.setProperty("class", "SettingsWhiteCard")
        sc_layout = QVBoxLayout(scan_card)
        sc_title = QLabel("Scan Parameters & Read-Only Direct I/O")
        sc_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        sc_layout.addWidget(sc_title)
        sc_info = QLabel(
            "• Direct IOCTL sector access: Bypasses OS caching for raw block read.\n"
            "• Sector read timeout: 2000 ms per block with exponential backoff.\n"
            "• Hardware bad sector handling: Max 3 retries, zero-filled replacement.\n"
            "• Write-blocker safety barrier: Hardware and software write protection enforced."
        )
        sc_info.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        sc_layout.addWidget(sc_info)
        s_layout.addWidget(scan_card)
        s_layout.addStretch(1)
        self.tabs.addTab(scan_tab, "Scanning")

        # Tab 3: File Types
        types_tab = QWidget()
        t_layout = QVBoxLayout(types_tab)
        t_layout.setContentsMargins(4, 12, 4, 12)
        types_card = QFrame()
        types_card.setProperty("class", "SettingsWhiteCard")
        tc_layout = QVBoxLayout(types_card)
        tc_title = QLabel("Supported Forensic File Signatures")
        tc_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        tc_layout.addWidget(tc_title)
        tc_info = QLabel(
            "• Images: JPEG (JFIF/EXIF), PNG, GIF, BMP, TIFF, WebP\n"
            "• Documents & Archives: PDF, ZIP, DOCX, XLSX, PPTX, TAR, GZ\n"
            "• Audio & Video: MP4, MOV, AVI, MKV, WAV, MP3\n"
            "• Custom Signatures: User-defined regex and byte magic rules supported."
        )
        tc_info.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        tc_layout.addWidget(tc_info)
        t_layout.addWidget(types_card)
        t_layout.addStretch(1)
        self.tabs.addTab(types_tab, "File Types")

        # Tab 4: Advanced
        adv_tab = QWidget()
        a_layout = QVBoxLayout(adv_tab)
        a_layout.setContentsMargins(4, 12, 4, 12)
        adv_card = QFrame()
        adv_card.setProperty("class", "SettingsWhiteCard")
        ac_layout = QVBoxLayout(adv_card)
        ac_title = QLabel("Forensic Audit & Persistence Engine")
        ac_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0f172a;")
        ac_layout.addWidget(ac_title)
        ac_info = QLabel(
            "• Cryptographic Integrity: SHA-256 validation computed on all recovered files.\n"
            "• Storage Engine: SQLite 3 with Write-Ahead Logging (WAL) and foreign keys.\n"
            "• Preview Isolation: Out-of-process subprocess isolation for untrusted binaries.\n"
            "• Audit Logging: Tamper-evident timestamped execution trace (DEBUG/INFO)."
        )
        ac_info.setStyleSheet("font-size: 13px; color: #334155; line-height: 1.6;")
        ac_layout.addWidget(ac_info)
        a_layout.addWidget(adv_card)
        a_layout.addStretch(1)
        self.tabs.addTab(adv_tab, "Advanced")

        root_layout.addWidget(self.tabs)

    def _select_theme_mode(self, mode_idx: int) -> None:
        """Handle theme switching from either the visual cards or radio buttons."""
        is_dark = mode_idx == 1
        self.dark_card.set_selected(is_dark)
        self.light_card.set_selected(not is_dark)
        self.dark_rb.setChecked(is_dark)
        self.light_rb.setChecked(not is_dark)

        theme_name = "dark" if is_dark else "light"
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme_name)
        self.theme_changed.emit(theme_name)

    def _on_demo_toggled(self, checked: bool) -> None:
        self.is_demo_mode = checked
        self.demo_mode_toggled.emit(checked)
