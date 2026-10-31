"""Modern interactive toggle switch widget (pill slider)."""

from typing import Any

from PySide6.QtCore import Property, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    """Modern pill slider toggle switch replacing traditional checkboxes."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(False)
        self._position: float = 0.0  # 0.0 = unchecked, 1.0 = checked

        self._track_radius: float = 12.0
        self._thumb_radius: float = 9.0

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(46, 24))
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._position = 1.0 if checked else 0.0
        self.update()

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._position = 1.0 if checked else 0.0
        self.update()

    def get_position(self) -> float:
        return self._position

    def set_position(self, pos: float) -> None:
        self._position = pos
        self.update()

    position = Property(float, get_position, set_position)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Track colors
        track_color = QColor("#2563eb") if self.isChecked() else QColor("#334155")
        if not self.isEnabled():
            track_color = QColor("#1e293b")

        # Draw rounded track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        track_rect = QRectF(0, 0, width, height)
        painter.drawRoundedRect(track_rect, height / 2.0, height / 2.0)

        # Draw thumb
        thumb_diameter = height - 4.0
        thumb_radius = thumb_diameter / 2.0

        min_x = 2.0 + thumb_radius
        max_x = width - 2.0 - thumb_radius
        thumb_x = min_x + (max_x - min_x) * self._position
        thumb_y = height / 2.0

        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(thumb_x, thumb_y), thumb_radius, thumb_radius)

        painter.end()
