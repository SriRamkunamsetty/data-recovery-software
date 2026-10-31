"""Build Microsoft Store MSIX package using Windows SDK MakeAppx."""

import os
import shutil
import subprocess
from pathlib import Path


def find_makeappx() -> str | None:
    candidates = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe",
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe",
        r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\makeappx.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Fallback to PATH search
    which = shutil.which("makeappx.exe")
    return which


def build_msix_package(project_root: Path) -> Path | None:
    makeappx = find_makeappx()
    if not makeappx:
        print("Warning: makeappx.exe not found in Windows SDK or PATH.")
        return None

    dist_app = project_root / "dist" / "recoverx"
    if not dist_app.exists() or not (dist_app / "recoverx.exe").exists():
        print("Error: dist/recoverx not built yet. Run build_exe.py first.")
        return None

    layout_dir = project_root / "dist" / "msix_layout"
    if layout_dir.exists():
        shutil.rmtree(layout_dir)
    layout_dir.mkdir(parents=True)

    print("Populating MSIX package layout...")
    # Copy app contents
    shutil.copytree(dist_app, layout_dir, dirs_exist_ok=True)

    # Copy AppxManifest.xml
    manifest_src = project_root / "packaging" / "AppxManifest.xml"
    shutil.copy2(manifest_src, layout_dir / "AppxManifest.xml")

    # Copy Assets
    assets_src = project_root / "packaging" / "msix_assets"
    assets_dest = layout_dir / "Assets"
    shutil.copytree(assets_src, assets_dest, dirs_exist_ok=True)

    msix_output = project_root / "dist" / "RecoverX-v0.1.0-Store.msix"
    if msix_output.exists():
        msix_output.unlink()

    print(f"Packaging MSIX with {makeappx}...")
    cmd = [
        makeappx,
        "pack",
        "/d",
        str(layout_dir),
        "/p",
        str(msix_output),
        "/o",
    ]
    res = subprocess.run(cmd, check=False)
    if res.returncode == 0 and msix_output.exists():
        size_mb = msix_output.stat().st_size / (1024 * 1024)
        print(f"SUCCESS: Microsoft Store package created: {msix_output.name} ({size_mb:.2f} MB)")
        return msix_output
    else:
        print(f"Error packing MSIX, code {res.returncode}")
        return None


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    build_msix_package(root)
