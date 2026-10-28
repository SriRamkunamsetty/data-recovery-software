"""Modern light and dark theme stylesheets for RecoverX PySide6 desktop UI."""

from PySide6.QtWidgets import QApplication

LIGHT_THEME_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #f8fafc;
    color: #0f172a;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13px;
}

/* Sidebar navigation */
QListWidget#SidebarList {
    background-color: #0f172a;
    color: #94a3b8;
    border: none;
    font-size: 14px;
    font-weight: 500;
    padding-top: 12px;
}
QListWidget#SidebarList::item {
    padding: 12px 18px;
    border-radius: 6px;
    margin: 3px 8px;
}
QListWidget#SidebarList::item:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QListWidget#SidebarList::item:selected {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
}

/* Cards & containers */
QFrame.CardFrame {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px;
}

/* Headings */
QLabel.PageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 8px;
}
QLabel.SectionHeader {
    font-size: 15px;
    font-weight: 600;
    color: #1e293b;
    margin-top: 8px;
    margin-bottom: 4px;
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
    padding: 8px 16px;
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
    background-color: #f1f5f9;
    color: #475569;
    font-weight: 600;
    padding: 6px 8px;
    border: 1px solid #e2e8f0;
}

/* Progress bar */
QProgressBar {
    background-color: #e2e8f0;
    border-radius: 6px;
    text-align: center;
    color: #0f172a;
    font-weight: 600;
    height: 18px;
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
    background-color: #0f172a;
    color: #f8fafc;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13px;
}

/* Sidebar navigation */
QListWidget#SidebarList {
    background-color: #020617;
    color: #94a3b8;
    border: none;
    font-size: 14px;
    font-weight: 500;
    padding-top: 12px;
}
QListWidget#SidebarList::item {
    padding: 12px 18px;
    border-radius: 6px;
    margin: 3px 8px;
}
QListWidget#SidebarList::item:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QListWidget#SidebarList::item:selected {
    background-color: #3b82f6;
    color: #ffffff;
    font-weight: 600;
}

/* Cards & containers */
QFrame.CardFrame {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
}

/* Headings */
QLabel.PageTitle {
    font-size: 20px;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 8px;
}
QLabel.SectionHeader {
    font-size: 15px;
    font-weight: 600;
    color: #e2e8f0;
    margin-top: 8px;
    margin-bottom: 4px;
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
    padding: 8px 16px;
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
    background-color: #3b82f6;
    border: 1px solid #2563eb;
    color: #ffffff;
    font-weight: 600;
}
QPushButton.PrimaryButton:hover {
    background-color: #2563eb;
}
QPushButton.PrimaryButton:pressed {
    background-color: #1d4ed8;
}
QPushButton.DangerButton {
    background-color: #ef4444;
    border: 1px solid #dc2626;
    color: #ffffff;
}
QPushButton.DangerButton:hover {
    background-color: #dc2626;
}

/* Tables & Trees */
QTableWidget, QTreeWidget {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #334155;
    selection-background-color: #1e3a8a;
    selection-color: #93c5fd;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #94a3b8;
    font-weight: 600;
    padding: 6px 8px;
    border: 1px solid #334155;
}

/* Progress bar */
QProgressBar {
    background-color: #334155;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-weight: 600;
    height: 18px;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 6px;
}

/* Inputs */
QLineEdit, QComboBox, QSpinBox {
    background-color: #0f172a;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f8fafc;
}
QLineEdit:focus, QComboBox:focus {
    border: 2px solid #3b82f6;
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


def apply_theme(app: QApplication, theme_name: str = "light") -> None:
    """Apply the selected stylesheet to the Qt application."""
    if theme_name.lower() == "dark":
        app.setStyleSheet(DARK_THEME_QSS)
    else:
        app.setStyleSheet(LIGHT_THEME_QSS)
