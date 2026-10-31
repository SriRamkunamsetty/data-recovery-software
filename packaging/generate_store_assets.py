"""Generate required Microsoft Store AppX / MSIX asset logos from base icon."""

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter


def generate_store_assets(base_icon_path: Path, output_assets_dir: Path) -> None:
    output_assets_dir.mkdir(parents=True, exist_ok=True)
    base_img = QImage(str(base_icon_path))
    if base_img.isNull():
        # Fallback create procedural shield
        base_img = QImage(512, 512, QImage.Format.Format_ARGB32)
        base_img.fill(QColor("#0B1120"))

    sizes = {
        "Square44x44Logo.png": (44, 44),
        "Square44x44Logo.targetsize-24_altform-unplated.png": (24, 24),
        "Square44x44Logo.targetsize-48_altform-unplated.png": (48, 48),
        "Square150x150Logo.png": (150, 150),
        "StoreLogo.png": (50, 50),
        "SplashScreen.png": (620, 300),
        "Wide310x150Logo.png": (310, 150),
    }

    for name, (w, h) in sizes.items():
        canvas = QImage(w, h, QImage.Format.Format_ARGB32)
        canvas.fill(QColor(0, 0, 0, 0))  # Transparent

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Fill background for splash
        if "Splash" in name:
            canvas.fill(QColor("#0B1120"))
            icon_dim = 120
            scaled = base_img.scaled(
                icon_dim,
                icon_dim,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawImage(x, y, scaled)
        else:
            scaled = base_img.scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (w - scaled.width()) // 2
            y = (h - scaled.height()) // 2
            painter.drawImage(x, y, scaled)

        painter.end()
        dest = output_assets_dir / name
        canvas.save(str(dest), "PNG")
        print(f"Generated Store asset: {dest.name} ({w}x{h})")


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    base_icon = project_root / "assets" / "icon.png"
    assets_dir = project_root / "packaging" / "msix_assets"
    generate_store_assets(base_icon, assets_dir)
