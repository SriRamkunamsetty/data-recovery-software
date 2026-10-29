"""Safe, sandboxed file preview dialog with resource limits and failure protection."""

import base64
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.presentation.preview.sandbox import PreviewResult, PreviewSandbox

logger = logging.getLogger(__name__)

MAX_PREVIEW_BYTES = 5 * 1024 * 1024  # 5 MiB ceiling for in-dialog preview decoding


class FilePreviewDialog(QDialog):
    """Untrusted file preview dialog with strict resource limits and process isolation.

    Section 11 of MASTER_PROMPT.md:
    Recovered files are untrusted. Previews run with strict limits in a separate
    subprocess that can be killed. Preview success displays content; failure displays
    'Unverified' with the reason, never crashes or hangs the GUI.
    """

    def __init__(
        self,
        candidate: RecoveryCandidate,
        device: ReadOnlyBlockDevice,
        sandbox: PreviewSandbox | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.device = device
        self.sandbox = sandbox or PreviewSandbox()

        self.setWindowTitle(f"Preview - {candidate.filename}")
        self.setAccessibleName("File Preview Dialog")
        self.setAccessibleDescription(
            f"Preview for candidate file {candidate.filename} at offset {candidate.source_offset}"
        )
        self.resize(650, 520)

        self._setup_ui()
        self._load_preview()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header info
        info_label = QLabel(
            f"<strong>{self.candidate.filename}</strong> &bull; "
            f"Size: {self.candidate.size_bytes:,} bytes &bull; "
            f"Status: {self.candidate.status.value}"
        )
        info_label.setAccessibleName("Candidate metadata info")
        layout.addWidget(info_label)

        # Content container
        self.preview_container = QVBoxLayout()
        layout.addLayout(self.preview_container)

        # Dialog buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.setAccessibleName("Close preview button")
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _load_preview(self) -> None:
        ext = self.candidate.extension.lower()

        if self.candidate.size_bytes == 0:
            self._show_text_message("Empty file (0 bytes). No preview available.")
            return

        if self.candidate.size_bytes > MAX_PREVIEW_BYTES:
            self._show_text_message(
                f"Candidate size ({self.candidate.size_bytes:,} bytes) exceeds the preview ceiling "
                f"({MAX_PREVIEW_BYTES:,} bytes).\n\n"
                "To protect memory and prevent GUI hangs, large previews are restricted.\n"
                "You can recover this file to a separate drive to inspect its complete contents."
            )
            return

        read_len = min(self.candidate.size_bytes, MAX_PREVIEW_BYTES)
        try:
            data = self.device.read_at(self.candidate.source_offset, read_len)
        except Exception as exc:
            logger.warning("Failed to read candidate bytes for preview: %s", exc)
            self._show_failure_message(f"Preview failed: Read error ({exc})")
            return

        # Execute preview generation in sandboxed subprocess
        result: PreviewResult = self.sandbox.generate_preview(data, ext)

        if not result.success or result.preview_type == "error":
            self._show_failure_message(
                f"Unverified: {result.error or 'Failed to decode file structure'}"
            )
            return

        # 1. Render Image
        if result.preview_type == "image" and result.image_b64:
            try:
                png_bytes = base64.b64decode(result.image_b64.encode("ascii"))
                pixmap = QPixmap()
                if pixmap.loadFromData(png_bytes) and not pixmap.isNull():
                    img_label = QLabel()
                    img_label.setAccessibleName(f"Image preview of {self.candidate.filename}")
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    scaled = pixmap.scaled(
                        580,
                        360,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    img_label.setPixmap(scaled)
                    self.preview_container.addWidget(img_label)

                    w = result.metadata.get("width", pixmap.width())
                    h = result.metadata.get("height", pixmap.height())
                    fmt = result.metadata.get("format", ext.upper())
                    dim_label = QLabel(f"Dimensions: {w} &times; {h} px &bull; Format: {fmt}")
                    dim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    dim_label.setStyleSheet("color: #64748b; font-size: 11px;")
                    self.preview_container.addWidget(dim_label)
                    return
            except Exception as exc:
                logger.warning("Error rendering base64 image pixmap: %s", exc)

        # 2. Render Text
        if result.preview_type == "text":
            text_edit = QPlainTextEdit()
            text_edit.setAccessibleName(f"Text preview of {self.candidate.filename}")
            text_edit.setReadOnly(True)
            text_edit.setPlainText(result.content)
            self.preview_container.addWidget(text_edit)
            return

        # 3. Render Archive Listing (ZIP / OOXML)
        if result.preview_type == "archive":
            card = QFrame()
            card.setStyleSheet(
                "background-color: #f8fafc; border: 1px solid #e2e8f0; "
                "border-radius: 6px; padding: 8px;"
            )
            card_layout = QVBoxLayout(card)

            doc_type = result.metadata.get("document_type", "Archive")
            total = result.metadata.get("total_entries", 0)
            zip_slip = result.metadata.get("zip_slip_risk", "None")

            status_text = (
                f"<strong>Type:</strong> {doc_type} &bull; <strong>Entries:</strong> {total}"
            )
            if zip_slip != "None":
                status_text += (
                    f" &bull; <span style='color: #dc2626; font-weight: bold;'>"
                    f"Security Risk: {zip_slip}</span>"
                )
            card_layout.addWidget(QLabel(status_text))

            if result.entries:
                table = QTableWidget(len(result.entries), 2)
                table.setHorizontalHeaderLabels(["Filename", "Uncompressed Size"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                for r, item in enumerate(result.entries):
                    table.setItem(r, 0, QTableWidgetItem(str(item.get("name", ""))))
                    table.setItem(r, 1, QTableWidgetItem(f"{item.get('size', 0):,} B"))
                card_layout.addWidget(table)

            self.preview_container.addWidget(card)
            return

        # 4. Render Multimedia / Database Metadata Cards
        if result.metadata:
            meta_frame = QFrame()
            meta_frame.setStyleSheet(
                "background-color: #f8fafc; border: 1px solid #e2e8f0; "
                "border-radius: 6px; padding: 12px;"
            )
            grid = QGridLayout(meta_frame)

            for row, (k, v) in enumerate(result.metadata.items()):
                label_key = QLabel(f"<strong>{k.replace('_', ' ').title()}:</strong>")
                label_val = QLabel(str(v))
                grid.addWidget(label_key, row, 0)
                grid.addWidget(label_val, row, 1)

            self.preview_container.addWidget(meta_frame)
            return

        # Generic fallback
        self._show_text_message(
            f"Binary format ({ext or 'unknown'}).\n"
            f"Source Offset: 0x{self.candidate.source_offset:X}\n"
            f"Size: {self.candidate.size_bytes:,} bytes\n"
            f"Status: {self.candidate.status.value}"
        )

    def _show_failure_message(self, message: str) -> None:
        """Display safe failure alert without crashing or hanging."""
        fail_label = QLabel(f"<strong>Notice:</strong> {message}")
        fail_label.setAccessibleName("Preview failure notice")
        fail_label.setWordWrap(True)
        fail_label.setStyleSheet(
            "background-color: #fee2e2; color: #991b1b; padding: 16px; border-radius: 6px;"
        )
        self.preview_container.addWidget(fail_label)

    def _show_text_message(self, message: str) -> None:
        label = QLabel(message)
        label.setAccessibleName("Preview information text")
        label.setWordWrap(True)
        label.setStyleSheet(
            "background-color: #f1f5f9; color: #334155; padding: 16px; border-radius: 6px;"
        )
        self.preview_container.addWidget(label)
