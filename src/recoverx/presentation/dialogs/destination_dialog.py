"""Recovery destination selection dialog enforcing strict source/destination separation."""

import logging
import shutil
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from recoverx.config import CollisionPolicy
from recoverx.infrastructure.storage.base import ReadOnlyBlockDevice
from recoverx.infrastructure.storage.resolver import (
    DestinationOnSourceError,
    VolumeIdentityResolver,
)

logger = logging.getLogger(__name__)


class RecoveryDestinationDialog(QDialog):
    """Recovery wizard dialog with destination separation verification.

    Rules 2 & 3 of CLAUDE.md:
    Nothing the app creates goes on the source device or on any volume of the same physical disk.
    If separation cannot be verified with confidence, refuse.
    """

    def __init__(
        self,
        source_device: ReadOnlyBlockDevice,
        resolver: VolumeIdentityResolver,
        total_files: int,
        total_bytes: int,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.source_device = source_device
        self.resolver = resolver
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.selected_destination: Path | None = None
        self.selected_policy = CollisionPolicy.RENAME

        self.setWindowTitle("Select Recovery Destination")
        self.setAccessibleName("Recovery Destination Dialog")
        self.setAccessibleDescription(
            "Dialog to select and verify a safe destination directory on a separate storage medium"
        )
        self.resize(550, 420)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Overview notice
        summary_text = (
            f"Ready to extract <strong>{self.total_files} file(s)</strong> "
            f"({self.total_bytes:,} bytes total)."
        )
        summary_label = QLabel(summary_text)
        summary_label.setAccessibleName("Recovery file count summary")
        layout.addWidget(summary_label)

        # Safety rule banner
        safety_notice = QLabel(
            "<strong>Forensic Safety Guarantee:</strong> Destination must reside on a completely "
            "separate physical disk or volume to prevent overwriting "
            "unrecovered data on the source."
        )
        safety_notice.setWordWrap(True)
        safety_notice.setStyleSheet(
            "background-color: #eff6ff; border-left: 4px solid #3b82f6; "
            "padding: 10px; border-radius: 4px; color: #1e3a8a;"
        )
        safety_notice.setAccessibleName("Destination separation safety notice")
        layout.addWidget(safety_notice)

        # Path selection box
        layout.addWidget(QLabel("<strong>Destination Directory:</strong>"))
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setAccessibleName("Destination directory path input")
        self.path_edit.setPlaceholderText("Select a folder on a separate drive...")
        self.path_edit.textChanged.connect(self._validate_destination)
        path_layout.addWidget(self.path_edit)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setAccessibleName("Browse destination directory button")
        self.browse_btn.clicked.connect(self._browse_directory)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # Verification feedback label
        self.status_label = QLabel("Please choose a destination directory.")
        self.status_label.setAccessibleName("Destination verification status message")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 8px; border-radius: 4px; color: #64748b;")
        layout.addWidget(self.status_label)

        # Collision Policy Group
        policy_group = QGroupBox("File Name Collision Policy")
        policy_group.setAccessibleName("Collision policy options group")
        policy_layout = QVBoxLayout(policy_group)

        self.rename_radio = QRadioButton("Rename automatically with (1), (2) [Recommended]")
        self.rename_radio.setAccessibleName("Rename collision policy radio button")
        self.rename_radio.setChecked(True)
        policy_layout.addWidget(self.rename_radio)

        self.skip_radio = QRadioButton("Skip existing files without overwriting")
        self.skip_radio.setAccessibleName("Skip collision policy radio button")
        policy_layout.addWidget(self.skip_radio)

        self.fail_radio = QRadioButton("Fail immediately if any file collision occurs")
        self.fail_radio.setAccessibleName("Fail collision policy radio button")
        policy_layout.addWidget(self.fail_radio)

        layout.addWidget(policy_group)

        # Dialog buttons
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Start Recovery")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setAccessibleName(
            "Confirm start recovery button"
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).setAccessibleName(
            "Cancel recovery button"
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.button_box.accepted.connect(self._on_confirm)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _browse_directory(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Select Recovery Destination Directory")
        if chosen:
            self.path_edit.setText(chosen)

    def _validate_destination(self) -> None:
        raw_path = self.path_edit.text().strip()
        ok_btn = self.button_box.button(QDialogButtonBox.StandardButton.Ok)

        if not raw_path:
            self.status_label.setText("Please choose a destination directory.")
            self.status_label.setStyleSheet("color: #64748b; padding: 8px;")
            ok_btn.setEnabled(False)
            return

        dest_path = Path(raw_path)
        try:
            # Enforce separation via VolumeIdentityResolver (Rule 2 & 3 of CLAUDE.md)
            self.resolver.verify_separation(
                self.source_device,
                dest_path,
                role="destination directory",
            )

            # Check free space
            free_bytes = 0
            probe_dir = dest_path if dest_path.exists() else dest_path.parent
            if probe_dir.exists():
                free_bytes = shutil.disk_usage(str(probe_dir)).free

            if free_bytes > 0 and free_bytes < self.total_bytes:
                self.status_label.setText(
                    f"Warning: Destination has only {free_bytes:,} bytes free; "
                    f"recovery requires {self.total_bytes:,} bytes."
                )
                self.status_label.setStyleSheet(
                    "background-color: #fefce8; color: #854d0e; padding: 8px; border-radius: 4px;"
                )
            else:
                self.status_label.setText(
                    "Verified: Destination resides on a confirmed separate volume."
                )
                self.status_label.setStyleSheet(
                    "background-color: #dcfce7; color: #166534; padding: 8px; border-radius: 4px;"
                )

            ok_btn.setEnabled(True)

        except DestinationOnSourceError as exc:
            self.status_label.setText(
                f"Refused: Destination is on the same volume or physical disk as source! ({exc})"
            )
            self.status_label.setStyleSheet(
                "background-color: #fee2e2; color: #991b1b; "
                "padding: 8px; border-radius: 4px; font-weight: 600;"
            )
            ok_btn.setEnabled(False)
        except Exception as exc:
            self.status_label.setText(f"Separation check error: {exc}")
            self.status_label.setStyleSheet(
                "background-color: #fee2e2; color: #991b1b; padding: 8px; border-radius: 4px;"
            )
            ok_btn.setEnabled(False)

    def _on_confirm(self) -> None:
        self.selected_destination = Path(self.path_edit.text().strip())
        if self.skip_radio.isChecked():
            self.selected_policy = CollisionPolicy.SKIP
        elif self.fail_radio.isChecked():
            self.selected_policy = CollisionPolicy.OVERWRITE_NEVER
        else:
            self.selected_policy = CollisionPolicy.RENAME
        self.accept()
