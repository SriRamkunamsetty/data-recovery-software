"""Candidate recovery results page with filtering, category tree, selection, and preview actions."""

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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
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
            return f"{size_float:.1f} {unit}"
    return f"{size_float:.1f} PiB"


class RecoveryResultsPage(QWidget):
    """Results page displaying discovered candidates with search, filtering, and recovery."""

    preview_requested = Signal(object)  # RecoveryCandidate
    recovery_requested = Signal(list)  # list[str] (candidate_ids)
    report_requested = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.all_candidates: list[RecoveryCandidate] = []
        self.filtered_candidates: list[RecoveryCandidate] = []
        self._selected_category_ext: str | None = None

        self.setAccessibleName("Recovery Results Page")
        self.setAccessibleDescription(
            "View discovered files, filter by filename or status, "
            "preview file contents, and recover files"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        # 1. Header with Discovered Summary
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title = QLabel("Recovered Files")
        title.setProperty("class", "PageTitle")
        title.setAccessibleName("Recovery Results Page Title")
        header_text.addWidget(title)

        self.summary_subtitle = QLabel("0 files found (0 B) • Select files to extract and recover")
        self.summary_subtitle.setProperty("class", "PageSubtitle")
        header_text.addWidget(self.summary_subtitle)
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)

        layout.addLayout(header_layout)

        # 2. Filter Toolbar (Screenshot 5)
        filter_toolbar = QFrame()
        filter_toolbar.setProperty("class", "CardFrame")
        filter_layout = QHBoxLayout(filter_toolbar)
        filter_layout.setContentsMargins(12, 8, 12, 8)
        filter_layout.setSpacing(12)

        # Search bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Search files or paths...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Filename search input")
        self.search_edit.textChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.search_edit, stretch=2)

        # Type filter dropdown
        self.type_combo = QComboBox()
        self.type_combo.addItems(
            ["All Types", "Images", "Documents", "Videos", "Archives", "Others"]
        )
        self.type_combo.currentTextChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.type_combo)

        # Status filter dropdown
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

        # Method filter dropdown
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

        layout.addWidget(filter_toolbar)

        # 3. Main Split View: Left Tree + Right Table (Screenshot 5)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Category Tree
        tree_card = QFrame()
        tree_card.setProperty("class", "CardFrame")
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(8, 8, 8, 8)

        tree_header = QLabel("<strong>File Categories</strong>")
        tree_header.setStyleSheet("color: #94a3b8; font-size: 12px; margin-bottom: 4px;")
        tree_layout.addWidget(tree_header)

        self.category_tree = QTreeWidget()
        self.category_tree.setHeaderHidden(True)
        self.category_tree.itemClicked.connect(self._on_tree_item_clicked)
        tree_layout.addWidget(self.category_tree)
        splitter.addWidget(tree_card)

        # Right: Candidate Files Table
        table_card = QFrame()
        table_card.setProperty("class", "CardFrame")
        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(8, 8, 8, 8)

        # Quick selection buttons row inside table card
        quick_sel_row = QHBoxLayout()
        sel_all_btn = QPushButton("Select All")
        sel_all_btn.clicked.connect(self._select_all)
        quick_sel_row.addWidget(sel_all_btn)

        desel_btn = QPushButton("Deselect All")
        desel_btn.clicked.connect(self._deselect_all)
        quick_sel_row.addWidget(desel_btn)

        sel_valid_btn = QPushButton("Select Validated Only")
        sel_valid_btn.clicked.connect(self._select_validated_only)
        quick_sel_row.addWidget(sel_valid_btn)
        quick_sel_row.addStretch(1)
        table_card_layout.addLayout(quick_sel_row)

        self.table = QTableWidget()
        self.table.setAccessibleName("Discovered Candidates Table")
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["", "Filename", "Path / Origin", "Size", "Type", "Status", "Method"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            5, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            6, QHeaderView.ResizeMode.ResizeToContents
        )

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.table.itemChanged.connect(self._on_table_item_changed)
        table_card_layout.addWidget(self.table)

        splitter.addWidget(table_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, stretch=1)

        # 4. Bottom Action Bar (Screenshot 5)
        bottom_bar = QHBoxLayout()
        self.sel_count_lbl = QLabel("0 files selected (0 B)")
        self.sel_count_lbl.setStyleSheet("color: #60a5fa; font-weight: 600; font-size: 13px;")
        bottom_bar.addWidget(self.sel_count_lbl)
        bottom_bar.addStretch(1)

        self.preview_btn = QPushButton("👁 Preview File...")
        self.preview_btn.setProperty("class", "SecondaryButton")
        self.preview_btn.clicked.connect(self._on_preview_clicked)
        bottom_bar.addWidget(self.preview_btn)

        self.report_btn = QPushButton("View Forensic Report →")
        self.report_btn.setProperty("class", "SecondaryButton")
        self.report_btn.setAccessibleName("View Forensic Report Button")
        self.report_btn.clicked.connect(self.report_requested.emit)
        bottom_bar.addWidget(self.report_btn)

        export_list_btn = QPushButton("Export List...")
        export_list_btn.setProperty("class", "SecondaryButton")
        bottom_bar.addWidget(export_list_btn)

        self.recover_btn = QPushButton("Recover Selected Files →")
        self.recover_btn.setProperty("class", "PrimaryButton")
        self.recover_btn.setAccessibleName("Recover Selected Files Button")
        self.recover_btn.clicked.connect(self._on_recover_clicked)
        bottom_bar.addWidget(self.recover_btn)

        layout.addLayout(bottom_bar)

    def set_candidates(self, candidates: list[RecoveryCandidate]) -> None:
        """Populate the table and category tree with discovered candidates."""
        self.all_candidates = candidates
        total_size = sum(c.size_bytes for c in candidates)
        self.summary_subtitle.setText(
            f"{len(candidates):,} files found ({_format_size(total_size)}) • "
            "Select files to extract and recover"
        )
        self._populate_category_tree()
        self._apply_filters()

    def _populate_category_tree(self) -> None:
        self.category_tree.clear()
        all_root = QTreeWidgetItem([f"📁 All Files ({len(self.all_candidates)})"])
        all_root.setData(0, Qt.ItemDataRole.UserRole, None)

        img_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg"}
        doc_exts = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".csv"}
        vid_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"}
        arc_exts = {".zip", ".rar", ".7z", ".tar", ".gz"}

        counts: dict[str, dict[str, int]] = {
            "Images": {},
            "Documents": {},
            "Videos": {},
            "Archives": {},
            "Other Files": {},
        }

        for c in self.all_candidates:
            ext = c.extension.lower()
            if ext in img_exts:
                counts["Images"][ext] = counts["Images"].get(ext, 0) + 1
            elif ext in doc_exts:
                counts["Documents"][ext] = counts["Documents"].get(ext, 0) + 1
            elif ext in vid_exts:
                counts["Videos"][ext] = counts["Videos"].get(ext, 0) + 1
            elif ext in arc_exts:
                counts["Archives"][ext] = counts["Archives"].get(ext, 0) + 1
            else:
                counts["Other Files"][ext] = counts["Other Files"].get(ext, 0) + 1

        icons = {
            "Images": "📷",
            "Documents": "📄",
            "Videos": "🎬",
            "Archives": "📦",
            "Other Files": "📁",
        }

        for cat, subcounts in counts.items():
            tot = sum(subcounts.values())
            cat_item = QTreeWidgetItem([f"{icons[cat]} {cat} ({tot})"])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, cat)
            for ext, cnt in subcounts.items():
                child = QTreeWidgetItem([f"{ext.upper().lstrip('.')} ({cnt})"])
                child.setData(0, Qt.ItemDataRole.UserRole, ext)
                cat_item.addChild(child)
            all_root.addChild(cat_item)

        self.category_tree.addTopLevelItem(all_root)
        all_root.setExpanded(True)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        target = item.data(0, Qt.ItemDataRole.UserRole)
        self._selected_category_ext = target
        self._apply_filters()

    def _apply_filters(self) -> None:
        search_text = self.search_edit.text().strip().lower()
        status_filter = self.status_combo.currentText()
        origin_filter = self.origin_combo.currentText()

        img_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".svg"}
        doc_exts = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".csv"}
        vid_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv"}
        arc_exts = {".zip", ".rar", ".7z", ".tar", ".gz"}

        filtered = []
        for c in self.all_candidates:
            # 1. Search text
            if search_text and (
                search_text not in c.filename.lower()
                and search_text not in c.relative_path.lower()
            ):
                continue

            # 2. Status filter
            if status_filter != "All Statuses" and c.status.value != status_filter:
                continue

            # 3. Method filter
            if origin_filter != "All Methods" and c.source_method.value != origin_filter:
                continue

            # 4. Tree category selection
            if self._selected_category_ext:
                ext = c.extension.lower()
                cat = self._selected_category_ext
                if cat == "Images" and ext not in img_exts:
                    continue
                if cat == "Documents" and ext not in doc_exts:
                    continue
                if cat == "Videos" and ext not in vid_exts:
                    continue
                if cat == "Archives" and ext not in arc_exts:
                    continue
                if cat == "Other Files" and (
                    ext in img_exts or ext in doc_exts or ext in vid_exts or ext in arc_exts
                ):
                    continue
                if cat.startswith(".") and ext != cat:
                    continue

            filtered.append(c)

        self.filtered_candidates = filtered
        self._update_table()

    def _update_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.filtered_candidates))

        for row, c in enumerate(self.filtered_candidates):
            # Checkbox item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk_item.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, chk_item)

            # Filename
            file_item = QTableWidgetItem(c.filename)
            file_item.setData(Qt.ItemDataRole.UserRole, c.candidate_id)
            self.table.setItem(row, 1, file_item)

            # Path / Origin
            self.table.setItem(row, 2, QTableWidgetItem(c.relative_path or "/"))

            # Size
            size_item = QTableWidgetItem(_format_size(c.size_bytes))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, size_item)

            # Type
            type_item = QTableWidgetItem(c.extension.upper().lstrip(".") or "BIN")
            self.table.setItem(row, 4, type_item)

            # Status pill
            status_item = QTableWidgetItem(c.status.value)
            if c.status == CandidateStatus.PREVIEW_VALIDATED:
                status_item.setForeground(Qt.GlobalColor.green)
            elif c.status == CandidateStatus.CORRUPTED:
                status_item.setForeground(Qt.GlobalColor.red)
            elif c.status == CandidateStatus.TRUNCATED:
                status_item.setForeground(Qt.GlobalColor.yellow)
            self.table.setItem(row, 5, status_item)

            # Method
            method_item = QTableWidgetItem(c.source_method.value)
            self.table.setItem(row, 6, method_item)

        self.table.blockSignals(False)
        self._update_selection_counter()

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_selection_counter()

    def _update_selection_counter(self) -> None:
        selected_ids = self._get_selected_candidate_ids()
        cands_map = {c.candidate_id: c for c in self.all_candidates}
        tot_bytes = sum(cands_map[cid].size_bytes for cid in selected_ids if cid in cands_map)
        self.sel_count_lbl.setText(
            f"{len(selected_ids):,} files selected ({_format_size(tot_bytes)})"
        )
        self.recover_btn.setEnabled(len(selected_ids) > 0)

    def _select_all(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        self.table.blockSignals(False)
        self._update_selection_counter()

    def _deselect_all(self) -> None:
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_counter()

    def _select_validated_only(self) -> None:
        self.table.blockSignals(True)
        for row, c in enumerate(self.filtered_candidates):
            item = self.table.item(row, 0)
            if item:
                if c.status == CandidateStatus.PREVIEW_VALIDATED:
                    item.setCheckState(Qt.CheckState.Checked)
                else:
                    item.setCheckState(Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self._update_selection_counter()

    def _get_selected_candidate_ids(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.table.rowCount()):
            chk = self.table.item(row, 0)
            if chk and chk.checkState() == Qt.CheckState.Checked:
                file_item = self.table.item(row, 1)
                if file_item:
                    cid = file_item.data(Qt.ItemDataRole.UserRole)
                    if cid:
                        selected.append(cid)
        return selected

    def _on_row_double_clicked(self, row: int, column: int) -> None:
        if 0 <= row < len(self.filtered_candidates):
            self.preview_requested.emit(self.filtered_candidates[row])

    def _on_preview_clicked(self) -> None:
        rows = self.table.selectedItems()
        if rows:
            row = rows[0].row()
            if 0 <= row < len(self.filtered_candidates):
                self.preview_requested.emit(self.filtered_candidates[row])
        elif self.filtered_candidates:
            self.preview_requested.emit(self.filtered_candidates[0])

    def _on_recover_clicked(self) -> None:
        selected_ids = self._get_selected_candidate_ids()
        if selected_ids:
            self.recovery_requested.emit(selected_ids)
