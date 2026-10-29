# Building RecoverX from Source

This guide covers building RecoverX from source, generating the PyInstaller `onedir` distribution, compiling the Windows installer with Inno Setup, and performing Authenticode signing.

---

## 1. Prerequisites

- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Python:** Python 3.12 (specifically tested against CPython 3.12.13).
- **Package Manager:** `uv` (recommended) or standard `pip`.
- **Packaging Tools:**
  - `pyinstaller` (version 6.22+)
  - [Inno Setup 6](https://jrsoftware.org/isinfo.php) (for installer generation)
  - Windows 10/11 SDK (for `signtool.exe` Authenticode code-signing)

---

## 2. Environment Setup

```powershell
# Clone the repository
git clone https://github.com/SriRamkunamsetty/data-recovery-software.git
cd data-recovery-software

# Create and activate Python 3.12 virtual environment
uv venv --python 3.12
.venv\Scripts\activate

# Install dependencies in editable mode with development tools
uv pip install -e ".[dev]"
uv pip install pyinstaller
```

---

## 3. Code Verification

Before building the binaries, verify that all static checks and tests pass:

```powershell
# Fast linting and format verification
ruff check .
ruff format --check .

# Strict type checking (190+ source files, 0 errors)
mypy src tests

# Execute complete test suite (300+ tests)
pytest
```

---

## 4. Building the Standalone `onedir` Distribution

Run the build script to generate the unpackaged standalone distribution in `dist\recoverx`:

```powershell
python packaging\build_exe.py
```

**Build Output:**
- Application Directory: `dist\recoverx\`
- Main Binary: `dist\recoverx\recoverx.exe`
- Dynamically Linked Qt Libraries: `dist\recoverx\_internal\PySide6\Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll` (satisfying LGPLv3 user replaceability).

Verify the standalone executable:
```powershell
.\dist\recoverx\recoverx.exe --version
.\dist\recoverx\recoverx.exe --help
```

---

## 5. Compiling the Windows Installer (Inno Setup)

Compile the Inno Setup script to create `dist\installer\recoverx-setup-1.0.0-windows-x64.exe`:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" packaging\installer.iss
```

The installer includes:
- 64-bit architecture enforcement (`x64compatible`).
- Desktop and Start Menu shortcuts.
- Clean uninstaller (`UninstallDisplayName` and registry entries).
- Dynamic Qt libraries kept intact.

---

## 6. Authenticode Code Signing

> [!IMPORTANT]
> Unsigned binaries opening raw physical devices (`\\.\PhysicalDriveX`) trigger aggressive Windows SmartScreen and antivirus heuristic warnings.
> Production releases must be signed with an EV or OV Authenticode certificate using `signtool.exe`.

```powershell
# Sign all binaries in dist\recoverx
$SignTool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"

Get-ChildItem -Path "dist\recoverx" -Include *.exe, *.dll, *.pyd -Recurse | ForEach-Object {
    & $SignTool sign /fd SHA256 `
        /tr "http://timestamp.digicert.com" `
        /td SHA256 `
        /d "RecoverX Data Recovery" `
        /sha1 "<YOUR_CERT_THUMBPRINT>" `
        $_.FullName
}

# Sign the setup installer
& $SignTool sign /fd SHA256 `
    /tr "http://timestamp.digicert.com" `
    /td SHA256 `
    /d "RecoverX Setup" `
    /sha1 "<YOUR_CERT_THUMBPRINT>" `
    "dist\installer\recoverx-setup-1.0.0-windows-x64.exe"
```

See [packaging/SIGNING.md](packaging/SIGNING.md) for full details on certificate management and false-positive handling.

---

## 7. Clean-Machine Smoke Test Verification

Execute the automated clean-machine smoke test to verify binary integrity:

```powershell
# Run smoke test on the compiled standalone binary
python scripts\smoke_test_clean_machine.py --exe dist\recoverx\recoverx.exe
```
