"""Generate high-resolution RecoverX application icon (.ico and .png).

Contains sizes: 256x256, 128x128, 64x64, 48x48, 32x32, 16x16.
Uses PySide6 QPainter with anti-aliasing to render a clean forensic recovery emblem.
"""

import os
import struct
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)


def render_icon(size: int) -> bytes:
    """Render a crisp icon at the requested pixel resolution, returning PNG bytes."""
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    scale = size / 256.0

    # Background badge: Rounded square / Shield plate
    pad = 8.0 * scale
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    radius = 36.0 * scale

    bg_grad = QLinearGradient(0, 0, size, size)
    bg_grad.setColorAt(0.0, QColor("#0F172A"))  # Deep slate navy
    bg_grad.setColorAt(1.0, QColor("#1E293B"))  # Midnight blue

    bg_pen = QPen(QColor("#0EA5E9"), 6.0 * scale)  # Cyan outline
    painter.setPen(bg_pen)
    painter.setBrush(QBrush(bg_grad))
    painter.drawRoundedRect(rect, radius, radius)

    # Stylized Data Recovery Circular Arc (3/4 circle with arrow)
    center = QPointF(size / 2.0, size / 2.0)
    arc_radius = 68.0 * scale
    arc_pen = QPen(QColor("#38BDF8"), 12.0 * scale)
    arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(arc_pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    arc_path = QPainterPath()
    arc_rect = QRectF(
        center.x() - arc_radius,
        center.y() - arc_radius,
        2 * arc_radius,
        2 * arc_radius,
    )
    # Draw arc from 45 deg to 315 deg (270 deg span)
    arc_path.arcMoveTo(arc_rect, 45)
    arc_path.arcTo(arc_rect, 45, 270)
    painter.drawPath(arc_path)

    # Arrow head at the end of the arc
    arrow_pen = QPen(QColor("#38BDF8"), 4.0 * scale)
    painter.setPen(arrow_pen)
    painter.setBrush(QBrush(QColor("#38BDF8")))
    arrow_path = QPainterPath()
    # At top-right (~45 deg)
    ax = center.x() + arc_radius * 0.7071
    ay = center.y() - arc_radius * 0.7071
    arrow_path.moveTo(ax - 4.0 * scale, ay - 14.0 * scale)
    arrow_path.lineTo(ax + 14.0 * scale, ay - 2.0 * scale)
    arrow_path.lineTo(ax - 2.0 * scale, ay + 14.0 * scale)
    arrow_path.closeSubpath()
    painter.drawPath(arrow_path)

    # Center text: "RX"
    if size >= 32:
        painter.setPen(QColor("#F8FAFC"))
        font = QFont("Segoe UI", int(58 * scale), QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.0 * scale)
        painter.setFont(font)
        text_rect = QRectF(0, size * 0.22, size, size * 0.56)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignCenter,
            "RX",
        )

    painter.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")  # type: ignore[call-overload]
    return bytes(buf.data().data())


def build_ico(png_streams: list[tuple[int, bytes]], output_ico_path: Path) -> None:
    """Pack multiple PNG streams into a standard Windows .ico file."""
    # ICONDIR: 2 bytes reserved (0), 2 bytes type (1=ICO), 2 bytes count (N)
    header = struct.pack("<HHH", 0, 1, len(png_streams))
    entries = []
    offset = 6 + len(png_streams) * 16

    for size, data in png_streams:
        w = size if size < 256 else 0
        h = size if size < 256 else 0
        # ICONDIRENTRY: width, height, colors, reserved, planes, bpp, bytes_in_res, image_offset
        entry = struct.pack(
            "<BBBBHHII",
            w,
            h,
            0,  # 256+ colors
            0,  # Reserved
            1,  # Color planes
            32,  # Bit depth
            len(data),
            offset,
        )
        entries.append(entry)
        offset += len(data)

    output_ico_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_ico_path, "wb") as f:
        f.write(header)
        for entry in entries:
            f.write(entry)
        for _, data in png_streams:
            f.write(data)


def main() -> None:
    _ = QGuiApplication.instance() or QGuiApplication(sys.argv)
    sizes = [256, 128, 64, 48, 32, 16]
    png_streams: list[tuple[int, bytes]] = []

    for s in sizes:
        png_data = render_icon(s)
        png_streams.append((s, png_data))

    # Save 256x256 PNG
    assets_dir = Path("assets")
    assets_dir.mkdir(parents=True, exist_ok=True)
    packaging_dir = Path("packaging")
    packaging_dir.mkdir(parents=True, exist_ok=True)

    with open(assets_dir / "icon.png", "wb") as f:
        f.write(png_streams[0][1])  # 256x256 PNG

    # Save .ico in assets and packaging
    build_ico(png_streams, assets_dir / "icon.ico")
    build_ico(png_streams, packaging_dir / "icon.ico")
    print(f"Generated icons in {assets_dir} and {packaging_dir}")


if __name__ == "__main__":
    main()
