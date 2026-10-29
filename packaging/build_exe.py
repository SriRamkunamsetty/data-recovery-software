"""Build script for packaging RecoverX with PyInstaller in onedir mode."""

import shutil
import subprocess
import sys
from pathlib import Path


def build() -> int:
    root_dir = Path(__file__).resolve().parent.parent
    spec_path = root_dir / "packaging" / "recoverx.spec"
    dist_dir = root_dir / "dist"
    output_bundle = dist_dir / "recoverx"

    print("=== RecoverX Windows onedir Packaging ===")
    print(f"Project root: {root_dir}")
    print(f"Spec file:    {spec_path}")

    # Ensure icons exist
    icon_ico = root_dir / "packaging" / "icon.ico"
    if not icon_ico.exists():
        print("Generating application icons...")
        gen_script = root_dir / "packaging" / "generate_icon.py"
        ret = subprocess.run([sys.executable, str(gen_script)], check=True)
        if ret.returncode != 0:
            print("Failed to generate icons.")
            return 1

    # Clean previous build directories
    if output_bundle.exists():
        print(f"Cleaning previous build output: {output_bundle}")
        shutil.rmtree(output_bundle, ignore_errors=True)

    # Run PyInstaller
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(spec_path),
    ]
    print(f"Executing: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=root_dir)
    if proc.returncode != 0:
        print(f"PyInstaller build failed with exit code {proc.returncode}")
        return proc.returncode

    # Verification of onedir output
    exe_path = output_bundle / "recoverx.exe"
    if not exe_path.exists():
        print(f"FAIL: Expected executable not found at {exe_path}")
        return 1

    print(f"SUCCESS: Executable created at {exe_path}")

    # Verify LGPL compliance: dynamically linked Qt binaries must exist in the folder
    qt_core_dll = list(output_bundle.glob("**/Qt6Core.dll"))
    if not qt_core_dll:
        print(
            "WARNING: Qt6Core.dll not found in bundle. Check dynamic linking for LGPL compliance."
        )
    else:
        print(f"Verified dynamic Qt library: {qt_core_dll[0].relative_to(output_bundle)}")

    # Test running --version on the packaged executable
    print("Testing packaged executable --version...")
    test_run = subprocess.run(
        [str(exe_path), "--version"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    print(f"Output: {test_run.stdout.strip()}")
    if test_run.returncode != 0:
        print(
            f"Packaged executable failed test run (code {test_run.returncode}): {test_run.stderr}"
        )
        return 1

    print("Packaged build verification passed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(build())
