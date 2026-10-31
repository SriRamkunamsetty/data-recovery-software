"""Radial circular progress ring widget with percentage and status display."""

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget


class RadialProgressRing(QWidget):
    """Circular progress indicator showing completion percentage and operation state."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._value: float = 0.0
        self._max_value: float = 100.0
        self._status_text: str = "Ready"

        self._track_color = QColor("#1e293b")
        self._progress_color = QColor("#3b82f6")
        self._text_color = QColor("#f8fafc")
        self._subtext_color = QColor("#94a3b8")

        self.setMinimumSize(180, 180)

    def set_value(self, value: float) -> None:
        """Update current progress value (0 to 100)."""
        clamped = max(0.0, min(float(value), self._max_value))
        if clamped != self._value:
            self._value = clamped
            self.update()

    def value(self) -> float:
        return self._value

    def set_status_text(self, text: str) -> None:
        """Update subtitle text under percentage."""
        if self._status_text != text:
            self._status_text = text
            self.update()

    def status_text(self) -> str:
        return self._status_text

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height)
        pen_width = max(10.0, side * 0.08)

        # Center square
        rect = QRectF(
            (width - side) / 2.0 + pen_width,
            (height - side) / 2.0 + pen_width,
            side - pen_width * 2.0,
            side - pen_width * 2.0,
        )

        # 1. Background Track
        track_pen = QPen(self._track_color, pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect, 0, 360 * 16)

        # 2. Progress Arc
        if self._value > 0.0:
            prog_pen = QPen(self._progress_color, pen_width)
            prog_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(prog_pen)

            # Arc starts at 90 degrees (top: 12 o'clock) and moves clockwise
            start_angle = 90 * 16
            span_angle = -int((self._value / self._max_value) * 360 * 16)
            painter.drawArc(rect, start_angle, span_angle)

        # 3. Text in Center
        painter.setPen(self._text_color)
        font_pct = QFont("Segoe UI", int(side * 0.16), QFont.Weight.Bold)
        painter.setFont(font_pct)

        pct_text = f"{int(self._value)}%"
        text_rect = QRectF(rect.x(), rect.y() + side * 0.18, rect.width(), side * 0.28)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, pct_text)

        # Subtitle
        painter.setPen(self._subtext_color)
        font_sub = QFont("Segoe UI", int(side * 0.065), QFont.Weight.Medium)
        painter.setFont(font_sub)
        sub_rect = QRectF(rect.x(), rect.y() + side * 0.44, rect.width(), side * 0.22)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, self._status_text)

        painter.end()
