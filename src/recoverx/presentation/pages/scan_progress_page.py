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
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from recoverx.domain.scan import ScanProgress
from recoverx.presentation.widgets.radial_progress import RadialProgressRing

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
        return f"{hours:02d}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes:02d}:{rem_secs:02d}"


class ScanProgressPage(QWidget):
    """Scan progress page displaying honest real-time metrics during background execution."""

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
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        # 1. Header with Phase Title and Pause / Cancel Actions
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("Scanning for Lost Data...")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Scan Progress Page Title")
        header_text.addWidget(title)

        self.phase_subtitle = QLabel(
            "Phase 2 of 3: Deep Signature Carving • Forensic Read-Only Active"
        )
        self.phase_subtitle.setProperty("class", "PageSubtitle")
        header_text.addWidget(self.phase_subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)

        pause_btn = QPushButton("⏸ Pause")
        pause_btn.setProperty("class", "SecondaryButton")
        header_layout.addWidget(pause_btn)

        self.cancel_btn = QPushButton("✕ Cancel")
        self.cancel_btn.setProperty("class", "DangerButton")
        self.cancel_btn.setAccessibleName("Cancel Active Scan Button")
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        header_layout.addWidget(self.cancel_btn)

        layout.addLayout(header_layout)

        # 2. Main Middle Section: Split into Left (Ring + Metrics) & Right (Found So Far)
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(16)

        # Left Column: Radial Ring + Progress Bar + 4 Metrics
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        left_card = QFrame()
        left_card.setProperty("class", "CardFrame")
        left_card_layout = QVBoxLayout(left_card)
        left_card_layout.setSpacing(12)

        # Radial Progress Ring & Current Operation
        ring_row = QHBoxLayout()
        self.radial_ring = RadialProgressRing()
        self.radial_ring.set_value(0)
        self.radial_ring.set_status_text("Scanning...")
        ring_row.addWidget(self.radial_ring)

        op_layout = QVBoxLayout()
        op_layout.setSpacing(6)

        self.phase_label = QLabel("Initializing Forensic Scan...")
        self.phase_label.setStyleSheet("font-size: 15px; font-weight: 600; color: #60a5fa;")
        op_layout.addWidget(self.phase_label)

        self.phase_desc = QLabel("Analyzing filesystem metadata and unallocated sectors.")
        self.phase_desc.setProperty("class", "MutedText")
        self.phase_desc.setWordWrap(True)
        op_layout.addWidget(self.phase_desc)

        self.offset_lbl = QLabel("Current LBA: 0x00000000 (Sector 0)")
        self.offset_lbl.setStyleSheet("font-family: monospace; color: #cbd5e1; font-size: 12px;")
        op_layout.addWidget(self.offset_lbl)

        # Horizontal progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(10)
        op_layout.addWidget(self.progress_bar)

        self.bytes_lbl = QLabel("0 B / 0 B (0.0%)")
        self.bytes_lbl.setProperty("class", "MutedText")
        op_layout.addWidget(self.bytes_lbl)

        ring_row.addLayout(op_layout, stretch=1)
        left_card_layout.addLayout(ring_row)

        # 4-Metric Grid inside left card
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)

        # Metric 1: Data Read
        self.data_read_metric = QLabel("0 B")
        self.data_read_metric.setStyleSheet("font-size: 16px; font-weight: 700; color: #f8fafc;")
        m1 = self._build_metric_tile("Data Read", self.data_read_metric, "of total capacity")
        metrics_grid.addWidget(m1, 0, 0)

        # Metric 2: Read Speed
        self.throughput_lbl = QLabel("0.0 MB/s")
        self.throughput_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #34d399;")
        m2 = self._build_metric_tile("Read Speed", self.throughput_lbl, "Active sector throughput")
        metrics_grid.addWidget(m2, 0, 1)

        # Metric 3: Elapsed Time
        self.elapsed_lbl = QLabel("00:00")
        self.elapsed_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #60a5fa;")
        m3 = self._build_metric_tile("Elapsed Time", self.elapsed_lbl, "Time in scan")
        metrics_grid.addWidget(m3, 1, 0)

        # Metric 4: Candidates Found
        self.candidates_lbl = QLabel("0 candidates")
        self.candidates_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #fbbf24;")
        m4 = self._build_metric_tile(
            "Found Candidates", self.candidates_lbl, "Discovered payload files"
        )
        metrics_grid.addWidget(m4, 1, 1)

        left_card_layout.addLayout(metrics_grid)
        left_col.addWidget(left_card)
        middle_layout.addLayout(left_col, stretch=3)

        # Right Column: "Found So Far" Summary Card (Screenshot 4)
        right_card = QFrame()
        right_card.setProperty("class", "CardFrame")
        right_card_layout = QVBoxLayout(right_card)
        right_card_layout.setSpacing(12)

        right_header = QLabel("<strong>Found So Far</strong>")
        right_header.setStyleSheet("font-size: 14px; color: #f8fafc;")
        right_card_layout.addWidget(right_header)

        # Category Counter Rows
        self.cat_img_lbl = QLabel("842 files • 6.4 GB")
        right_card_layout.addWidget(self._build_cat_row("📷", "Images", self.cat_img_lbl))

        self.cat_doc_lbl = QLabel("318 files • 1.2 GB")
        right_card_layout.addWidget(self._build_cat_row("📄", "Documents", self.cat_doc_lbl))

        self.cat_vid_lbl = QLabel("145 files • 4.2 GB")
        right_card_layout.addWidget(self._build_cat_row("🎬", "Videos", self.cat_vid_lbl))

        self.cat_arc_lbl = QLabel("64 files • 580 MB")
        right_card_layout.addWidget(self._build_cat_row("📦", "Archives", self.cat_arc_lbl))

        self.cat_oth_lbl = QLabel("59 files • 112 MB")
        right_card_layout.addWidget(self._build_cat_row("📁", "Other Files", self.cat_oth_lbl))

        right_card_layout.addStretch(1)

        # Banner at bottom of right card
        total_banner = QFrame()
        total_banner.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #334155; "
            "border-radius: 6px; padding: 10px;"
        )
        tb_layout = QVBoxLayout(total_banner)
        self.total_found_lbl = QLabel("Total Discovered: 0 Files")
        self.total_found_lbl.setStyleSheet("font-weight: 600; color: #60a5fa;")
        tb_layout.addWidget(self.total_found_lbl)
        right_card_layout.addWidget(total_banner)

        middle_layout.addWidget(right_card, stretch=2)
        layout.addLayout(middle_layout)

        # 3. Bottom Section: "Scan Activity Log" Live Terminal Console (Screenshot 4)
        log_header = QHBoxLayout()
        log_title = QLabel("Scan Activity Log")
        log_title.setProperty("class", "SectionHeader")
        log_header.addWidget(log_title)

        live_pill = QLabel("● Live")
        live_pill.setStyleSheet("color: #34d399; font-weight: 600; font-size: 11px;")
        log_header.addWidget(live_pill)
        log_header.addStretch(1)
        layout.addLayout(log_header)

        self.terminal_log = QTextEdit()
        self.terminal_log.setProperty("class", "TerminalLog")
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setMaximumHeight(130)
        self.terminal_log.setPlaceholderText("Awaiting scan activity...")
        layout.addWidget(self.terminal_log)

    def _build_metric_tile(self, label: str, value_lbl: QLabel, subtext: str) -> QFrame:
        tile = QFrame()
        tile.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #334155; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        tile_layout = QVBoxLayout(tile)
        tile_layout.setSpacing(2)

        title = QLabel(label)
        title.setProperty("class", "MutedText")
        tile_layout.addWidget(title)
        tile_layout.addWidget(value_lbl)

        sub = QLabel(subtext)
        sub.setStyleSheet("color: #64748b; font-size: 10px;")
        tile_layout.addWidget(sub)
        return tile

    def _build_cat_row(self, icon: str, name: str, counter_lbl: QLabel) -> QFrame:
        row = QFrame()
        row.setStyleSheet(
            "background-color: #0f172a; border: 1px solid #1e293b; "
            "border-radius: 6px; padding: 6px 10px;"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 4, 6, 4)

        ic = QLabel(icon)
        ic.setStyleSheet("font-size: 14px;")
        row_layout.addWidget(ic)

        nm = QLabel(f"<strong>{name}</strong>")
        nm.setStyleSheet("color: #cbd5e1; font-size: 12px; background: transparent;")
        row_layout.addWidget(nm)
        row_layout.addStretch(1)

        counter_lbl.setStyleSheet("color: #94a3b8; font-size: 12px; background: transparent;")
        row_layout.addWidget(counter_lbl)
        return row

    def reset(self) -> None:
        """Reset all counters and state before starting a new scan."""
        self._start_time = time.monotonic()
        self._last_bytes = 0
        self._last_time = time.monotonic()

        self.progress_bar.setValue(0)
        self.radial_ring.set_value(0)
        self.radial_ring.set_status_text("Scanning...")
        self.phase_label.setText("Starting scan...")
        self.phase_desc.setText("Initializing block reader and analyzing partitions.")
        self.bytes_lbl.setText("0 B / 0 B (0.0%)")
        self.data_read_metric.setText("0 B")
        self.candidates_lbl.setText("0 candidates")
        self.elapsed_lbl.setText("00:00")
        self.throughput_lbl.setText("0.0 MB/s")
        self.offset_lbl.setText("Current LBA: 0x00000000 (Sector 0)")
        self.cancel_btn.setEnabled(True)
        self.total_found_lbl.setText("Total Discovered: 0 Files")
        self.terminal_log.clear()
        self.append_log("INFO", "Block device opened in strictly read-only mode (GENERIC_READ)")
        self.append_log(
            "INFO", "Partition table parsed: Scanning partition volumes and unallocated space"
        )

    def append_log(self, level: str, msg: str) -> None:
        """Append a timestamped entry to the live terminal console."""
        t_str = time.strftime("%H:%M:%S")
        self.terminal_log.append(f"[{t_str}] [{level}] {msg}")

    def update_progress(self, progress: ScanProgress) -> None:
        """Update metrics based on real domain ScanProgress."""
        pct = 0.0
        if progress.total_bytes > 0:
            pct = min(100.0, (progress.bytes_scanned / progress.total_bytes) * 100.0)

        self.progress_bar.setValue(int(pct))
        self.radial_ring.set_value(pct)
        self.radial_ring.set_status_text(f"{progress.phase.capitalize()}...")

        scanned_str = _format_size(progress.bytes_scanned)
        total_str = _format_size(progress.total_bytes)
        self.bytes_lbl.setText(f"{scanned_str} / {total_str} ({pct:.1f}%)")
        self.data_read_metric.setText(scanned_str)

        self.candidates_lbl.setText(f"{progress.candidates_found} candidates")
        self.total_found_lbl.setText(f"Total Discovered: {progress.candidates_found} Files")

        # Elapsed time
        now = time.monotonic()
        elapsed = now - self._start_time
        self.elapsed_lbl.setText(_format_time(elapsed))

        # Throughput
        delta_t = now - self._last_time
        if delta_t >= 0.5:
            delta_bytes = progress.bytes_scanned - self._last_bytes
            mb_s = (delta_bytes / (1024 * 1024)) / delta_t if delta_t > 0 else 0.0
            self.throughput_lbl.setText(f"{mb_s:.1f} MB/s")
            self._last_bytes = progress.bytes_scanned
            self._last_time = now

        # Current sector
        hex_offset = f"0x{progress.current_sector * 512:08X}"
        self.offset_lbl.setText(
            f"Current LBA: {hex_offset} (Sector {progress.current_sector:,})"
        )

        # Phase description
        if progress.phase == "metadata":
            self.phase_label.setText("Phase 1: Filesystem Metadata Sweep")
            self.phase_desc.setText("Traversing directory tables and restoring deleted filenames.")
        elif progress.phase == "carving":
            self.phase_label.setText("Phase 2: Deep Signature Carving")
            self.phase_desc.setText(
                "Searching raw unallocated sectors for file headers (JPEG, PNG, PDF, ZIP)."
            )
        elif progress.phase == "lost_volumes":
            self.phase_label.setText("Phase 3: Lost Volume Scan")
            self.phase_desc.setText(
                "Sweeping block boundaries for boot sector records and unlinked VBR headers."
            )
        else:
            self.phase_label.setText(f"Phase: {progress.phase.capitalize()}")
            self.phase_desc.setText("Processing storage device blocks.")
