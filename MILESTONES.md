# RecoverX milestones: one prompt per coding session

How to use: start a fresh session for each milestone. Put `CLAUDE.md`, `MASTER_PROMPT.md` and `MILESTONES.md` in the repo root (create `PROGRESS.md` and `docs/DECISIONS.md` in M1). Paste the short prompt below the milestone heading. Do not start the next milestone until the current one's acceptance checks pass.

Standard opening line for every session:

> Read CLAUDE.md, PROGRESS.md and docs/DECISIONS.md, then the section of MASTER_PROMPT.md and the milestone text named below. Do only this milestone. When its acceptance checks pass, update PROGRESS.md and stop with the report format from CLAUDE.md.

The core milestones (M1 to M8) are headless with a CLI, so the engine is proven on images before any GUI or real device exists.

---

## M1: Project foundation

**Prompt:** Do Milestone M1 from MILESTONES.md.

Build: repo structure from the architecture, `pyproject.toml` with pinned dependencies, Ruff and mypy strict config, pytest config, GitHub Actions workflow (Windows plus Linux for core tests), structured logging, configuration, all domain models (including `DeviceIdentity`, `BadSectorRange`, candidate statuses as an enum), `PROGRESS.md`, `docs/DECISIONS.md`, and a stub `LICENSE` marked "owner to decide".

Acceptance: `pytest`, `ruff check`, `ruff format --check` and `mypy` all pass on Linux; domain model tests cover validation and status enums; the package imports with no Windows-only modules present; a decision log entry exists for the Python version and every dependency.

Not in scope: any device, filesystem or UI code.

## M2: Read-only storage and fixtures

**Prompt:** Do Milestone M2 from MILESTONES.md.

Build: `ReadOnlyBlockDevice` interface, `DiskImageReader` (memory-safe, bounds-checked `read_at`), `FaultInjectionReader` wrapper (configurable unreadable ranges, short reads, delays, disconnect), fixture builders for synthetic images with known files and recorded SHA-256 values, an image-hash snapshot helper.

Acceptance: safety tests prove the interface and readers expose no write API (inspect the class attributes and the open mode); out-of-range, negative and overflowing offsets and lengths raise before any I/O; image bytes and hash are unchanged after reads; fault-injection behaves as configured; Hypothesis tests on `read_at` boundaries pass.

Not in scope: filesystem parsing, carving, Windows access.

## M3: Carving engine, first formats, `recoverx scan` CLI

**Prompt:** Do Milestone M3 from MILESTONES.md.

Build: streaming carving scanner with chunk overlap, cancellation tokens, bounded memory, progress, deduplication and read-error continuation; declarative signature registry; validators for JPEG (including embedded-thumbnail handling), PNG (chunk walk and CRC), PDF, ZIP and OOXML classification; candidate statuses (Signature matched, Preview validated, Truncated); CLI command `recoverx scan IMAGE --json`.

Acceptance: images containing known files at known offsets (including across chunk boundaries and with truncated and corrupt files) produce the expected candidates, offsets and statuses; no status is "Preview validated" unless the validator walked the whole structure; memory stays bounded on a large sparse image; cancellation stops within one chunk; Hypothesis fuzzing of each validator never crashes or hangs.

Not in scope: writing recovered files, MP4 and other formats.

## M4: Destination safety and `recoverx recover`

**Prompt:** Do Milestone M4 from MILESTONES.md.

Build: destination and work-directory validator (canonical paths, reserved Windows names, trailing dots and spaces, `:`, long paths, case-insensitive collisions, symlink and junction resolution), `RecoveryDestinationWriter` (temp file then atomic replace, no-overwrite policy, SHA-256 verification), `RecoveryService`, CLI `recoverx recover`. Define a `VolumeIdentityResolver` interface with an in-memory fake for tests; the Windows implementation comes in M10.

Acceptance: recovered files match recorded hashes; collisions never overwrite; disk-full, permission-denied and disconnect simulations leave no file that looks complete; destinations and work directories on the source (using the fake resolver, same volume and same physical disk) are refused; path traversal and every reserved-name case is rejected or rewritten.

Not in scope: real Windows volume resolution, GUI.

## M5a: FAT12/16/32 metadata recovery

**Prompt:** Do Milestone M5a from MILESTONES.md.

Build: FAT parser, directory walk with cycle and limit checks, deleted-entry detection, LFN reassembly with checksum check, contiguous-chain assumption with allocation checks, mapping into candidates with factual statuses, `recoverx scan` integration (metadata first, carving optional).

Acceptance: images from independent tools (`mkfs.fat`, mtools in Linux CI) and from the fixture builder; deleted files recover with correct names, paths and hashes; overwritten clusters are detected and reported rather than recovered; corrupted boot sectors, bad cluster counts and loops are rejected safely; Hypothesis tests on malformed boot sectors and directories. Record in the capability table that FAT12/16/32 is Supported only if all of the above pass.

## M5b: exFAT metadata recovery

**Prompt:** Do Milestone M5b from MILESTONES.md.

Build: exFAT parser with entry-set checksum, allocation bitmap, NoFatChain handling, up-case table, deleted-entry recovery.

Acceptance: same standard as M5a using `mkfs.exfat` images; NoFatChain files recover with matching hashes; entry-set checksum failures are reported as damaged metadata.

## M6: Partition analysis and lost-volume recovery

**Prompt:** Do Milestone M6 from MILESTONES.md.

Build: MBR and GPT parsers (header CRC checks, backup GPT comparison), boot-sector signature scan for lost volumes, use of FAT32, exFAT and NTFS backup boot structures, in-memory-only offset mapping so metadata recovery can run on a recovered volume without writing anything.

Acceptance: images with wiped, truncated and corrupted partition tables recover the volume offset; backup structures are used only after validation; nothing is ever written; a damaged-primary and intact-backup GPT case is reported correctly.

## M7: Disk imaging

**Prompt:** Do Milestone M7 from MILESTONES.md.

Build: `DiskImagingService` with copy, trim and scrape passes, growing skip size, bounded retries and delays, persistent range-status map, sidecar metadata, machine-readable bad-sector map, flush and checkpoints, cancellation, resume with identity and settings check, SHA-256 verification, CLI `recoverx image`.

Acceptance: using the fault-injection reader, bad ranges are found to sector precision; interrupted imaging resumes correctly and produces an identical result to an uninterrupted run; resume with a mismatched identity is refused; zero-filled placeholders are never confused with genuine zeros; an acquisition with unreadable ranges is never reported complete.

## M8: Application services, persistence, workers

**Prompt:** Do Milestone M8 from MILESTONES.md.

Build: SQLite repositories with migrations and corruption handling, `SessionService`, `ScanCoordinator` (the full orchestration order), `JobManager` (no duplicate jobs on a source, no destination conflicts), cancellation, structured logging, `ReportService` (JSON and HTML export).

Acceptance: end-to-end tests on images run coordinator, metadata, carving, merge and recovery with expected hashes; deep scan never starts without an explicit request; duplicate-job and destination-conflict cases are refused; a corrupt database produces a clear recovery path; no recovered content is stored in SQLite.

## M9: Desktop UI

**Prompt:** Do Milestone M9 from MILESTONES.md.

Build: all pages and dialogs from MASTER_PROMPT section 13 over the real services (the device list may use image files as sources until M10), worker threads, light and dark themes, accessibility names, capability labels, shutdown handling.

Acceptance: pytest-qt tests (offscreen) for device selection, scan start and cancel, filtering, preview failure, destination selection, error messages and accessibility names; the window launches on Windows 10/11 and a smoke run recovers a file from a test image; nothing blocks the UI thread; demo mode is clearly marked and off by default.

## M10: Windows device access

**Prompt:** Do Milestone M10 from MILESTONES.md.

Build: `ctypes` adapters for device enumeration, `WindowsRawDeviceReader`, the elevated read-helper process and named-pipe protocol, device triage, identity record and revalidation, Windows `VolumeIdentityResolver`, hung-read cancellation.

Acceptance: unit tests with mocked Win32 responses cover access denied, sharing violation, removal, invalid handle and alignment; read-only open flags are asserted; the helper rejects out-of-range and malformed requests; a hung read is cancelled without freezing the GUI; hardware tests exist but are opt-in and documented to use disposable media only; any check that could not run on the build machine is listed with the exact reason.

## M11: Extra formats, previews and reports polish

**Prompt:** Do Milestone M11 from MILESTONES.md.

Build: second-set formats (MP4/MOV, HEIC, GIF, BMP, WAV/AVI, MP3, TIFF-based RAW, SQLite) each with its own validator and tests; sandboxed preview subprocess with limits; report improvements.

Acceptance: each new format has independent tests including truncated and corrupt cases and fuzzing; preview limits are enforced and a malformed file cannot crash or hang the GUI; the capability table is updated to match reality.

## M12: NTFS metadata recovery

**Prompt:** Do Milestone M12 from MILESTONES.md.

Build: MFT record parsing with fixups, attribute and data-run parsing with bounds checks, deleted-record detection, path reconstruction, resident and non-resident data recovery.

Acceptance: images from real tools (`mkntfs` or a Windows-formatted VHD) with known deleted files recover correctly; corrupt MFT records are handled safely; fuzzing passes. NTFS is labelled Supported only if all of this passes, otherwise Partial with the gaps listed.

## M13: Packaging, documentation and release checks

**Prompt:** Do Milestone M13 from MILESTONES.md.

Build: PyInstaller onedir spec, installer with uninstall, version info and icon, SBOM, license inventory, SHA-256 checksums, signing instructions, all documentation from MASTER_PROMPT section 19, clean-machine smoke test script, release notes.

Acceptance: build is reproducible from the documented steps; the smoke test passes on a clean Windows 10/11 x64 machine (if no such machine is available, say so and list it as an open item); documentation matches the real capability table; license and name decisions are recorded; open security and data-integrity issues are listed honestly.
