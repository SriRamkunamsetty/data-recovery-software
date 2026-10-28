"""Device and disk image selection page with forensic triage and capability labels."""

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recoverx.domain.session import DeviceTriageResult
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.image import DiskImageReader
from recoverx.services.device_triage_service import DeviceTriageService

logger = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    size_float = float(size_bytes)
    for unit in ["KiB", "MiB", "GiB", "TiB"]:
        size_float /= 1024.0
        if size_float < 1024.0:
            return f"{size_float:.2f} {unit}"
    return f"{size_float:.2f} PiB"


class DeviceSelectionPage(QWidget):
    """Device selection page enabling file-image loading, device inspection, and triage."""

    device_selected = Signal(str, object)  # path, ReadOnlyBlockDevice

    def __init__(self, triage_service: DeviceTriageService, parent: Any = None) -> None:
        super().__init__(parent)
        self.triage_service = triage_service
        self.current_reader: ReadOnlyBlockDevice | None = None
        self.current_path: str = ""

        self.setAccessibleName("Device Selection Page")
        self.setAccessibleDescription(
            "Page for selecting and triaging removable storage media or raw disk images"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Select Storage Media")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Device Selection Page Title")
        layout.addWidget(title)

        # File picker bar
        picker_frame = QFrame()
        picker_frame.setProperty("class", "CardFrame")
        picker_layout = QHBoxLayout(picker_frame)

        picker_label = QLabel("<strong>Source Storage Image / Raw Media:</strong>")
        picker_layout.addWidget(picker_label)

        self.path_display = QLabel("No disk image loaded.")
        self.path_display.setAccessibleName("Selected image path display")
        self.path_display.setStyleSheet("color: #64748b; font-style: italic;")
        picker_layout.addWidget(self.path_display, stretch=1)

        self.load_btn = QPushButton("Open Disk Image...")
        self.load_btn.setProperty("class", "PrimaryButton")
        self.load_btn.setAccessibleName("Open Disk Image Button")
        self.load_btn.clicked.connect(self._open_file_dialog)
        picker_layout.addWidget(self.load_btn)

        layout.addWidget(picker_frame)

        # Device Identity Card
        self.info_card = QFrame()
        self.info_card.setProperty("class", "CardFrame")
        info_layout = QGridLayout(self.info_card)

        self.vendor_lbl = QLabel("-")
        self.vendor_lbl.setAccessibleName("Device Model Info")
        self.capacity_lbl = QLabel("-")
        self.capacity_lbl.setAccessibleName("Device Capacity Info")
        self.sector_lbl = QLabel("-")
        self.sector_lbl.setAccessibleName("Device Sector Size Info")
        self.hash_lbl = QLabel("-")
        self.hash_lbl.setAccessibleName("Device Sector 0 Hash Info")

        info_layout.addWidget(QLabel("<strong>Model / Identity:</strong>"), 0, 0)
        info_layout.addWidget(self.vendor_lbl, 0, 1)
        info_layout.addWidget(QLabel("<strong>Capacity:</strong>"), 1, 0)
        info_layout.addWidget(self.capacity_lbl, 1, 1)
        info_layout.addWidget(QLabel("<strong>Sector Size:</strong>"), 2, 0)
        info_layout.addWidget(self.sector_lbl, 2, 1)
        info_layout.addWidget(QLabel("<strong>Sector 0 Fingerprint:</strong>"), 3, 0)
        info_layout.addWidget(self.hash_lbl, 3, 1)

        layout.addWidget(self.info_card)

        # Triage Status Box
        self.triage_box = QFrame()
        self.triage_box.setProperty("class", "NoticeBox")
        triage_layout = QVBoxLayout(self.triage_box)
        self.triage_status_lbl = QLabel("<strong>Triage: Awaiting Device Selection</strong>")
        self.triage_status_lbl.setAccessibleName("Device Triage Status")
        self.triage_desc_lbl = QLabel(
            "Load a disk image file to inspect health and partition state."
        )
        self.triage_desc_lbl.setWordWrap(True)
        triage_layout.addWidget(self.triage_status_lbl)
        triage_layout.addWidget(self.triage_desc_lbl)
        layout.addWidget(self.triage_box)

        # Capability Table Section (Section 13 of MASTER_PROMPT.md)
        cap_title = QLabel("Engine Capabilities & Verified Scope")
        cap_title.setProperty("class", "SectionHeader")
        layout.addWidget(cap_title)

        cap_frame = QFrame()
        cap_frame.setProperty("class", "CardFrame")
        cap_layout = QGridLayout(cap_frame)

        cap_layout.addWidget(QLabel("<strong>FAT12 / FAT16 / FAT32:</strong>"), 0, 0)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Supported</span>"), 0, 1
        )
        cap_layout.addWidget(QLabel("<strong>exFAT:</strong>"), 1, 0)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Supported</span>"), 1, 1
        )
        cap_layout.addWidget(QLabel("<strong>NTFS:</strong>"), 2, 0)
        cap_layout.addWidget(
            QLabel("<span style='color: #ca8a04; font-weight: 600;'>Pending (M12)</span>"), 2, 1
        )

        cap_layout.addWidget(QLabel("<strong>JPEG / PNG / PDF / ZIP:</strong>"), 0, 2)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Supported</span>"), 0, 3
        )
        cap_layout.addWidget(QLabel("<strong>MP4 / MOV / RAW:</strong>"), 1, 2)
        cap_layout.addWidget(
            QLabel("<span style='color: #ca8a04; font-weight: 600;'>Pending (M11)</span>"), 1, 3
        )
        cap_layout.addWidget(QLabel("<strong>Raw Disk Imaging:</strong>"), 2, 2)
        cap_layout.addWidget(
            QLabel("<span style='color: #16a34a; font-weight: 600;'>Supported</span>"), 2, 3
        )

        layout.addWidget(cap_frame)

        # Navigation Action
        self.confirm_btn = QPushButton("Confirm Device & Configure Scan")
        self.confirm_btn.setProperty("class", "PrimaryButton")
        self.confirm_btn.setAccessibleName("Confirm Device Selection Button")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._on_confirm)
        layout.addWidget(self.confirm_btn)

    def _open_file_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Raw Disk Image File",
            "",
            "Disk Images (*.img *.raw *.bin *.dd *.vhd);;All Files (*.*)",
        )
        if file_path:
            self.load_image(file_path)

    def load_image(self, file_path: str) -> None:
        """Load and triage a disk image file."""
        path = Path(file_path)
        if not path.exists():
            return

        if self.current_reader is not None:
            self.current_reader.close()

        try:
            reader = DiskImageReader(path)
            self.current_reader = reader
            self.current_path = str(path)

            self.path_display.setText(str(path))
            self.path_display.setStyleSheet("color: #0f172a; font-weight: 600;")

            # Display identity
            id_rec = reader.identity
            self.vendor_lbl.setText(f"{id_rec.vendor} {id_rec.product}".strip() or "Raw Image")
            self.capacity_lbl.setText(
                f"{_format_size(id_rec.capacity_bytes)} ({id_rec.capacity_bytes:,} bytes)"
            )
            self.sector_lbl.setText(
                f"{id_rec.logical_sector_size} B Logical / {id_rec.physical_sector_size} B Physical"
            )
            self.hash_lbl.setText(
                f"<code>{id_rec.sector0_hash[:24]}...</code>" if id_rec.sector0_hash else "None"
            )

            # Run triage
            triage: DeviceTriageResult = self.triage_service.triage_device(reader)
            self.triage_status_lbl.setText(f"<strong>Triage: {triage.status.value}</strong>")
            self.triage_desc_lbl.setText(
                f"{triage.explanation} &bull; <em>{triage.recommended_action}</em>"
            )

            if triage.recommend_imaging:
                self.triage_box.setProperty("class", "WarningBox")
            else:
                self.triage_box.setProperty("class", "NoticeBox")
            self.triage_box.update()

            self.confirm_btn.setEnabled(triage.can_scan)

        except Exception as exc:
            logger.exception("Failed to open disk image: %s", exc)
            self.triage_status_lbl.setText("<strong>Error Opening Image</strong>")
            self.triage_desc_lbl.setText(str(exc))
            self.confirm_btn.setEnabled(False)

    def _on_confirm(self) -> None:
        if self.current_reader is not None and self.current_path:
            self.device_selected.emit(self.current_path, self.current_reader)
