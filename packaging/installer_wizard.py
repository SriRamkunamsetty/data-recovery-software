"""RecoverX Windows Production Setup Wizard.

A modern, standalone Windows installer providing standard application setup:
- Destination directory selection (defaults to %LOCALAPPDATA%\\Programs\\RecoverX)
- Extraction progress indicator
- Desktop & Start Menu shortcut creation
- Windows Add/Remove Programs registry registration
- Automatic launch on finish
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


def get_default_install_dir() -> Path:
    """Return standard user-level application directory (no UAC prompt required)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / "RecoverX"
    return Path.home() / "AppData" / "Local" / "Programs" / "RecoverX"


def get_payload_path() -> Path:
    """Locate the bundled payload zip archive."""
    # PyInstaller temp folder
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(getattr(sys, "_MEIPASS"))
        bundled = meipass / "payload.zip"
        if bundled.exists():
            return bundled

    # Development / build tree
    local_payload = Path(__file__).resolve().parent / "payload.zip"
    if local_payload.exists():
        return local_payload

    dist_zip = Path(__file__).resolve().parent.parent / "dist" / "RecoverX-v0.1.0-Windows-x64.zip"
    if dist_zip.exists():
        return dist_zip

    return Path("payload.zip")


class ExtractionWorker(QThread):
    """Background worker extracting application payload and registering Windows shortcuts."""

    progress = Signal(int, str)  # percent, message
    finished_success = Signal(str)  # install directory
    finished_error = Signal(str)

    def __init__(
        self,
        target_dir: Path,
        create_desktop: bool,
        create_start_menu: bool,
        payload_path: Path,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.target_dir = target_dir
        self.create_desktop = create_desktop
        self.create_start_menu = create_start_menu
        self.payload_path = payload_path

    def run(self) -> None:
        try:
            if not self.payload_path.exists():
                self.finished_error.emit(f"Setup payload archive not found at: {self.payload_path}")
                return

            self.progress.emit(5, "Preparing target directory...")
            self.target_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit(10, "Reading application archive...")
            with zipfile.ZipFile(self.payload_path, "r") as zf:
                file_list = zf.infolist()
                total_files = len(file_list)
                if total_files == 0:
                    self.finished_error.emit("Payload archive is empty.")
                    return

                for idx, item in enumerate(file_list):
                    zf.extract(item, self.target_dir)
                    percent = 10 + int((idx / total_files) * 75)
                    fname = Path(item.filename).name
                    if fname:
                        self.progress.emit(percent, f"Extracting {fname}...")

            # Check if extracted inside a subfolder or directly
            exe_path = self.target_dir / "recoverx.exe"
            if not exe_path.exists():
                nested_exe = list(self.target_dir.glob("**/recoverx.exe"))
                if nested_exe:
                    exe_path = nested_exe[0]

            self.progress.emit(88, "Creating Windows shortcuts and registry entries...")
            self._create_shortcuts_and_registry(exe_path)

            self.progress.emit(100, "Installation complete.")
            self.finished_success.emit(str(exe_path))

        except Exception as e:
            self.finished_error.emit(str(e))

    def _create_shortcuts_and_registry(self, exe_path: Path) -> None:
        target_folder = exe_path.parent
        icon_path = target_folder / "assets" / "icon.ico"
        if not icon_path.exists():
            nested_icon = list(target_folder.glob("**/icon.ico"))
            if nested_icon:
                icon_path = nested_icon[0]

        ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell

# 1. Desktop Shortcut
if ({' $true ' if self.create_desktop else ' $false '}) {{
    $desktopPaths = @(
        "$env:USERPROFILE\\OneDrive\\Desktop",
        "$env:USERPROFILE\\Desktop"
    )
    foreach ($dp in $desktopPaths) {{
        if (Test-Path $dp) {{
            $scPath = Join-Path $dp 'RecoverX.lnk'
            $sc = $WshShell.CreateShortcut($scPath)
            $sc.TargetPath = '{str(exe_path)}'
            $sc.Arguments = 'gui'
            $sc.WorkingDirectory = '{str(target_folder)}'
            $sc.IconLocation = '{str(icon_path)},0'
            $sc.Description = 'RecoverX - Forensic Removable Storage Data Recovery'
            $sc.Save()
        }}
    }}
}}

# 2. Start Menu Shortcut
if ({' $true ' if self.create_start_menu else ' $false '}) {{
    $smPath = Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\RecoverX'
    if (!(Test-Path $smPath)) {{ New-Item -ItemType Directory -Path $smPath -Force | Out-Null }}
    $sc = $WshShell.CreateShortcut((Join-Path $smPath 'RecoverX.lnk'))
    $sc.TargetPath = '{str(exe_path)}'
    $sc.Arguments = 'gui'
    $sc.WorkingDirectory = '{str(target_folder)}'
    $sc.IconLocation = '{str(icon_path)},0'
    $sc.Description = 'RecoverX - Forensic Removable Storage Data Recovery'
    $sc.Save()
}}

# 3. Register in Windows Add/Remove Programs (Registry)
$regKey = 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\RecoverX'
if (!(Test-Path $regKey)) {{ New-Item -Path $regKey -Force | Out-Null }}
Set-ItemProperty -Path $regKey -Name 'DisplayName' -Value 'RecoverX Forensic Data Recovery'
Set-ItemProperty -Path $regKey -Name 'DisplayVersion' -Value '0.1.0'
Set-ItemProperty -Path $regKey -Name 'Publisher' -Value 'RecoverX Open Source'
Set-ItemProperty -Path $regKey -Name 'InstallLocation' -Value '{str(target_folder)}'
Set-ItemProperty -Path $regKey -Name 'DisplayIcon' -Value '{str(icon_path)}'
Set-ItemProperty -Path $regKey -Name 'HelpLink' -Value 'https://github.com/SriRamkunamsetty/data-recovery-software'
Set-ItemProperty -Path $regKey -Name 'NoModify' -Value 1 -Type DWord
Set-ItemProperty -Path $regKey -Name 'NoRepair' -Value 1 -Type DWord
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )


class InstallerWindow(QMainWindow):
    """Fluent dark-neon installer window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RecoverX Setup - Forensic Data Recovery")
        self.resize(620, 440)
        self.setFixedSize(620, 440)

        icon_path = Path(__file__).resolve().parent / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.payload_path = get_payload_path()
        self.installed_exe_path: str = ""
        self.worker: ExtractionWorker | None = None

        self._setup_style()
        self._setup_ui()

    def _setup_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b1120;
                color: #f8fafc;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 13px;
            }
            QFrame.Card {
                background-color: #111c35;
                border: 1px solid #1e293b;
                border-radius: 12px;
                padding: 16px;
            }
            QPushButton.PrimaryBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #3b82f6);
                color: #ffffff;
                font-weight: 600;
                font-size: 13px;
                border: none;
                border-radius: 8px;
                padding: 9px 24px;
            }
            QPushButton.PrimaryBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #60a5fa);
            }
            QPushButton.SecondaryBtn {
                background-color: #1e293b;
                color: #cbd5e1;
                font-weight: 500;
                font-size: 13px;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 9px 18px;
            }
            QPushButton.SecondaryBtn:hover {
                background-color: #334155;
                color: #ffffff;
            }
            QLineEdit {
                background-color: #070d19;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 8px 12px;
                color: #f8fafc;
                font-size: 12px;
            }
            QProgressBar {
                background-color: #070d19;
                border: 1px solid #1e293b;
                border-radius: 6px;
                height: 12px;
                text-align: center;
                color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8);
                border-radius: 5px;
            }
            QCheckBox {
                color: #cbd5e1;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #334155;
                background-color: #070d19;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border: 1px solid #3b82f6;
            }
        """)

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        # Header with Logo
        header = QHBoxLayout()
        header.setSpacing(14)
        shield_icon = QLabel("🛡")
        shield_icon.setStyleSheet(
            "font-size: 24px; background: #1e293b; border: 1px solid #334155; "
            "border-radius: 10px; padding: 6px 10px;"
        )
        header.addWidget(shield_icon)

        htext = QVBoxLayout()
        htext.setSpacing(2)
        app_name = QLabel("<strong>RecoverX Setup</strong>")
        app_name.setStyleSheet("font-size: 18px; color: #ffffff;")
        htext.addWidget(app_name)
        app_sub = QLabel("Forensic Removable Storage Data Recovery • v0.1.0")
        app_sub.setStyleSheet("font-size: 11px; color: #94a3b8;")
        htext.addWidget(app_sub)
        header.addLayout(htext)
        header.addStretch(1)
        root.addLayout(header)

        # Main Pages Stack
        self.stack = QStackedWidget()

        # Page 0: Welcome & Options
        page0 = QWidget()
        p0_layout = QVBoxLayout(page0)
        p0_layout.setContentsMargins(0, 8, 0, 0)
        p0_layout.setSpacing(14)

        info_card = QFrame()
        info_card.setProperty("class", "Card")
        ic_layout = QVBoxLayout(info_card)
        ic_layout.setSpacing(6)
        ic_title = QLabel("<strong>Ready to install RecoverX</strong>")
        ic_title.setStyleSheet("font-size: 14px; color: #ffffff;")
        ic_layout.addWidget(ic_title)
        ic_desc = QLabel(
            "This setup wizard will install RecoverX on your computer. "
            "RecoverX features non-destructive raw direct block I/O, sector-level signature "
            "carving, and multi-filesystem directory reconstruction (FAT12/16/32, exFAT, NTFS)."
        )
        ic_desc.setWordWrap(True)
        ic_desc.setStyleSheet("color: #94a3b8; font-size: 12px; line-height: 1.4;")
        ic_layout.addWidget(ic_desc)
        p0_layout.addWidget(info_card)

        # Destination selector
        dest_card = QFrame()
        dest_card.setProperty("class", "Card")
        dc_layout = QVBoxLayout(dest_card)
        dc_layout.setSpacing(8)
        dest_title = QLabel("Destination Folder")
        dest_title.setStyleSheet("font-size: 12px; font-weight: 600; color: #cbd5e1;")
        dc_layout.addWidget(dest_title)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        self.dest_edit = QLineEdit(str(get_default_install_dir()))
        dest_row.addWidget(self.dest_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.setProperty("class", "SecondaryBtn")
        browse_btn.clicked.connect(self._on_browse)
        dest_row.addWidget(browse_btn)
        dc_layout.addLayout(dest_row)
        p0_layout.addWidget(dest_card)

        # Options check
        options_layout = QHBoxLayout()
        self.cb_desktop = QCheckBox("Create Desktop Shortcut")
        self.cb_desktop.setChecked(True)
        options_layout.addWidget(self.cb_desktop)

        self.cb_start_menu = QCheckBox("Create Start Menu Shortcut")
        self.cb_start_menu.setChecked(True)
        options_layout.addWidget(self.cb_start_menu)
        options_layout.addStretch(1)
        p0_layout.addLayout(options_layout)

        p0_layout.addStretch(1)
        self.stack.addWidget(page0)

        # Page 1: Progress
        page1 = QWidget()
        p1_layout = QVBoxLayout(page1)
        p1_layout.setContentsMargins(0, 16, 0, 0)
        p1_layout.setSpacing(14)

        prog_card = QFrame()
        prog_card.setProperty("class", "Card")
        pr_layout = QVBoxLayout(prog_card)
        pr_layout.setSpacing(12)

        pr_title = QLabel("<strong>Installing RecoverX...</strong>")
        pr_title.setStyleSheet("font-size: 15px; color: #ffffff;")
        pr_layout.addWidget(pr_title)

        self.status_lbl = QLabel("Extracting application packages...")
        self.status_lbl.setStyleSheet("color: #60a5fa; font-size: 12px;")
        pr_layout.addWidget(self.status_lbl)

        self.pbar = QProgressBar()
        self.pbar.setValue(0)
        pr_layout.addWidget(self.pbar)
        prog_card.setFixedHeight(140)
        p1_layout.addWidget(prog_card)
        p1_layout.addStretch(1)
        self.stack.addWidget(page1)

        # Page 2: Finish
        page2 = QWidget()
        p2_layout = QVBoxLayout(page2)
        p2_layout.setContentsMargins(0, 16, 0, 0)
        p2_layout.setSpacing(14)

        fin_card = QFrame()
        fin_card.setProperty("class", "Card")
        fc_layout = QVBoxLayout(fin_card)
        fc_layout.setSpacing(10)

        fc_title = QLabel("<strong>Installation Completed!</strong>")
        fc_title.setStyleSheet("font-size: 16px; color: #10b981;")
        fc_layout.addWidget(fc_title)

        fc_desc = QLabel(
            "RecoverX has been successfully installed on your computer.\n"
            "Desktop and Start Menu shortcuts have been configured.\n"
            "You can now launch the application and begin forensic storage recovery."
        )
        fc_desc.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.6;")
        fc_layout.addWidget(fc_desc)

        self.cb_launch = QCheckBox("Launch RecoverX now")
        self.cb_launch.setChecked(True)
        self.cb_launch.setStyleSheet("color: #60a5fa; font-weight: 600; font-size: 14px;")
        fc_layout.addWidget(self.cb_launch)
        p2_layout.addWidget(fin_card)
        p2_layout.addStretch(1)
        self.stack.addWidget(page2)

        root.addWidget(self.stack, stretch=1)

        # Bottom Actions Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)
        bottom_bar.addStretch(1)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("class", "SecondaryBtn")
        self.cancel_btn.clicked.connect(self.close)
        bottom_bar.addWidget(self.cancel_btn)

        self.action_btn = QPushButton("Install")
        self.action_btn.setProperty("class", "PrimaryBtn")
        self.action_btn.clicked.connect(self._on_action_clicked)
        bottom_bar.addWidget(self.action_btn)
        root.addLayout(bottom_bar)

    def _on_browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Directory",
            self.dest_edit.text(),
        )
        if chosen:
            self.dest_edit.setText(chosen)

    def _on_action_clicked(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 0:
            target_path = Path(self.dest_edit.text().strip())
            self.stack.setCurrentIndex(1)
            self.cancel_btn.setEnabled(False)
            self.action_btn.setEnabled(False)

            self.worker = ExtractionWorker(
                target_dir=target_path,
                create_desktop=self.cb_desktop.isChecked(),
                create_start_menu=self.cb_start_menu.isChecked(),
                payload_path=self.payload_path,
            )
            self.worker.progress.connect(self._on_progress)
            self.worker.finished_success.connect(self._on_install_success)
            self.worker.finished_error.connect(self._on_install_error)
            self.worker.start()

        elif idx == 2:
            # Finish clicked
            if self.cb_launch.isChecked() and self.installed_exe_path:
                subprocess.Popen(
                    [self.installed_exe_path, "gui"],
                    cwd=str(Path(self.installed_exe_path).parent),
                )
            self.close()

    def _on_progress(self, percent: int, msg: str) -> None:
        self.pbar.setValue(percent)
        self.status_lbl.setText(msg)

    def _on_install_success(self, exe_path: str) -> None:
        self.installed_exe_path = exe_path
        self.stack.setCurrentIndex(2)
        self.cancel_btn.setVisible(False)
        self.action_btn.setEnabled(True)
        self.action_btn.setText("Finish")

    def _on_install_error(self, err_msg: str) -> None:
        self.status_lbl.setText(f"Installation error: {err_msg}")
        self.status_lbl.setStyleSheet("color: #ef4444; font-size: 12px;")
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Close")


def main() -> int:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 9))
    win = InstallerWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
