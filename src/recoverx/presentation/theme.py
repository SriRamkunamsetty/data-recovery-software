"""Modern light and dark theme stylesheets for RecoverX PySide6 desktop UI."""

from PySide6.QtWidgets import QApplication

LIGHT_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* Sidebar navigation */
QFrame#SidebarContainer {
    background-color: #070d19;
    border-right: 1px solid #1e293b;
}
QListWidget#SidebarList {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    outline: none;
    font-size: 13px;
    font-weight: 500;
}
QListWidget#SidebarList::item {
    padding: 10px 16px;
    border-radius: 8px;
    margin: 3px 12px;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:hover {
    background-color: #1e293b;
    color: #f8fafc;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3b82f6);
    color: #ffffff;
    font-weight: 600;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:selected:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3b82f6);
    color: #ffffff;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:focus,
QListWidget#SidebarList::item:selected:focus {
    border: none;
    outline: none;
}

/* Cards & containers */
QFrame.CardFrame {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
}
QFrame.CardFrameSelected {
    background-color: #eff6ff;
    border: 2px solid #2563eb;
    border-radius: 8px;
    padding: 16px;
}

/* Action Cards */
QFrame.ActionCardBlue {
    background-color: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardPurple {
    background-color: #faf5ff;
    border: 1px solid #e9d5ff;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardGreen {
    background-color: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardOrange {
    background-color: #fffbeb;
    border: 1px solid #fde68a;
    border-radius: 8px;
    padding: 14px;
}

/* Badges / Status Pills */
QLabel.BadgeReady, QLabel.BadgeSuccess {
    background-color: #dcfce7;
    color: #15803d;
    border: 1px solid #86efac;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeWarning, QLabel.BadgeNeedsCheck {
    background-color: #fef3c7;
    color: #b45309;
    border: 1px solid #fcd34d;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeDanger, QLabel.BadgeCorrupted {
    background-color: #fee2e2;
    color: #b91c1c;
    border: 1px solid #fca5a5;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeBlue, QLabel.BadgeInfo {
    background-color: #dbeafe;
    color: #1d4ed8;
    border: 1px solid #93c5fd;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeSlate {
    background-color: #f1f5f9;
    color: #475569;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

/* Headings */
QLabel.PageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #0f172a;
}
QLabel.PageSubtitle {
    font-size: 12px;
    color: #64748b;
    margin-top: 2px;
}
QLabel.SectionHeader {
    font-size: 14px;
    font-weight: 600;
    color: #1e293b;
    margin-top: 4px;
    margin-bottom: 2px;
}
QLabel.MutedText {
    color: #64748b;
    font-size: 12px;
}

/* Buttons */
QPushButton {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
    color: #1e293b;
}
QPushButton:hover {
    background-color: #f1f5f9;
    border-color: #94a3b8;
}
QPushButton:pressed {
    background-color: #e2e8f0;
}
QPushButton.PrimaryButton {
    background-color: #2563eb;
    border: 1px solid #1d4ed8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton.PrimaryButton:hover {
    background-color: #1d4ed8;
}
QPushButton.PrimaryButton:pressed {
    background-color: #1e40af;
}
QPushButton.DangerButton {
    background-color: #dc2626;
    border: 1px solid #b91c1c;
    color: #ffffff;
}
QPushButton.DangerButton:hover {
    background-color: #b91c1c;
}

/* Tables & Trees */
QTableWidget, QTreeWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    gridline-color: #f1f5f9;
    selection-background-color: #e0f2fe;
    selection-color: #0369a1;
}
QHeaderView::section {
    background-color: #f8fafc;
    color: #475569;
    font-weight: 600;
    padding: 6px 10px;
    border: 1px solid #e2e8f0;
}

/* Tab widget */
QTabWidget::pane {
    border: none;
    background: transparent;
    margin-top: 8px;
}
QTabBar::tab {
    background-color: #e2e8f0;
    color: #475569;
    padding: 8px 18px;
    margin-right: 8px;
    border-radius: 8px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

/* Settings White Card */
QFrame.SettingsWhiteCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 20px;
}
QFrame.SettingsWhiteCard QLabel {
    color: #0f172a;
}

/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}

/* Progress bar */
QProgressBar {
    background-color: #e2e8f0;
    border-radius: 6px;
    text-align: center;
    color: #0f172a;
    font-weight: 600;
    height: 14px;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 6px;
}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 6px 10px;
    color: #0f172a;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #2563eb;
}

/* Notice box */
QFrame.NoticeBox {
    background-color: #eff6ff;
    border-left: 4px solid #3b82f6;
    border-radius: 4px;
    padding: 12px;
}
QFrame.WarningBox {
    background-color: #fefce8;
    border-left: 4px solid #eab308;
    border-radius: 4px;
    padding: 12px;
}
QFrame.DemoBanner {
    background-color: #fef2f2;
    border: 1px solid #fecaca;
    color: #991b1b;
    padding: 6px 12px;
    font-weight: 600;
}
"""

DARK_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #0b1120;
    color: #f8fafc;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 13px;
}

/* Sidebar navigation */
QFrame#SidebarContainer {
    background-color: #070d19;
    border-right: 1px solid #1e293b;
}
QListWidget#SidebarList {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    outline: none;
    font-size: 13px;
    font-weight: 500;
}
QListWidget#SidebarList::item {
    padding: 10px 16px;
    border-radius: 8px;
    margin: 3px 12px;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:hover {
    background-color: #1e293b;
    color: #f8fafc;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:selected {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3b82f6);
    color: #ffffff;
    font-weight: 600;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:selected:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3b82f6);
    color: #ffffff;
    border: none;
    outline: none;
}
QListWidget#SidebarList::item:focus,
QListWidget#SidebarList::item:selected:focus {
    border: none;
    outline: none;
}

/* Cards & containers */
QFrame.CardFrame {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
}
QFrame.CardFrameSelected {
    background-color: #172554;
    border: 2px solid #2563eb;
    border-radius: 8px;
    padding: 16px;
}

/* Action Cards */
QFrame.ActionCardBlue {
    background-color: #0f1f3d;
    border: 1px solid #1e3a8a;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardPurple {
    background-color: #1e1338;
    border: 1px solid #581c87;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardGreen {
    background-color: #09261a;
    border: 1px solid #065f46;
    border-radius: 8px;
    padding: 14px;
}
QFrame.ActionCardOrange {
    background-color: #2e1706;
    border: 1px solid #78350f;
    border-radius: 8px;
    padding: 14px;
}

/* Badges / Status Pills */
QLabel.BadgeReady, QLabel.BadgeSuccess {
    background-color: #064e3b;
    color: #34d399;
    border: 1px solid #059669;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeWarning, QLabel.BadgeNeedsCheck {
    background-color: #78350f;
    color: #fbbf24;
    border: 1px solid #d97706;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeDanger, QLabel.BadgeCorrupted {
    background-color: #7f1d1d;
    color: #f87171;
    border: 1px solid #dc2626;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeBlue, QLabel.BadgeInfo {
    background-color: #1e3a8a;
    color: #60a5fa;
    border: 1px solid #2563eb;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}
QLabel.BadgeSlate {
    background-color: #334155;
    color: #cbd5e1;
    border: 1px solid #475569;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}

/* Headings */
QLabel.PageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #f8fafc;
}
QLabel.PageSubtitle {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 2px;
}
QLabel.SectionHeader {
    font-size: 14px;
    font-weight: 600;
    color: #e2e8f0;
    margin-top: 4px;
    margin-bottom: 2px;
}
QLabel.MutedText {
    color: #94a3b8;
    font-size: 12px;
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
    color: #f8fafc;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #64748b;
}
QPushButton:pressed {
    background-color: #475569;
}
QPushButton.PrimaryButton {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
    color: #ffffff;
    font-weight: 600;
}
QPushButton.PrimaryButton:hover {
    background-color: #1d4ed8;
}
QPushButton.PrimaryButton:pressed {
    background-color: #1e40af;
}
QPushButton.DangerButton {
    background-color: #dc2626;
    border: 1px solid #ef4444;
    color: #ffffff;
}
QPushButton.DangerButton:hover {
    background-color: #b91c1c;
}

/* Tables & Trees */
QTableWidget, QTreeWidget {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #1e293b;
    selection-background-color: #1e3a8a;
    selection-color: #93c5fd;
}
QHeaderView::section {
    background-color: #1e293b;
    color: #94a3b8;
    font-weight: 600;
    padding: 6px 10px;
    border: 1px solid #334155;
}

/* Tab widget */
QTabWidget::pane {
    border: none;
    background: transparent;
    margin-top: 8px;
}
QTabBar::tab {
    background-color: #111c35;
    color: #94a3b8;
    padding: 8px 18px;
    margin-right: 8px;
    border-radius: 8px;
    border: 1px solid #1e293b;
    font-weight: 500;
}
QTabBar::tab:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QTabBar::tab:selected {
    background-color: #1d4ed8;
    color: #ffffff;
    font-weight: 600;
    border: 1px solid #3b82f6;
}

/* Settings White Card */
QFrame.SettingsWhiteCard {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 20px;
}
QFrame.SettingsWhiteCard QLabel {
    color: #0f172a;
}

/* Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}

/* Progress bar */
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    height: 14px;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 6px;
}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #2563eb;
}

/* Live Terminal Log */
QTextEdit.TerminalLog {
    background-color: #050a14;
    border: 1px solid #1e293b;
    border-radius: 6px;
    color: #a7f3d0;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    padding: 8px;
}

/* Notice box */
QFrame.NoticeBox {
    background-color: #1e3a8a;
    border-left: 4px solid #60a5fa;
    border-radius: 4px;
    padding: 12px;
}
QFrame.WarningBox {
    background-color: #713f12;
    border-left: 4px solid #facc15;
    border-radius: 4px;
    padding: 12px;
}
QFrame.DemoBanner {
    background-color: #7f1d1d;
    border: 1px solid #f87171;
    color: #fecaca;
    padding: 6px 12px;
    font-weight: 600;
}
"""


def apply_theme(app: QApplication, theme_name: str = "dark") -> None:
    """Apply the selected stylesheet to the Qt application."""
    if theme_name.lower() == "light":
        app.setStyleSheet(LIGHT_THEME_QSS)
    else:
        app.setStyleSheet(DARK_THEME_QSS)
