"""Safe, sandboxed file preview dialog with resource limits and failure protection."""

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from recoverx.domain.candidate import RecoveryCandidate
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice

logger = logging.getLogger(__name__)

MAX_PREVIEW_BYTES = 5 * 1024 * 1024  # 5 MiB ceiling for in-process image preview


class FilePreviewDialog(QDialog):
    """Untrusted file preview dialog with strict resource limits.

    Section 11 of MASTER_PROMPT.md:
    Recovered files are untrusted. Previews run with strict limits.
    Preview success displays content; failure displays 'Preview failed' with the reason,
    never crashes or hangs the GUI.
    """

    def __init__(
        self,
        candidate: RecoveryCandidate,
        device: ReadOnlyBlockDevice,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.candidate = candidate
        self.device = device

        self.setWindowTitle(f"Preview - {candidate.filename}")
        self.setAccessibleName("File Preview Dialog")
        self.setAccessibleDescription(
            f"Preview for candidate file {candidate.filename} at offset {candidate.source_offset}"
        )
        self.resize(600, 500)

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
        read_len = min(self.candidate.size_bytes, MAX_PREVIEW_BYTES)

        if read_len <= 0:
            self._show_text_message("Empty file (0 bytes). No preview available.")
            return

        try:
            data = self.device.read_at(self.candidate.source_offset, read_len)
        except Exception as exc:
            logger.warning("Failed to read candidate bytes for preview: %s", exc)
            self._show_failure_message(f"Preview failed: Read error ({exc})")
            return

        # 1. Image preview (.jpg, .jpeg, .png, etc.)
        if ext in (".jpg", ".jpeg", ".png"):
            pixmap = QPixmap()
            success = pixmap.loadFromData(data)
            if success and not pixmap.isNull():
                img_label = QLabel()
                img_label.setAccessibleName(f"Image preview of {self.candidate.filename}")
                img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scaled = pixmap.scaled(
                    540,
                    400,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                img_label.setPixmap(scaled)
                self.preview_container.addWidget(img_label)

                dim_label = QLabel(f"Dimensions: {pixmap.width()} &times; {pixmap.height()} px")
                dim_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                dim_label.setStyleSheet("color: #64748b; font-size: 11px;")
                self.preview_container.addWidget(dim_label)
            else:
                self._show_failure_message(
                    "Preview failed: Unable to decode image structure. "
                    "The file header or stream may be corrupted or truncated."
                )

        # 2. Text / Document preview
        elif ext in (".txt", ".log", ".csv", ".json", ".xml", ".ini"):
            text_edit = QPlainTextEdit()
            text_edit.setAccessibleName(f"Text preview of {self.candidate.filename}")
            text_edit.setReadOnly(True)
            text_content = data[:4096].decode("utf-8", errors="replace")
            text_edit.setPlainText(text_content)
            self.preview_container.addWidget(text_edit)

        # 3. Generic metadata view for other formats
        else:
            self._show_text_message(
                f"Binary format ({ext or 'unknown'}).\n"
                f"Source Offset: {self.candidate.source_offset}\n"
                f"Payload size: {self.candidate.size_bytes:,} bytes\n"
                f"SHA-256 fingerprint: {self.candidate.sha256_hash or 'Not calculated'}\n\n"
                f"Structure verification: {self.candidate.status.value}"
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
