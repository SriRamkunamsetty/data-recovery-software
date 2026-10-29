# RecoverX

[![Platform: Windows 10/11 x64](https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011%20x64-blue.svg)](https://www.microsoft.com/windows)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![GUI: PySide6](https://img.shields.io/badge/GUI-PySide6%20(Qt%206.12)-green.svg)](https://www.qt.io/)
[![License: Owner to Decide](https://img.shields.io/badge/License-Owner%20to%20Decide-lightgrey.svg)](LICENSE)
[![Safety: 100% Offline](https://img.shields.io/badge/Safety-100%25%20Offline%20%26%20Read--Only-brightgreen.svg)](SECURITY.md)

**RecoverX** is a local-first, forensic-grade Windows 10/11 x64 desktop data recovery application engineered specifically for removable block storage media (USB flash drives, SD/microSD cards, CF cards, external HDDs) and raw disk image files.

Built strictly under non-destructive invariants, RecoverX guarantees that source media are never modified or written to, while enforcing physical disk separation to prevent accidental overwrites of existing data.

---

## Key Features

- **Strictly Read-Only Operation:** Source devices are opened exclusively in read-only mode (`GENERIC_READ`). Hardware write, format, and partition modify commands are structurally prohibited.
- **Deep Filesystem Metadata Recovery:**
  - **FAT12 / FAT16 / FAT32:** Recovers directory structures, cluster chains, and deleted directory entries (`0xE5`).
  - **exFAT:** Reconstructs full Unicode filenames up to 255 characters, timestamps, and contiguous cluster streams.
  - **NTFS:** Parses primary and backup boot sectors, Update Sequence (Fixup) arrays, resident streams, and non-resident data runs with hierarchical directory tree walking.
- **Advanced File Carving (17+ Formats):** High-speed sliding-window carver with dedicated structural and delimiter validators for:
  - *Images:* JPEG (with EXIF thumbnails), PNG, GIF, BMP, HEIC/AVIF, TIFF-based RAW (Canon CR2, Nikon NEF, Sony ARW, DNG).
  - *Documents & Archives:* PDF, ZIP, DOCX, XLSX, PPTX, 7-Zip.
  - *Audio & Video:* MP4, MOV, M4A, RIFF (WAVE, AVI), MP3.
  - *Databases:* SQLite 3.
- **Out-of-Process Preview Sandbox:** Decodes untrusted candidate files inside an isolated, killable subprocess with a 10 MiB buffer cap, 4096px downscale limit, and a 3.0s hard timeout to protect the system against crafted media exploits.
- **Multi-Pass Forensic Disk Imaging:** Implements a resilient ddrescue-style acquisition engine (Copy, Split, Retry, Scrape) to extract readable sectors from failing drives onto safe storage before analysis.
- **Strict Destination Separation:** Queries Windows IOCTLs to strictly block recovery operations targeting the source volume or physical disk.
- **Forensic Audit Reporting:** Exports interactive HTML and structured JSON reports containing device serial numbers, bad sector maps, format breakdowns, and SHA-256 hashes of all recovered files.

---

## Core Safety Rules (Never Relaxed)

1. **Read-Only Invariant:** Hardware readers never issue write commands or modifying IOCTLs.
2. **Physical Disk Separation:** Nothing RecoverX creates (recovered files, images, session databases, logs, temp files) goes on the source device or on any volume of the same physical disk.
3. **Factual Statuses Only:** No speculative percentage "recovery chances". File status is reported factually (*Metadata recovered*, *Signature matched*, *Preview validated*, *Partially readable*, *Truncated*, *Unverified*, *Recovery failed*).
4. **100% Offline & Private:** Zero network communication. No telemetry, analytics, or phone-home calls.

---

## Quick Start

### Running the Desktop GUI
```bash
recoverx gui
```

### Command-Line Interface (CLI)
```bash
# Scan a raw disk image for recoverable files
recoverx scan C:\forensics\usb_dump.raw

# Output discovered candidates as JSON
recoverx scan C:\forensics\usb_dump.raw --json

# Recover files to a safe separate destination
recoverx recover C:\forensics\usb_dump.raw D:\recovered_files --collision-policy rename

# Analyze partition tables (MBR/GPT) and lost volumes
recoverx partitions C:\forensics\usb_dump.raw

# Acquire a multi-pass forensic disk image
recoverx image \\.\PhysicalDrive1 D:\images\drive1_backup.raw
```

---

## Documentation Roadmap

| Document | Description |
| :--- | :--- |
| **[USER_GUIDE.md](USER_GUIDE.md)** | Step-by-step user manual with screenshots/ASCII workflows, CLI flags, and troubleshooting FAQ. |
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | Detailed layer breakdown (Presentation -> Application -> Domain -> Infrastructure), threading model, and IPC helper architecture. |
| **[RECOVERY_LIMITATIONS.md](RECOVERY_LIMITATIONS.md)** | Factual explanation of logical deletion vs data overwrite, SSD TRIM mechanics, encryption, and the 5-step recovery safety checklist. |
| **[SECURITY.md](SECURITY.md)** | Security threat model, sandboxed preview decoding, elevated named-pipe protocol, and vulnerability reporting policy. |
| **[BUILDING.md](BUILDING.md)** | Complete instructions to build from source, package with PyInstaller onedir, compile Inno Setup installers, and code-sign with `signtool.exe`. |
| **[TESTING.md](TESTING.md)** | Test strategy, running unit/property/integration tests, synthetic image fixtures, and offscreen headless Qt configuration. |
| **[docs/LICENSES.md](docs/LICENSES.md)** | Third-party dependency inventory and LGPLv3 dynamic linking compliance terms. |
| **[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)** | Full legal notices and license texts for Qt, PySide6, Python, Hypothesis, and other libraries. |
| **[CHANGELOG.md](CHANGELOG.md)** | Chronological history of all milestone deliverables (M1 through M13). |
| **[RELEASE_NOTES.md](RELEASE_NOTES.md)** | Release notes for RecoverX v1.0.0. |

---

## Development Setup

```powershell
# Create Python 3.12 virtual environment
uv venv --python 3.12
.venv\Scripts\activate

# Install in editable mode with development tools
uv pip install -e ".[dev]"
uv pip install pyinstaller

# Run verification checks
ruff check .
ruff format --check .
mypy src tests
pytest
```

---

## Packaging and Release

RecoverX is distributed as a standalone directory (`onedir`) to maintain dynamically linked Qt libraries under LGPLv3:

```powershell
# Build standalone onedir distribution
python packaging\build_exe.py

# Run clean-machine smoke test verification
python scripts\smoke_test_clean_machine.py --exe dist\recoverx\recoverx.exe
```

---

## License

The RecoverX root repository is currently marked **"Owner to decide"** (see [LICENSE](LICENSE) and [docs/DECISIONS.md](docs/DECISIONS.md) ADR 019). All third-party libraries retain their original open-source licenses.
