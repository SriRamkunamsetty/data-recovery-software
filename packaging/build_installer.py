"""Automated build script for RecoverX standalone Windows installer & portable zip."""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


def create_portable_zip(dist_dir: Path, output_zip: Path) -> None:
    """Pack dist/recoverx into a high-compression zip file."""
    print(f"Compressing {dist_dir} into {output_zip}...")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for file_path in dist_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(dist_dir)
                zf.write(file_path, arcname=str(rel_path))
    size_mb = output_zip.stat().st_size / (1024 * 1024)
    print(f"Portable zip created successfully: {output_zip.name} ({size_mb:.2f} MB)")


def build_installer_exe(project_root: Path, payload_zip: Path) -> Path:
    """Build single-file Windows setup executable embedding the payload zip."""
    print("Building standalone RecoverX-Setup-v0.1.0.exe installer with PyInstaller...")
    icon_path = project_root / "assets" / "icon.ico"
    wizard_script = project_root / "packaging" / "installer_wizard.py"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name=RecoverX-Setup-v0.1.0",
        f"--icon={icon_path}",
        f"--add-data={payload_zip};.",
        str(wizard_script),
    ]

    subprocess.run(cmd, cwd=str(project_root), check=True)
    setup_exe = project_root / "dist" / "RecoverX-Setup-v0.1.0.exe"
    if setup_exe.exists():
        size_mb = setup_exe.stat().st_size / (1024 * 1024)
        print(f"Installer executable created successfully: {setup_exe.name} ({size_mb:.2f} MB)")
    return setup_exe


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    dist_dir = project_root / "dist" / "recoverx"
    if not dist_dir.exists() or not (dist_dir / "recoverx.exe").exists():
        print(f"Error: {dist_dir} does not exist. Run packaging/build_exe.py first.")
        return 1

    portable_zip = project_root / "dist" / "RecoverX-v0.1.0-Windows-x64.zip"
    create_portable_zip(dist_dir, portable_zip)

    # Copy as payload for installer embedding
    payload_zip = project_root / "packaging" / "payload.zip"
    shutil.copy2(portable_zip, payload_zip)

    # Build Setup EXE
    setup_exe = build_installer_exe(project_root, payload_zip)

    # Clean up payload temp file
    if payload_zip.exists():
        payload_zip.unlink()

    print("\n=== All Installation Packages Built Successfully ===")
    print(f"1. Standalone App Directory: {dist_dir}")
    print(f"2. Portable Zip Package:     {portable_zip}")
    print(f"3. Production Windows Setup: {setup_exe}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
