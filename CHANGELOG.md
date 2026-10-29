# Changelog

All notable changes to RecoverX are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-10-29

### Added
- **M13: Packaging, Documentation and Release System:**
  - Standalone PyInstaller `onedir` distribution maintaining dynamically linked Qt libraries to comply with LGPLv3 (ADR 018).
  - Multi-resolution Windows application icon (`assets/icon.ico`) with 256, 128, 64, 48, 32, 16 pixel frames.
  - Windows PE version resource (`packaging/version_info.txt`) and manifest (`packaging/recoverx.manifest`) declaring PerMonitorV2 high-DPI awareness and least-privilege `asInvoker` security.
  - Inno Setup 6 installer script (`packaging/installer.iss`) with 64-bit architecture enforcement, clean uninstaller, and Start Menu / Desktop shortcuts.
  - Machine-readable SPDX 2.3 Software Bill of Materials (`docs/SBOM.json`) and comprehensive third-party license inventory (`docs/LICENSES.md`, `THIRD_PARTY_NOTICES.md`).
  - Automated release checksum generator (`packaging/generate_checksums.py`) creating `SHA256SUMS.txt`.
  - Windows Authenticode code signing guide (`packaging/SIGNING.md`) with instructions for `signtool.exe`, timestamping, and SmartScreen reputation management.
  - Automated clean-machine smoke test script (`scripts/smoke_test_clean_machine.py`, `scripts/smoke_test_clean_machine.ps1`) verifying CLI, GUI offscreen, preview sandboxing, destination safety, and end-to-end carving.
  - Comprehensive documentation suite: `ARCHITECTURE.md`, `SECURITY.md`, `TESTING.md`, `BUILDING.md`, `USER_GUIDE.md`, `RECOVERY_LIMITATIONS.md`, `RELEASE_NOTES.md`.
  - ADR 018 (Packaging Architecture) and ADR 019 (Trademark Collision Analysis & License Status) in `docs/DECISIONS.md`.

- **M12: NTFS Filesystem Metadata Recovery:**
  - Primary and backup boot sector parsing with OEM ID `NTFS    ` validation and negative power-of-two MFT record sizes.
  - In-memory Update Sequence (Fixup) array validation and application, rejecting torn writes and `BAAD` signatures without modifying the source medium.
  - Bounds-checked parsing for `$STANDARD_INFORMATION`, `$FILE_NAME`, `$DATA`, `$VOLUME_NAME`, and `$BITMAP` attributes.
  - Variable-length non-resident data-run decoding supporting signed relative cluster deltas.
  - Deleted MFT record detection (`flags & 0x0001 == 0`) and Allocation Bitmap ($Bitmap) allocation cross-verification.
  - Hierarchical directory path reconstruction up to Root Record 5 with cycle detection.
  - In-memory block device abstraction (`MemoryBlockDevice`).

- **M11: Extra File Carving Formats & Isolated Preview Sandbox:**
  - Second-set carving validators: MP4/MOV/M4A, HEIC/AVIF, GIF, BMP, RIFF (WAV/AVI), MP3, TIFF/RAW (CR2, NEF, ARW, DNG), and SQLite 3.
  - Sandboxed preview executor (`PreviewSandbox`) spawning an isolated, killable subprocess with a 10 MiB buffer limit, 4096px downscaling, and a 3.0s hard execution timeout.
  - Rich preview dialog cards displaying EXIF metadata, video dimensions, audio specs, SQLite table schemas, and formatted hex samples.
  - Detailed format breakdown and limitations tables in forensic HTML/JSON reports.

- **M10: Windows Native Physical Device Access & Separation:**
  - Audited `ctypes` Win32 bindings for device enumeration (`IOCTL_STORAGE_QUERY_PROPERTY`, `IOCTL_DISK_GET_DRIVE_GEOMETRY_EX`).
  - Elevated read helper service (`ElevatedReadHelperService`) providing read-only disk handles over a secure local named pipe with UAC elevation.
  - `WindowsVolumeIdentityResolver` resolving physical disk numbers and partition extents to enforce strict destination separation.
  - Hung-read cancellation and media removal detection via sector0 hash revalidation.

- **M9: Desktop Graphical User Interface (PySide6):**
  - High-DPI, dark-mode desktop GUI with navigation sidebar: Dashboard, Devices, Scan Progress, Recovery Results, Reports, Settings.
  - Multi-threaded asynchronous workers (`ScanWorker`, `ImagingWorker`, `RecoveryWorker`) running on dedicated `QThread` instances.

- **M8: Forensic Disk Imaging Service:**
  - Multi-pass ddrescue-style acquisition engine (Phase 1 Copy, Phase 2 Split, Phase 3 Retry, Phase 4 Scrape).
  - Bit-precise bad sector tracking and SHA-256 destination hash verification.

- **M7: Partition Analysis & Lost Volume Detection:**
  - MBR and GPT partition table parsers with bounds and overlap validation.
  - `LostVolumeScanner` identifying unpartitioned or orphaned volume boot sectors.

- **M6: exFAT Filesystem Metadata Recovery:**
  - VBR parsing with boot checksum verification.
  - Stream Extension directory entry parsing and Allocation Bitmap cross-checking.

- **M5: FAT12 / FAT16 / FAT32 Filesystem Recovery:**
  - BPB and extended BPB parsing, FAT cluster chain following, and deleted directory entry (`0xE5`) recovery.

- **M4: Destination Safety & Atomic Destination Writer:**
  - Windows reserved filename sanitization (`CON`, `PRN`, `AUX`, `NUL`, etc.) and path traversal (`../`) neutralization.
  - Atomic two-stage writing (`.tmp` write followed by `os.replace`) with SHA-256 verification.

- **M3: Core File Carving Engine:**
  - Chunked carving scanner with sliding overlap buffers.
  - Initial format validators for JPEG, PNG, PDF, ZIP, and 7-Zip.

- **M2: Read-Only Storage Abstractions & Synthetic Test Harness:**
  - `ReadOnlyBlockDevice`, `DiskImageReader`, `FaultInjectionReader`.
  - Synthetic test fixtures (`SyntheticImageBuilder`, `SyntheticFatBuilder`).

- **M1: Project Foundation & Architecture:**
  - Core domain models, logging, error hierarchies, configuration management, strict mypy typing, and ruff linting.
