# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir specification for RecoverX.

Requirements:
- onedir mode: preserves dynamically linked Qt libraries to comply with LGPLv3 (ADR 002 & ADR 018).
- Bundles full application dependencies and subpackages.
- Bundles application icons, manifest, and Windows PE version info.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
root_dir = Path.cwd()

# Collect all recoverx submodules and data files
hidden_imports = collect_submodules("recoverx")
hidden_imports.extend([
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shiboken6",
    "sqlite3",
    "zipfile",
    "ctypes",
    "ctypes.wintypes",
])

datas = [
    (str(root_dir / "assets" / "icon.png"), "assets"),
    (str(root_dir / "assets" / "icon.ico"), "assets"),
    (str(root_dir / "LICENSE"), "."),
    (str(root_dir / "docs" / "CAPABILITIES.md"), "docs"),
]

# Analysis
a = Analysis(
    [str(root_dir / "src" / "recoverx" / "cli.py")],
    pathex=[str(root_dir / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "notebook",
        "pytest",
        "hypothesis",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="recoverx",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX is disabled to prevent antivirus false positives and avoid PE corruption
    console=True,  # Allows CLI commands and GUI invocation
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(root_dir / "packaging" / "version_info.txt"),
    icon=str(root_dir / "packaging" / "icon.ico"),
    manifest=str(root_dir / "packaging" / "recoverx.manifest"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="recoverx",
)
