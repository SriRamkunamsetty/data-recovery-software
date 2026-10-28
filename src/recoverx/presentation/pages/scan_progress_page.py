"""Real-time scan progress page with honest metrics, phase tracking, and cancellation."""

import logging
import time
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from recoverx.domain.scan import ScanProgress

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


def _format_time(seconds: float) -> str:
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m {rem_secs:02d}s"
    return f"{minutes:02d}m {rem_secs:02d}s"


class ScanProgressPage(QWidget):
    """Scan progress page displaying honest real-time metrics during background execution.

    Section 6 of MASTER_PROMPT.md:
    Accurate, factual progress reporting. No fake animations, no synthetic delays.
    Never report percentage recovery chances.
    """

    cancel_requested = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._start_time: float = time.monotonic()
        self._last_bytes: int = 0
        self._last_time: float = time.monotonic()

        self.setAccessibleName("Scan Progress Page")
        self.setAccessibleDescription(
            "Monitors real-time recovery scan progress, bytes read, "
            "candidate count, and elapsed time"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title = QLabel("Scan in Progress")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Scan Progress Page Title")
        layout.addWidget(title)

        # Phase banner card
        phase_card = QFrame()
        phase_card.setProperty("class", "CardFrame")
        phase_layout = QVBoxLayout(phase_card)

        self.phase_label = QLabel("Initializing scan...")
        self.phase_label.setStyleSheet("font-size: 16px; font-weight: 600; color: #2563eb;")
        self.phase_label.setAccessibleName("Scan Phase Label")
        phase_layout.addWidget(self.phase_label)

        self.phase_desc = QLabel("Preparing block device and analyzing partition records.")
        self.phase_desc.setStyleSheet("color: #64748b;")
        self.phase_desc.setWordWrap(True)
        self.phase_desc.setAccessibleName("Scan Phase Description")
        phase_layout.addWidget(self.phase_desc)

        layout.addWidget(phase_card)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setAccessibleName("Scan Progress Bar")
        self.progress_bar.setAccessibleDescription("Progress percentage of the active scan")
        layout.addWidget(self.progress_bar)

        # Metrics Grid Card
        metrics_card = QFrame()
        metrics_card.setProperty("class", "CardFrame")
        metrics_layout = QGridLayout(metrics_card)
        metrics_layout.setSpacing(12)

        self.bytes_lbl = QLabel("0 B / 0 B (0.0%)")
        self.bytes_lbl.setAccessibleName("Processed Bytes Counter")
        self.candidates_lbl = QLabel("0 candidates")
        self.candidates_lbl.setAccessibleName("Candidates Discovered Counter")
        self.elapsed_lbl = QLabel("00m 00s")
        self.elapsed_lbl.setAccessibleName("Elapsed Time Counter")
        self.throughput_lbl = QLabel("0.0 MB/s")
        self.throughput_lbl.setAccessibleName("Read Throughput Counter")
        self.offset_lbl = QLabel("0x0 (Sector 0)")
        self.offset_lbl.setAccessibleName("Current Sector Offset Counter")

        metrics_layout.addWidget(QLabel("<strong>Data Processed:</strong>"), 0, 0)
        metrics_layout.addWidget(self.bytes_lbl, 0, 1)

        metrics_layout.addWidget(QLabel("<strong>Candidates Found:</strong>"), 0, 2)
        metrics_layout.addWidget(self.candidates_lbl, 0, 3)

        metrics_layout.addWidget(QLabel("<strong>Elapsed Time:</strong>"), 1, 0)
        metrics_layout.addWidget(self.elapsed_lbl, 1, 1)

        metrics_layout.addWidget(QLabel("<strong>Read Speed:</strong>"), 1, 2)
        metrics_layout.addWidget(self.throughput_lbl, 1, 3)

        metrics_layout.addWidget(QLabel("<strong>Current Offset:</strong>"), 2, 0)
        metrics_layout.addWidget(self.offset_lbl, 2, 1)

        layout.addWidget(metrics_card)

        # Safety Assurance Frame
        safety_frame = QFrame()
        safety_frame.setProperty("class", "NoticeBox")
        safety_layout = QVBoxLayout(safety_frame)
        safety_text = QLabel(
            "&bull; <strong>Forensic Safety Active:</strong> Source media is opened "
            "strictly in read-only mode.<br>"
            "&bull; No write requests, temporary files, or directory indexes are written "
            "to the source drive."
        )
        safety_layout.addWidget(safety_text)
        layout.addWidget(safety_frame)

        layout.addStretch(1)

        # Action bar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        self.cancel_btn = QPushButton("Cancel Scan")
        self.cancel_btn.setProperty("class", "DangerButton")
        self.cancel_btn.setAccessibleName("Cancel Scan Button")
        self.cancel_btn.setAccessibleDescription(
            "Stops the active scan gracefully without modifying source media"
        )
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def reset(self) -> None:
        """Reset progress state for a new scan."""
        self._start_time = time.monotonic()
        self._last_bytes = 0
        self._last_time = time.monotonic()
        self.progress_bar.setValue(0)
        self.phase_label.setText("Initializing scan...")
        self.phase_desc.setText("Preparing block device and analyzing partition records.")
        self.bytes_lbl.setText("0 B / 0 B (0.0%)")
        self.candidates_lbl.setText("0 candidates")
        self.elapsed_lbl.setText("00m 00s")
        self.throughput_lbl.setText("0.0 MB/s")
        self.offset_lbl.setText("0x0 (Sector 0)")
        self.cancel_btn.setEnabled(True)

    def update_progress(self, progress: ScanProgress) -> None:
        """Update live UI metrics from ScanProgress domain object."""
        pct = progress.progress_percent
        self.progress_bar.setValue(min(100, int(pct)))

        # Phase text
        phase_str = progress.phase.capitalize() if progress.phase else "Scanning"
        self.phase_label.setText(f"Phase: {phase_str}")

        # Bytes label
        processed_str = _format_size(progress.bytes_scanned)
        total_str = _format_size(progress.total_bytes)
        self.bytes_lbl.setText(f"{processed_str} / {total_str} ({pct:.1f}%)")

        # Candidates label
        self.candidates_lbl.setText(f"{progress.candidates_found} candidates")

        # Offset label
        sector_num = progress.current_sector
        offset = sector_num * 512
        self.offset_lbl.setText(f"0x{offset:X} (Sector {sector_num:,})")

        # Elapsed and throughput
        now = time.monotonic()
        elapsed = now - self._start_time
        self.elapsed_lbl.setText(_format_time(elapsed))

        # Speed calculation
        dt = now - self._last_time
        if dt >= 0.5:
            d_bytes = progress.bytes_scanned - self._last_bytes
            speed_mb = (d_bytes / (1024 * 1024)) / dt if dt > 0 else 0.0
            self.throughput_lbl.setText(f"{speed_mb:.1f} MB/s")
            self._last_bytes = progress.bytes_scanned
            self._last_time = now
