"""Donut chart widget for visualizing forensic file type distributions."""

from typing import Any, ClassVar

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import QWidget


class DonutChartWidget(QWidget):
    """Modern donut chart widget displaying distribution of recovered file categories."""

    CATEGORY_COLORS: ClassVar[dict[str, QColor]] = {
        "Images": QColor("#3b82f6"),  # Blue
        "Documents": QColor("#10b981"),  # Green
        "Videos": QColor("#8b5cf6"),  # Purple
        "Archives": QColor("#f59e0b"),  # Amber
        "Other Files": QColor("#64748b"),  # Slate
        "Others": QColor("#64748b"),
    }

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._data: dict[str, int] = {
            "Images": 842,
            "Documents": 318,
            "Videos": 145,
            "Archives": 64,
            "Other Files": 59,
        }
        self.setMinimumSize(180, 180)

    def set_data(self, data: dict[str, int]) -> None:
        """Update chart slices with category counts."""
        self._data = data
        self.update()

    def total_count(self) -> int:
        return sum(self._data.values())

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, height)

        outer_radius = side * 0.44
        inner_radius = side * 0.28
        center = QPointF(width / 2.0, height / 2.0)

        total = self.total_count()
        if total <= 0:
            # Draw empty placeholder ring
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#334155"))
            path = QPainterPath()
            path.addEllipse(center, outer_radius, outer_radius)
            hole = QPainterPath()
            hole.addEllipse(center, inner_radius, inner_radius)
            painter.drawPath(path.subtracted(hole))

            painter.setPen(QColor("#94a3b8"))
            painter.setFont(QFont("Segoe UI", int(side * 0.08), QFont.Weight.Medium))
            painter.drawText(
                QRectF(0, 0, width, height),
                Qt.AlignmentFlag.AlignCenter,
                "No Data",
            )
            painter.end()
            return

        # Draw slices
        start_angle = 90.0  # Top

        outer_rect = QRectF(
            center.x() - outer_radius,
            center.y() - outer_radius,
            outer_radius * 2.0,
            outer_radius * 2.0,
        )
        inner_rect = QRectF(
            center.x() - inner_radius,
            center.y() - inner_radius,
            inner_radius * 2.0,
            inner_radius * 2.0,
        )

        for cat, count in self._data.items():
            if count <= 0:
                continue
            span_angle = (count / total) * 360.0
            color = self.CATEGORY_COLORS.get(cat, QColor("#94a3b8"))

            path = QPainterPath()
            path.arcMoveTo(outer_rect, start_angle)
            path.arcTo(outer_rect, start_angle, -span_angle)
            path.arcTo(inner_rect, start_angle - span_angle, span_angle)
            path.closeSubpath()

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)

            start_angle -= span_angle

        # Center Text: Total Count & "Total Files"
        painter.setPen(QColor("#f8fafc"))
        font_count = QFont("Segoe UI", int(side * 0.12), QFont.Weight.Bold)
        painter.setFont(font_count)
        count_rect = QRectF(
            center.x() - inner_radius,
            center.y() - inner_radius * 0.6,
            inner_radius * 2.0,
            inner_radius * 0.7,
        )
        painter.drawText(count_rect, Qt.AlignmentFlag.AlignCenter, f"{total:,}")

        painter.setPen(QColor("#94a3b8"))
        font_sub = QFont("Segoe UI", int(side * 0.065), QFont.Weight.Medium)
        painter.setFont(font_sub)
        sub_rect = QRectF(
            center.x() - inner_radius,
            center.y() + inner_radius * 0.1,
            inner_radius * 2.0,
            inner_radius * 0.5,
        )
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "Total Files")

        painter.end()
