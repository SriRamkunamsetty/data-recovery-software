# MASTER SPECIFICATION: RECOVERX (v2)

Read `CLAUDE.md` first. It holds the permanent safety and workflow rules. This file is the full specification. `MILESTONES.md` says which part to build in each session. Build only the milestone you are given.

## Role

Act as a senior Windows desktop engineer, digital-forensics software architect, Python engineer, storage-systems specialist, Qt UI/UX designer, test engineer and application security reviewer.

Build **RecoverX**, a Windows desktop data-recovery application for USB flash drives, SD cards, memory cards and other supported block-storage devices. Produce a coherent, runnable codebase with real implementations, tests, documentation and a repeatable Windows build. Do not produce only a tutorial, pseudocode, mockup or architecture document.

## 1. Product objective and honest scope

RecoverX is a local-first Windows application that can:

1. Discover removable storage devices and triage their condition.
2. Identify capacity, sector size, partitions and filesystems.
3. Scan without ever writing to the source.
4. Recover deleted files from filesystem metadata where the format permits.
5. Find lost or damaged partitions and filesystems using backup structures.
6. Carve files by signature when metadata is unavailable.
7. Image unstable devices with a bad-sector map, then work from the image.
8. Preview recovered files safely.
9. Recover selected files to a separate, validated destination and verify the output.
10. Export scan and recovery reports.
11. Resume scans and imaging only where saved state makes that safe.
12. Explain unsupported cases honestly.

Target: Windows 10/11 x64 first. Keep the design modular for later expansion.

### What software can and cannot do

State this in the UI, `USER_GUIDE.md` and `RECOVERY_LIMITATIONS.md`:

| Situation | Approach | Honest limit |
|---|---|---|
| Files deleted | FAT/exFAT metadata recovery, then carving | Fails if clusters were reused |
| Quick-formatted | Carving; metadata only if directories survive | Names and folders usually lost |
| RAW / "needs formatting" / lost partition | Partition recovery, backup boot structures, carving | Depends on what survived |
| Corrupted filesystem | Image first, then metadata parse, then carving | Partial results are normal |
| Bad sectors / read errors | Multi-pass imaging with a bad-sector map | Unreadable ranges stay unreadable |
| Controller failure (shows 0 bytes, wrong tiny capacity, "insert disk") | Detect and report | Software cannot fix this; recommend professional chip-level recovery |
| Encrypted (BitLocker etc.) | Detect and report | Cannot recover without the key |
| Overwritten or TRIM-erased flash | Detect where possible | Gone; do not promise otherwise |
| Fragmented files | Report as Truncated or Partially readable | No claim of reconstruction without a validated algorithm |

## 2. Technology

- Python 3.12+ (pin the exact tested version), PySide6, SQLite, pytest, pytest-qt, Hypothesis.
- Strict typing with mypy, Ruff for lint and format.
- Windows APIs through `ctypes` in a small, audited adapter. No shell-outs (PowerShell, diskpart, wmic) for device handling.
- Packaging: PyInstaller in **onedir** mode (keeps Qt replaceable under the LGPL), then an installer. GitHub Actions on Windows runners for CI.
- Pin all dependencies with hashes. Keep a written reason in `docs/DECISIONS.md` for every dependency beyond the core list.
- Performance: the carver must use `bytes.find`, compiled `re` or similar over large chunks with `memoryview`. No per-byte Python loops over device data. Keep native extensions (Rust, C++) as a later optimization, and only if a profile shows the need.

## 3. Architecture

Dependency direction is strictly downward: Presentation, then Application services, then Domain and Recovery engines, then Infrastructure. Use explicit constructor dependencies.

A. Presentation: MainWindow (sidebar: Dashboard, Devices, Recovery Sessions, Reports, Settings), DashboardPage, DeviceSelectionPage, ScanConfigurationPage, ScanProgressPage, RecoveryResultsPage, FilePreviewDialog, RecoveryDestinationDialog, RecoveryReportPage, SettingsPage.

B. Application services: DeviceDiscoveryService, DeviceTriageService, ScanCoordinator, PartitionAnalysisService, MetadataRecoveryService, CarvingRecoveryService, DiskImagingService, RecoveryService, SessionService, ReportService, JobManager.

C. Domain: StorageDevice, DeviceIdentity, PartitionInfo, FileSystemInfo, ScanJob, ScanProgress, RecoveryCandidate, RecoveryResult, SectorReadResult, BadSectorRange, RecoveryReport.

D. Infrastructure: ReadOnlyBlockDevice, WindowsRawDeviceReader, DiskImageReader, FaultInjectionReader (tests), RecoveryDestinationWriter, SQLite repositories, structured logging.

Everything works over `ReadOnlyBlockDevice`, so the same engines run on a real device or on an image. Develop and test on images first.

### Elevated read helper (design decision to implement in the Windows milestone)

Raw reads of `\\.\PhysicalDriveN` need administrator rights. Do not run the GUI elevated. Use an unelevated GUI plus a small elevated helper process:

- Launched on demand through a UAC prompt.
- Talks to the GUI over a named pipe with an ACL restricted to the current user.
- Exposes only: open-by-validated-identity, `read_at`, metadata, `close`, cancel. Nothing else.
- Validates every request (offset, length, handle ownership) before any I/O.
- Raw reads happen in this process, so a hung read can be cancelled by `CancelIoEx` or by terminating the helper, and the GUI never freezes.

Record the final design in `docs/DECISIONS.md` and `SECURITY.md`.

## 4. Read-only safety

Highest-priority constraint. See `CLAUDE.md` rules 1 to 3.

For Windows raw access:

- `CreateFileW` with read-only desired access and `OPEN_EXISTING`. Sharing flags set deliberately (normally `FILE_SHARE_READ | FILE_SHARE_WRITE`, so other processes are not blocked). Never fall back to write access.
- Validate the physical-disk number, size (`IOCTL_DISK_GET_LENGTH_INFO`) and sector size/alignment (`IOCTL_STORAGE_QUERY_PROPERTY`) before the first read.
- `read_at` hides alignment: it performs sector-aligned reads and returns exactly the requested slice.
- Validate offset and length (non-negative, within size, no overflow) before any I/O. Invalid requests never reach the OS.
- Handle access denied, sharing violations, device removal, invalid handles and timeouts with distinct, actionable errors.
- Raw functionality stays disabled when identity or safety checks fail.

State clearly in the UI and docs: a software read-only handle is not a hardware write blocker. Windows may itself write to a mounted removable volume (indexing, System Volume Information, thumbnails, autorun artifacts). Recommend a hardware write blocker for forensic use. For ordinary recovery, tell the user how to reduce that risk (for example, set the disk offline in Disk Management). RecoverX itself must never change disk, volume or registry settings.

## 5. Device discovery and triage

Use documented APIs through `ctypes`: `IOCTL_STORAGE_GET_DEVICE_NUMBER`, `IOCTL_STORAGE_QUERY_PROPERTY`, `IOCTL_DISK_GET_DRIVE_LAYOUT_EX`, `IOCTL_DISK_GET_LENGTH_INFO`, SetupAPI or CfgMgr32 for the device tree, volume enumeration for drive letters.

Show, where available: friendly name, vendor, model, bus type (USB/SD), capacity, physical disk number, logical and physical sector size, partition layout, drive letters, filesystem, removable or fixed, readability status and last I/O error.

**Identity record.** Never identify a source by drive letter alone. Build a `DeviceIdentity` from: vendor, product, serial (if present and not a known duplicate-prone value), capacity, sector size, MBR disk signature or GPT disk GUID, and a hash of sector 0. Revalidate it immediately before every scan, imaging or read session. If card readers or USB bridges give generic or duplicate identifiers, say so, lower confidence, and ask the user to confirm the physical device. If identity stays ambiguous, refuse.

**Triage.** Before scanning, classify the device and show the result with a plain explanation:

- Not detected by Windows
- Detected, no media / 0 bytes / implausible capacity (likely controller failure; recommend professional recovery, do not scan)
- Readable with I/O errors (offer imaging first, warn against repeated scans)
- Readable, partition table damaged or missing
- Readable, filesystem unrecognized or damaged
- Readable, supported filesystem present
- Encrypted volume detected (BitLocker and similar signatures)

Never initialize, mount for repair, format or modify an unrecognized disk.

## 6. Partition and lost-filesystem recovery

- Parse MBR and GPT read-only. Validate GPT header CRCs and compare with the backup header at the last LBA. Report which copy is intact.
- If tables are missing or damaged, scan for boot-sector signatures to locate lost volumes.
- Use backup structures when the primary is damaged: FAT32 backup boot sector (BPB_BkBootSec, usually sector 6), exFAT backup boot region (sectors 12 to 23), NTFS backup boot sector (last sector of the volume).
- Report findings as candidates with the evidence used. Never write a repaired table to the device. Offer to treat a candidate volume as the base offset for metadata recovery in memory only.

## 7. Filesystem metadata recovery

Stable parser interface. FAT12/16/32 first, exFAT second, NTFS last and separately tested.

For each supported filesystem:

- Validate boot-sector signature and every structural field. Validate cluster and sector sizes. Check all offsets, counts and arithmetic for overflow and bounds. Never trust on-disk sizes or pointers.
- Walk directories with cycle detection and depth and entry-count limits.
- Detect deleted entries and report allocation state as one of: deleted and cluster chain assumed, damaged metadata, unknown allocation, unrecoverable.
- Recover names and paths when metadata survives. Handle LFN and Unicode safely.

Format-specific rules to implement and test:

- **FAT12/16/32.** Deleting a file clears its FAT chain, so recovery assumes a contiguous run starting at the first cluster and sized from the directory entry. Check that those clusters are currently unallocated and not claimed by another live file, and validate content with the format validator. First character of a deleted short name is lost; mark it unknown. Reassemble LFN entries and verify the LFN checksum against the short name. Handle FAT32 high cluster word.
- **exFAT.** Parse the entry set (File, Stream Extension, File Name) and verify the entry-set checksum. Use the allocation bitmap. A file with the NoFatChain flag is contiguous and recovers well after deletion; others need the FAT chain, which may be intact. Use the up-case table for names.
- **NTFS (later milestone).** MFT record parsing with fixup validation, attribute parsing, resident and non-resident data, data runs with bounds checks, deleted-record detection, `$FILE_NAME` paths. Do not mark NTFS as supported until all of it is implemented and passes tests.

Do not claim support because a boot sector was recognized. Clearly mark incomplete capabilities in the UI and docs. Never return an empty result while claiming recovery works.

## 8. File carving

Streaming scanner over `ReadOnlyBlockDevice`:

- Configurable chunk size, correct overlap so signatures across chunk boundaries are found, cancellation checkpoints, bounded memory, progress by bytes scanned, candidate deduplication, sector and byte offsets, versioned signatures, graceful continuation after read errors.
- Declarative signature registry; each format has independent tests.
- Per-format validators that walk real structure. Do not assume an end marker exists.

Format priority:

1. **First set:** JPEG (marker walk; handle embedded EXIF thumbnails so they are not reported as separate files), PNG (chunk walk with CRC checks, IEND), PDF (header, `%%EOF` with awareness of incremental updates, xref sanity), ZIP and ZIP-based Office (end-of-central-directory, local headers; classify DOCX/XLSX/PPTX via `[Content_Types].xml`; zip-bomb limits).
2. **Second set (SD cards and cameras):** MP4/MOV (atom walk, `ftyp`, `moov`/`mdat` sizes), HEIC, GIF, BMP, WAV/AVI (RIFF length), MP3, TIFF-based RAW (CR2, NEF, ARW, DNG), SQLite.

Statuses: header only is **Signature matched**. Structure walked and complete is **Preview validated** (only when the preview actually decoded). Structure ends early is **Truncated**. Do not claim reconstruction of fragmented files unless a validated algorithm exists. Sanitize output names (see section 10). Do not execute recovered content.

## 9. Disk imaging

Separate `DiskImagingService`. The image is written to a destination validated as separate from the source.

Use a multi-pass, ddrescue-style strategy (reimplement the idea; do not copy GPL code):

1. **Copy pass.** Large aligned reads. On error, skip ahead with a growing skip size and mark the skipped range as not yet tried.
2. **Trim pass.** Return to the edges of failed regions and read inward to find the exact boundary.
3. **Scrape pass.** Read remaining untried areas sector by sector, with bounded retries and configurable delay.

Keep a persistent per-range status map: finished, not tried, not trimmed, not scraped, bad. Flash media gains little from retries and repeated reads stress a failing controller, so defaults are conservative and documented.

Also: record source identity, capacity, sector size, acquisition time and settings in a sidecar metadata file; machine-readable bad-sector map; flush and checkpoint at safe points; graceful cancellation; resume only if metadata matches the source identity and settings; distinguish zero-filled placeholders from genuine zero data (the map decides, never the content); verify length and optionally SHA-256; never claim a complete acquisition when unreadable regions exist. Never modify the source to improve results.

## 10. Recovery destination and work-directory safety

The destination must be separate from the source.

- Validate before scanning and again immediately before writing. Resolve drive letters to volume and physical-disk identity. Reject the source volume, any volume on the source physical disk, and paths that resolve into either (junctions, symlinks, subst, mapped drives).
- Apply the same check to the **work directory** (session database, logs, temp files, images).
- Canonical paths. Prevent traversal.
- Windows filename rules: reject or rewrite reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9), trailing dots and spaces, `:` (alternate data streams), invalid characters, control characters; handle paths over 260 characters (long-path support) and case-insensitive collisions.
- Never overwrite by default. Collision policy is explicit (rename, skip, ask).
- Write to a temporary file in the destination, then finalize atomically (`os.replace`).
- Handle disconnection, permission errors and disk-full with clear messages and no partial files left looking complete.
- Verify output by size and SHA-256.
- If separation cannot be established confidently, refuse and explain why. Never format or repair as a fallback.

## 11. Preview safety

Recovered files are untrusted. Previews run with strict limits (file size, pixel dimensions, decode time) and, for anything beyond simple images, in a separate low-privilege subprocess that can be killed. No embedded-content execution, no external links followed. ZIP previews list safely with zip-slip protection and entry/size limits. Start with image previews and a metadata-only view for other formats. Preview success alone sets the status; failure sets "Unverified" with the reason, never a crash.

## 12. Hybrid orchestration

`ScanCoordinator` order:

1. Validate and identify the source (identity record, revalidation).
2. Triage (section 5).
3. If read errors or instability: recommend imaging first and warn against repeated scans.
4. Analyze partitions (section 6).
5. Run metadata recovery for supported filesystems.
6. Offer carving, with a plain explanation of time and resource use. Never start a deep scan silently.
7. Merge and deduplicate without losing metadata (names, paths, timestamps).
8. Validate candidates.
9. Present findings with factual statuses and an explanation of each.
10. Recover selected files to a validated destination.

## 13. User interface

Professional, modern, restrained. Light and dark themes, consistent spacing and type, keyboard navigation, accessible names and descriptions on all controls, readable contrast, scalable text, no UI-thread blocking, no fake progress or data in production mode.

- Dashboard: start recovery, resume sessions, recent sessions, devices, safety guidance.
- Devices: real devices, identity and triage result, selection state, readability warnings, explicit confirmation of the selected device.
- Scan: quick vs deep, defensible estimates only, bytes scanned, elapsed time, current operation, last read error, cancel (and pause only where truly supported).
- Results: tree and filters, name, type, size, source offset, method, status, preview; selective recovery; export.
- Recovery wizard: destination picker, separation verification, free-space warning, collision policy, final confirmation.
- Capability labels: each filesystem and format shows Supported, Partial or Not supported, matching `RECOVERY_LIMITATIONS.md`.

All values come from real service data. A clearly marked demo mode may exist for screenshots only.

## 14. Background execution

Scans, imaging, parsing and recovery run in workers (QThread with worker objects, signals and slots only; never touch widgets from workers). Thread-safe cancellation tokens. Deterministic handle closing. No duplicate jobs on one source; no concurrent jobs sharing a destination path. Shutdown asks about active work and cleans up. Persist only what can safely resume.

## 15. Persistence and logging

SQLite with migrations and repository abstractions. Persist sessions, device identity, scan options, checkpoints, candidate metadata, outcomes, error summaries and report references. Never store recovered content in SQLite. Structured local logs; do not log file contents or sensitive filenames by default; nothing leaves the machine. Database corruption or migration failure must not affect the source and must produce a clear recovery path (back up, rebuild).

## 16. Testing

Actual tests, not placeholders.

- **Unit:** parsers, signatures, chunk overlap, filename sanitization (including Windows reserved names), bounds and overflow, destination validation, progress accounting, cancellation, image metadata, bad-sector map.
- **Property-based (Hypothesis):** parser invariants and malformed byte sequences never crash, hang or read out of bounds.
- **Integration:** synthetic FAT and exFAT images with known files and hashes; deleted entries; corrupted boot sectors; lost partition tables; truncated images; fault-injection reader for unreadable sectors; interrupted imaging and resume; output collisions; disk-full simulation.
- **Independent validation.** Do not rely only on images produced by your own fixture writer, because the parser and writer could share the same mistake. Also test against images made by real tools (`mkfs.fat` and `mkfs.exfat` on Linux CI, Windows `format` on a VHD) and public forensic test images (for example NIST CFReDS and Digital Corpora) with their licenses recorded. The Sleuth Kit may be used as a dev-time comparison oracle only, never bundled.
- **Safety:** source abstraction exposes no write API; source bytes and hashes unchanged after image-backed runs; same-volume and same-physical-disk destinations refused; ambiguous identity refused; invalid offsets never reach the raw reader; unplugged device fails safely; work directory on the source refused.
- **UI (pytest-qt, offscreen):** device selection, scan start and cancel, filtering, preview failures, destination selection, error messages, accessibility names.
- Hardware tests use disposable media only, are opt-in, and are never run automatically.

## 17. Security

Validate every binary input. Strict resource limits (depth, counts, sizes, time). No unsafe deserialization (no `pickle`). No shell execution for device handling. No plugin loading from untrusted directories. Secure temp files. Catch expected I/O failures with actionable messages. No network use in core recovery. No stealth, collection or exfiltration. Document limits for encryption, overwritten data and physical failure.

## 18. Packaging and licensing

- PyInstaller onedir plus installer with uninstall support. Version info and icon.
- Unsigned PyInstaller executables that open raw disks are often flagged by SmartScreen or antivirus. Plan for Authenticode signing and document how, and note this in `BUILDING.md`.
- SHA-256 checksums, SBOM, third-party license inventory, release notes, versioned artifacts.
- PySide6 is LGPL: keep it dynamically linked and replaceable (onedir), include required notices.
- Record the application's own license in `docs/DECISIONS.md`. The owner chooses it; until then use a placeholder `LICENSE` marked "owner to decide" and do not ship a release.
- Check that the name "RecoverX" does not collide with an existing product before release and record the result.
- Do not bundle third-party recovery executables or copied code.
- Test the packaged build on a clean Windows 10/11 x64 machine and document which operations need administrator rights.

## 19. Documentation

README.md, ARCHITECTURE.md, SECURITY.md, TESTING.md, BUILDING.md, USER_GUIDE.md, RECOVERY_LIMITATIONS.md, THIRD_PARTY_NOTICES.md, LICENSE, CHANGELOG.md, plus `PROGRESS.md` and `docs/DECISIONS.md`.

Document supported filesystems and formats precisely (Supported / Partial / Not supported). Explain logical corruption vs overwritten data vs encryption vs physical failure. Include a recovery safety checklist (stop using the device, do not format, do not run repeated scans on a failing device, image first, recover to a different drive) and recommend professional recovery for physically failing devices.

## 20. Workflow

Work in the milestones listed in `MILESTONES.md`, one per session, vertical slice first: headless core and CLI before the GUI.

After each milestone: list files changed, run the real checks, report results honestly, state what is incomplete, fix regressions, update docs, `PROGRESS.md` and `DECISIONS.md`. Never mark a feature complete because its interface exists.

## 21. Definition of done (advanced beta)

- Launches on a clean Windows 10/11 x64 system.
- UI uses real application services.
- Supported synthetic and real-tool images scan and recover correctly with matching hashes.
- Read-only and destination-safety tests pass.
- Cancellation and error handling work, including a hung read.
- Packaged build and smoke test pass.
- Documentation states actual capabilities and limits.
- Dependencies and licenses reviewed; license and name decisions recorded.
- No critical security or data-integrity issue open.

If something cannot be built or validated in the current environment, say so, explain the blocker, and give the exact next step. Do not fabricate completed features, test results, device detections or recovery statistics.
