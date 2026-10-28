"""Candidate recovery results page with filtering, selection, and preview actions."""

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.domain.enums import CandidateStatus, RecoverySourceMethod

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


class RecoveryResultsPage(QWidget):
    """Results page displaying discovered candidates with search, filtering, and recovery.

    Rule 7 of CLAUDE.md:
    Accurate factual candidate statuses only.
    No percentage recovery probability.
    """

    preview_requested = Signal(object)  # RecoveryCandidate
    recovery_requested = Signal(list)  # list[str] (candidate_ids)
    report_requested = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.all_candidates: list[RecoveryCandidate] = []
        self.filtered_candidates: list[RecoveryCandidate] = []

        self.setAccessibleName("Recovery Results Page")
        self.setAccessibleDescription(
            "View discovered files, filter by filename or status, "
            "preview file contents, and recover files"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # Title and header
        title = QLabel("Discovered Recovery Candidates")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Recovery Results Page Title")
        layout.addWidget(title)

        # Filter bar
        filter_card = QFrame()
        filter_card.setProperty("class", "CardFrame")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(12)

        # Search box
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search filenames or paths...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Filename search input")
        self.search_edit.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_edit, stretch=2)

        # Status filter dropdown
        status_label = QLabel("Status:")
        filter_layout.addWidget(status_label)
        self.status_combo = QComboBox()
        self.status_combo.setAccessibleName("Candidate status filter dropdown")
        self.status_combo.addItems(
            [
                "All Statuses",
                CandidateStatus.PREVIEW_VALIDATED.value,
                CandidateStatus.METADATA_RECOVERED.value,
                CandidateStatus.SIGNATURE_MATCHED.value,
                CandidateStatus.TRUNCATED.value,
                CandidateStatus.CORRUPTED.value,
                CandidateStatus.OVERWRITTEN.value,
            ]
        )
        self.status_combo.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.status_combo)

        # Origin filter dropdown
        origin_label = QLabel("Method:")
        filter_layout.addWidget(origin_label)
        self.origin_combo = QComboBox()
        self.origin_combo.setAccessibleName("Candidate method filter dropdown")
        self.origin_combo.addItems(
            [
                "All Methods",
                RecoverySourceMethod.METADATA.value,
                RecoverySourceMethod.CARVED.value,
                RecoverySourceMethod.LOST_VOLUME.value,
            ]
        )
        self.origin_combo.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.origin_combo)

        layout.addWidget(filter_card)

        # Quick selection bar
        sel_bar = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.setAccessibleName("Select All Files Button")
        select_all_btn.clicked.connect(self._select_all)
        sel_bar.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.setAccessibleName("Deselect All Files Button")
        deselect_all_btn.clicked.connect(self._deselect_all)
        sel_bar.addWidget(deselect_all_btn)

        select_verified_btn = QPushButton("Select Validated Only")
        select_verified_btn.setAccessibleName("Select Validated Files Button")
        select_verified_btn.clicked.connect(self._select_validated_only)
        sel_bar.addWidget(select_verified_btn)

        sel_bar.addStretch(1)

        self.selection_summary_lbl = QLabel("0 of 0 files selected (0 B)")
        self.selection_summary_lbl.setAccessibleName("Selection summary counter")
        self.selection_summary_lbl.setStyleSheet("color: #64748b; font-weight: 500;")
        sel_bar.addWidget(self.selection_summary_lbl)

        layout.addLayout(sel_bar)

        # Candidate table
        self.table = QTableWidget()
        self.table.setAccessibleName("Discovered Candidates Table")
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "Filename / Path", "Size", "Format", "Origin", "Status", "Source Offset"]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemDoubleClicked.connect(self._on_table_double_click)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

        # Action bar at bottom
        action_layout = QHBoxLayout()

        self.preview_btn = QPushButton("Preview File...")
        self.preview_btn.setAccessibleName("Preview Selected File Button")
        self.preview_btn.setEnabled(False)
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        action_layout.addWidget(self.preview_btn)

        action_layout.addStretch(1)

        self.report_btn = QPushButton("Forensic Report &rarr;")
        self.report_btn.setAccessibleName("View Forensic Report Button")
        self.report_btn.clicked.connect(self.report_requested.emit)
        action_layout.addWidget(self.report_btn)

        self.recover_btn = QPushButton("Recover Selected Files...")
        self.recover_btn.setProperty("class", "PrimaryButton")
        self.recover_btn.setAccessibleName("Recover Selected Files Button")
        self.recover_btn.setEnabled(False)
        self.recover_btn.clicked.connect(self._on_recover_clicked)
        action_layout.addWidget(self.recover_btn)

        layout.addLayout(action_layout)

    def set_candidates(self, candidates: list[RecoveryCandidate]) -> None:
        """Populate the table with scanned recovery candidates."""
        self.all_candidates = list(candidates)
        self._apply_filters()

    def _apply_filters(self) -> None:
        search_text = self.search_edit.text().strip().lower()
        selected_status = self.status_combo.currentText()
        selected_origin = self.origin_combo.currentText()

        self.filtered_candidates = []
        for cand in self.all_candidates:
            # Filename filter
            if search_text and (
                search_text not in cand.filename.lower()
                and (not cand.relative_path or search_text not in cand.relative_path.lower())
            ):
                continue

            # Status filter
            if selected_status != "All Statuses" and cand.status.value != selected_status:
                continue

            # Origin filter
            if selected_origin != "All Methods" and cand.source_method.value != selected_origin:
                continue

            self.filtered_candidates.append(cand)

        self._populate_table()

    def _populate_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.filtered_candidates))

        for row, cand in enumerate(self.filtered_candidates):
            # Checkbox item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            chk_item.setData(Qt.ItemDataRole.UserRole, cand.candidate_id)
            self.table.setItem(row, 0, chk_item)

            # Filename
            display_name = cand.relative_path or cand.filename
            name_item = QTableWidgetItem(display_name)
            name_item.setToolTip(f"ID: {cand.candidate_id}\nSHA256: {cand.sha256_hash or 'None'}")
            self.table.setItem(row, 1, name_item)

            # Size
            size_item = QTableWidgetItem(_format_size(cand.size_bytes))
            size_item.setData(Qt.ItemDataRole.UserRole, cand.size_bytes)
            self.table.setItem(row, 2, size_item)

            # Format
            fmt_str = cand.extension.upper() if cand.extension else "UNKNOWN"
            self.table.setItem(row, 3, QTableWidgetItem(fmt_str))

            # Origin / Method
            self.table.setItem(row, 4, QTableWidgetItem(cand.source_method.value))

            # Status
            status_item = QTableWidgetItem(cand.status.value)
            self.table.setItem(row, 5, status_item)

            # Source Offset
            offset_item = QTableWidgetItem(f"0x{cand.source_offset:X}")
            self.table.setItem(row, 6, offset_item)

        self.table.blockSignals(False)
        self._update_selection_summary()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_selection_summary()

    def _on_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        self.preview_btn.setEnabled(len(selected_rows) == 1)

    def _update_selection_summary(self) -> None:
        selected_count = 0
        selected_bytes = 0

        for row in range(self.table.rowCount()):
            chk_item = self.table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                selected_count += 1
                size_item = self.table.item(row, 2)
                if size_item:
                    size_val = size_item.data(Qt.ItemDataRole.UserRole)
                    if isinstance(size_val, int):
                        selected_bytes += size_val

        total_count = len(self.filtered_candidates)
        self.selection_summary_lbl.setText(
            f"{selected_count} of {total_count} files selected ({_format_size(selected_bytes)})"
        )
        self.recover_btn.setEnabled(selected_count > 0)

    def _select_all(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._update_selection_summary()

    def _deselect_all(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_summary()

    def _select_validated_only(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            cand = self.filtered_candidates[row]
            item = self.table.item(row, 0)
            if item:
                if cand.status in (
                    CandidateStatus.PREVIEW_VALIDATED,
                    CandidateStatus.METADATA_RECOVERED,
                    CandidateStatus.SIGNATURE_MATCHED,
                ):
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_summary()

    def _get_selected_candidate_ids(self) -> list[str]:
        ids: list[str] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                cand_id = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(cand_id, str):
                    ids.append(cand_id)
        return ids

    def _on_preview_clicked(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if len(selected_rows) == 1:
            row = selected_rows[0].row()
            if 0 <= row < len(self.filtered_candidates):
                cand = self.filtered_candidates[row]
                self.preview_requested.emit(cand)

    def _on_table_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if 0 <= row < len(self.filtered_candidates):
            cand = self.filtered_candidates[row]
            self.preview_requested.emit(cand)

    def _on_recover_clicked(self) -> None:
        cand_ids = self._get_selected_candidate_ids()
        if cand_ids:
            self.recovery_requested.emit(cand_ids)
