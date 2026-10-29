# Architecture Decision Records (ADRs)

This document tracks all key technical, architectural, tooling, and dependency decisions made in the RecoverX project.

---

## ADR 001: Python Runtime Version Pinning

* **Status:** Accepted
* **Context:** RecoverX needs modern Python typing features, performance improvements in binary handling, and long-term stability across Windows and Linux test environments.
* **Decision:** Target Python 3.12 (specifically tested against CPython 3.12.13). We configure `requires-python = ">=3.12"` with strict testing under 3.12.
* **Rationale:** Python 3.12 introduces faster comprehension execution, improved error locations, native support for type parameter syntax (PEP 695), and broad, stable binary wheel availability for PySide6 and testing tooling.
* **Consequences:** Codebase can freely use Python 3.12 typing and standard library features while remaining strictly typed.

---

## ADR 002: Dependency Selection and Rationale

* **Status:** Accepted
* **Context:** CLAUDE.md and MASTER_PROMPT.md require every external dependency beyond standard library to have an explicit justification and verified license. RecoverX prioritizes safety, auditable code, and minimal attack surface.
* **Core Dependencies:**
  1. **`PySide6`**:
     * *Purpose:* Official Qt for Python bindings for the desktop GUI.
     * *License:* LGPLv3 / Commercial.
     * *Rationale:* PySide6 provides cross-platform desktop UI capabilities, high-DPI scaling, dark/light theme support, and native widget performance. To comply with LGPLv3, the application will be distributed in PyInstaller `onedir` mode with dynamic linking, allowing users to swap Qt libraries if desired.
  2. **`pytest`**:
     * *Purpose:* Test execution and test runner.
     * *License:* MIT.
     * *Rationale:* Industry standard Python test framework offering rich assertion reporting, fixture management, and modular test organization.
  3. **`pytest-qt`**:
     * *Purpose:* Qt fixture and headless testing helper for pytest.
     * *License:* MIT.
     * *Rationale:* Enables testing PySide6 signals, slots, and dialogs offscreen (`QT_QPA_PLATFORM=offscreen`) without requiring a live desktop display, ensuring continuous integration runs cleanly on headless CI.
  4. **`Hypothesis`**:
     * *Purpose:* Property-based testing framework.
     * *License:* MPLv2.
     * *Rationale:* Essential for testing binary parsers (MBR, GPT, FAT, exFAT, NTFS, file carvers) against malformed, adversarial, and truncated byte inputs to guarantee that parsers never crash or enter infinite loops.
  5. **`ruff`**:
     * *Purpose:* Fast linter and code formatter.
     * *License:* MIT / Apache-2.0.
     * *Rationale:* Replaces Flake8, Black, and isort with sub-second execution speeds, enforcing consistent code quality and formatting.
  6. **`mypy`**:
     * *Purpose:* Static type checker running in strict mode.
     * *License:* MIT.
     * *Rationale:* Enforces complete type safety across all domain models, services, and hardware abstractions, preventing runtime `None` dereferences, type confusion, or unhandled states.
  7. **`hatchling`**:
     * *Purpose:* Modern build backend conforming to PEP 517 / PEP 621.
     * *License:* MIT.
     * *Rationale:* Lightweight, standard-compliant build tool that builds clean wheels and editable packages (`uv pip install -e .`) without legacy setuptools bloat.
* **Dependencies Rejected or Deferred:**
  * *`pydantic`*: Rejected for domain models to avoid runtime overhead and serialization complexities; Python standard library `@dataclass(frozen=True)` with custom `__post_init__` checks provides zero-overhead, strictly typed data structures.
  * *`GPL recovery libraries (TestDisk, PhotoRec, ddrescue, Sleuth Kit)`*: Forbidden from being bundled or copied; all formats and algorithms are reimplemented independently from official specifications.

---

## ADR 003: Elevated Read Helper for Windows Raw Disk Access

* **Status:** Accepted (to be implemented in M10)
* **Context:** Accessing raw disk handles (`\\.\PhysicalDriveN`) requires elevated (Administrator) rights on Windows. Running the entire Qt GUI as Administrator creates severe security risks and drags untrusted recovered data into high integrity.
* **Decision:** The GUI process runs unelevated (standard user). When raw device access is required, a lightweight elevated helper process is spawned via UAC, communicating with the GUI over an authenticated Named Pipe with a strict user-only ACL.
* **Rationale:** A hung read on a damaged drive can be cancelled without freezing the GUI. The helper implements only a minimal, audited API: `open`, `read_at`, `get_metadata`, `close`, `cancel`.

---

## ADR 004: Factual Candidate Statuses (No Percentage Guarantees)

* **Status:** Accepted
* **Context:** Commercial data recovery software frequently misleads users with arbitrary percentage estimates (e.g., "95% chance of recovery") that have no mathematical or forensic basis.
* **Decision:** RecoverX strictly uses factual status enums:
  * `Metadata recovered`: Found through intact directory/filesystem tables.
  * `Signature matched`: File header signature detected, but internal structure is not yet verified.
  * `Preview validated`: Complete file structure successfully decoded by format validator or preview generator.
  * `Partially readable`: File contains unreadable sectors or bad blocks.
  * `Truncated`: File structure ends prematurely before the expected end marker.
  * `Unverified`: Recovered without formal validator check.
  * `Recovery failed`: Output could not be written or read failed completely.
* **Rationale:** Preserves forensic integrity and sets transparent user expectations.

---

## ADR 005: Project Licensing Placeholder

* **Status:** Pending Owner Selection
* **Context:** A formal software license must be chosen by the project repository owner prior to release.
* **Decision:** Marked as "Owner to decide" in `LICENSE`. Third-party notices and LGPL compliance requirements are documented.

---

## ADR 006: Read-Only Storage Abstraction and Fault Injection

* **Status:** Accepted
* **Context:** CLAUDE.md Rule 1 mandates that the source block device is strictly read-only by construction. The core recovery engines (carving, partition analysis, metadata parsing, disk imaging) must run identically over physical block devices and synthetic disk images without knowing the underlying medium. Robustness against hardware read failures, degraded sectors, and unexpected disconnections must be verifiable in tests.
* **Decision:**
  1. Define `ReadOnlyBlockDevice` abstract base class exposing strictly: `identity`, `device_info`, `size_bytes`, `logical_sector_size`, `read_at(offset, length)`, `close()`, and context manager support. No write, format, erase, or truncate methods exist.
  2. Implement `DiskImageReader` opening images strictly with mode `"rb"`, asserting `handle.writable() is False`.
  3. Implement `FaultInjectionReader` as a decorator around any `ReadOnlyBlockDevice`, capable of simulating unreadable bad sector ranges (`DeviceReadError`), short reads, latency/delays, and unexpected disconnections (`DeviceDisconnectedError`).
  4. Implement `SyntheticImageBuilder` and `ImageHashSnapshot` to generate test disk images with known payloads and cryptographically prove that image bytes and hashes are 100% immutable across all read operations.
* **Rationale:** Provides complete separation between storage I/O and recovery engines, enforces compile-time and runtime read-only safety, and provides deterministic testing of failing media scenarios.

---

## ADR 007: Streaming File Carving and Structural Validation Architecture

* **Status:** Accepted
* **Context:** When filesystems are quick-formatted or corrupted, file carving must locate files by binary signature and structure without relying on directory metadata. Carving must process arbitrary disk capacities with strictly bounded memory, operate across chunk boundaries without missing cross-boundary headers, deduplicate embedded objects (e.g., EXIF thumbnails inside JPEGs), continue gracefully across bad sectors, and enforce that no file is assigned `Preview validated` status unless its internal structure was fully walked and verified.
* **Decision:**
  1. Implement `CarvingScanner` with sliding window chunking (`chunk_size` + `overlap`). Scans use fast `bytes.find` across chunk buffers in memory with bounds checks.
  2. Implement `CancellationToken` checked per chunk, ensuring prompt cancellation without blocking.
  3. Implement declarative `SignatureRegistry` and per-format validators for first-set formats:
     - `JpegValidator`: Walks markers (SOI, DQT, SOF, DHT, SOS, EOI), entropy scan, and parses APP1 EXIF segment lengths to skip inner embedded thumbnails and prevent false candidate duplication.
     - `PngValidator`: Walks chunks from `IHDR` to `IEND`, verifying CRC-32 on every chunk.
     - `PdfValidator`: Scans for startxref, xref/trailer, and final `%%EOF`, accounting for incremental updates.
     - `ZipValidator`: Locates and parses EOCD, traverses Central Directory records, checks zip-bomb ceilings (ratio and entry counts), and classifies OOXML files (`.docx`, `.xlsx`, `.pptx`) via `[Content_Types].xml`.
  4. Only files where the complete structure decodes cleanly receive `CandidateStatus.PREVIEW_VALIDATED`. Truncated or corrupt streams receive `CandidateStatus.TRUNCATED` or `CandidateStatus.SIGNATURE_MATCHED`.
  5. Provide CLI `recoverx scan IMAGE [--json]` for headless command-line execution and automated integration.
* **Rationale:** Maximizes forensic accuracy, prevents false recovery claims, handles large storage media in bounded memory, and ensures embedded thumbnails and corrupt chunks are correctly handled.

---

## ADR 008: Destination Safety, Path Sanitization, and Atomic File Writing

* **Status:** Accepted
* **Context:** Recovering deleted data requires non-negotiable guarantees that writing output will never contaminate, overwrite, or corrupt the source storage device. Furthermore, recovered filenames originating from corrupted media or foreign filesystems may contain path traversal sequences (`../../`), Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`), Alternate Data Streams (`:`), or invalid trailing characters. Interruptions (disk-full, permission errors, sudden disconnect) must never leave partial files that look complete.
* **Decision:**
  1. Implement `VolumeIdentityResolver` interface and `FakeVolumeIdentityResolver` to establish physical disk and volume boundaries. Any destination or work directory sharing the same volume or physical disk as the source device is unconditionally refused (`DestinationOnSourceError`). Ambiguous identities are similarly refused (`AmbiguousSeparationError`).
  2. Implement `sanitize_filename` and `sanitize_relative_path` neutralizing path traversal sequences, rewriting reserved Windows names (e.g., `CON.txt` -> `_CON.txt`), stripping trailing dots/spaces, and removing illegal characters and `:` alternate streams.
  3. Enforce a strict no-overwrite policy: `resolve_collision` handles case-insensitive name collisions (e.g., `file (1).ext`) without clobbering existing user files.
  4. Implement `RecoveryDestinationWriter` staging output via `.recoverx_tmp_*.part` files with `fsync()`, verifying computed SHA-256 against expected candidate hashes, unlinking staging files on any error (so no partial file remains), and atomically finalizing via `os.replace`.
  5. Provide CLI command `recoverx recover IMAGE DESTINATION [--json] [--collision-policy rename|skip|never_overwrite]`.
* **Rationale:** Satisfies CLAUDE.md Rules 2, 3, and 4; prevents data loss; ensures atomic and forensically verified recovery outputs.

---

## ADR 009: FAT12/16/32 Filesystem Metadata Recovery, LFN Reassembly, and Allocation Verification

* **Status:** Accepted
* **Context:** Files deleted from FAT filesystems have their FAT allocation chains zeroed by operating systems, but their directory entries (including LFN parts) survive marked with `0xE5`. Recovering deleted files from FAT requires reading BIOS Parameter Blocks (BPB), traversing root and subdirectories safely with cycle detection, reassembling Long File Names with short-name checksum validation, evaluating contiguous cluster allocation against the FAT table, and verifying file integrity with structural format validators.
* **Decision:**
  1. Determine FAT type strictly by Microsoft cluster count specification (`CountofClusters < 4085` -> FAT12, `< 65525` -> FAT16, `>= 65525` -> FAT32), never trusting OEM strings or `BS_FilSysType`.
  2. Implement automatic fallback to backup boot sector (sector 6 on FAT32) when primary sector 0 has corrupted signatures.
  3. Reassemble LFN entries preceding deleted short entries by matching the 8-bit checksum against candidate original characters. Mark lost first character of short names as `_` when LFN is unavailable.
  4. Assume contiguous cluster allocation starting at `DIR_FstClusLO/HI` for deleted files. Validate every cluster in the run against the FAT table. If any cluster is non-zero (allocated/bad), classify as `CandidateStatus.OVERWRITTEN` and do not claim recovery or compute false hashes.
  5. Run structural format validators on unallocated cluster runs, conferring `CandidateStatus.PREVIEW_VALIDATED` only when the complete structure decodes cleanly.
  6. Enforce depth limits (64) and cycle detection via visited cluster sets to prevent infinite loops on corrupted directories.
* **Rationale:** Satisfies CLAUDE.md Rules 1, 4, 7 and Milestone M5a acceptance criteria.

---

## ADR 010: exFAT Metadata Recovery, Entry-Set Checksum, and Allocation Bitmap Verification

* **Status:** Accepted
* **Context:** exFAT structures directories as sets of 32-byte records (File, Stream Extension, and 1+ File Name entries) protected by a 16-bit set checksum. Stream Extension entries feature a `NoFatChain` flag denoting contiguous cluster allocation. The Allocation Bitmap tracks cluster usage across the cluster heap. The Main Boot Region spans sectors 0 to 11 (with sector 11 storing a 32-bit checksum of sectors 0 to 10), mirrored by a Backup Boot Region in sectors 12 to 23.
* **Decision:**
  1. Validate Volume Boot Record parameters from sector 0 and verify the 32-bit VBR boot checksum against sector 11. If primary boot sectors are damaged, automatically fall back to the Backup Boot Region (sectors 12 to 23).
  2. Parse file entry sets (primary File entry, Stream Extension, and concatenated File Name entries).
  3. Validate the 16-bit `SetChecksum` field across the entry set (restoring the active `0x80` bit for deleted entries `0x05`, `0x40`, `0x41`). If checksum fails, report the entry as `CandidateStatus.CORRUPTED` (damaged metadata) rather than attempting unsafe recovery.
  4. For intact deleted entries with `NoFatChain == 1`, check the Allocation Bitmap for all clusters in `[FirstCluster, FirstCluster + clusters_needed)`. If any cluster is allocated (bit = 1), report as `CandidateStatus.OVERWRITTEN`. If all clusters are unallocated (bit = 0), validate payload with format validators and set `CandidateStatus.PREVIEW_VALIDATED`.
  5. Integrate exFAT discovery into `recoverx scan` and `recoverx recover` with metadata-first priority.
* **Rationale:** Satisfies CLAUDE.md Rules 1, 4, 7 and Milestone M5b acceptance criteria.

---

## ADR 011: Partition Table Recovery, GPT Backup CRC Fallback, and Read-Only SubDevice Mapping

* **Status:** Accepted
* **Context:** Physical storage media and disk images often feature partition tables (MBR or GPT) defining volume boundaries. Partition tables may be wiped, truncated, or damaged, or primary structures may be corrupted while backup structures survive (e.g., backup GPT header at the last LBA, FAT32 backup boot sector at sector 6, exFAT backup boot region at sectors 12-23, NTFS backup boot sector at the last volume sector). Under Rule 1 of CLAUDE.md, RecoverX must never repair, write to, or modify partition tables on disk; instead, discovered partitions and lost volumes must be represented as in-memory slices for metadata recovery and carving.
* **Decision:**
  1. Implement read-only `MbrParser` validating boot signature `0x55 0xAA`, 4 primary partition records, protective MBR (`0xEE`), and safely traversing EBR extended partition chains with cycle detection and depth bounds.
  2. Implement `GptParser` validating primary GPT header at LBA 1 and backup GPT header at the last LBA. Validate header CRC32 (with CRC field zeroed) and partition entry array CRC32.
  3. Explicitly assess and report `GptHeaderHealth` (`BOTH_VALID`, `PRIMARY_VALID_BACKUP_CORRUPT`, `BACKUP_VALID_PRIMARY_CORRUPT`, `BOTH_CORRUPT`, `NOT_FOUND`). When primary GPT is damaged but backup GPT is intact, automatically recover partition entries from the backup copy.
  4. Implement `LostVolumeScanner` performing sector sweeps for lost volumes across FAT12, FAT16, FAT32, exFAT, and NTFS. Recognize backup boot structures when primary boot sectors are wiped/destroyed, reconstructing the original volume start offset without creating duplicate candidates.
  5. Implement `SubDeviceReader(ReadOnlyBlockDevice)` representing an in-memory view of a partition slice at `base_offset` with `size_bytes`. The subdevice translates read requests strictly in memory and exposes zero write/modification methods.
  6. Add CLI command `recoverx partitions IMAGE [--json] [--scan-lost]` and integrate partition discovery into `recoverx scan` and `recoverx recover`.
* **Rationale:** Satisfies CLAUDE.md Rule 1 (source is strictly read-only by construction), Rule 7 (factual reporting), and Milestone M6 acceptance criteria.

---

## ADR 012: Multi-Pass Disk Imaging, Bad-Sector Map, and Resume Identity Check

* **Status:** Accepted
* **Context:** Removable storage devices and failing block devices often suffer from I/O errors and physical degradation. Reading linearly with naive 1-sector retries can take hours or destroy failing flash media. A professional forensic acquisition engine requires multi-pass acquisition (copy, trim, scrape) modeled after GNU ddrescue, non-destructive read timeouts, atomic mapfile checkpointing, ddrescue mapfile compatibility, and safety checks against resuming an image against a different device. Furthermore, under CLAUDE.md Rule 7, if any sector is unreadable, RecoverX must never report the acquisition as complete (`is_complete=False`), and placeholders must be distinguishable from real data zeros via the map.
* **Decision:**
  1. Implement `RangeStatusMap` tracking every sector in one of five states (`NON_TRIED`, `NON_TRIMMED`, `NON_SCRAPED`, `BAD`, `FINISHED`). Support sub-range interval splitting, contiguous range coalescing (conditioned on matching status), atomic JSON serialization, and export to GNU ddrescue v1 format and machine-readable bad sectors JSON.
  2. Implement `DiskImagingService` executing three sequential passes:
     - **Copy pass:** Large aligned block reads (default 64 KiB) advancing sequentially. Upon encountering an unreadable block, skip ahead with an exponentially increasing skip size (from 128 sectors up to 2048 sectors) and mark the unread interval `NON_TRIMMED`.
     - **Trim pass:** For every `NON_TRIMMED` range, probe sector-by-sector from the left edge until an error occurs, probe sector-by-sector backwards from the right edge until an error occurs, and mark the remaining damaged interior as `NON_SCRAPED`.
     - **Scrape pass:** For every `NON_SCRAPED` sector, perform isolated single-sector reads with configurable retries (default 1) and optional delay. If the sector cannot be read, zero-fill the image sector, mark the sector `BAD`, and record its byte offset and length.
  3. Support atomic resumption (`resume=True`). Before resuming an acquisition, read the map's device identity metadata (`capacity_bytes`, `sector_size`, `device_id`, `sector_zero_hash`) and verify that it matches the current source device (`ResumeIdentityMismatchError` on mismatch).
  4. Ensure factual completion: set `is_complete = range_map.is_all_finished and range_map.bad_sectors_count == 0`. If any bad sectors exist, `is_complete` is strictly `False`.
  5. Enforce destination safety: verify that the destination image file does not reside on the source device or volume (`DestinationOnSourceError`).
  6. Add CLI command `recoverx image SOURCE DESTINATION [--block-size] [--retries] [--delay] [--resume] [--no-trim] [--no-scrape] [--no-hash] [--json]`.
* **Rationale:** Satisfies CLAUDE.md Rules 1, 2, 7, and Milestone M7 acceptance criteria.

---

## ADR 013: Application Services, Session Persistence in SQLite, Resource Locking, and Non-Destructive Rebuild

* **Status:** Accepted
* **Context:** The orchestration of multi-step forensic recovery involves managing state across sessions, jobs, candidates, and reports. Under CLAUDE.md Rule 2 and Section 15 of MASTER_PROMPT.md:
  1. The database, work directories, and extracted files must never reside on the source medium.
  2. Recovered file content (bytes) must NEVER be stored in SQLite. Only metadata, hashes, offsets, and paths are persisted.
  3. Database corruption or migration failures must never compromise the source or block recovery; instead, a clear recovery path (backup corrupt database to `.corrupt.<timestamp>` and rebuild fresh schema) is required.
  4. Concurrency constraints require that no two concurrent jobs run on the same source device (`DuplicateSourceJobError`) and no two concurrent jobs target conflicting destination directories (`DestinationConflictError`).
  5. Deep carving must NEVER be launched silently; it requires an explicit user request.
* **Decision:**
  1. Implement `DatabaseManager` providing WAL mode, foreign keys, synchronous=NORMAL, and automatic integrity verification (`PRAGMA integrity_check`). Upon detecting database corruption, preserve a backup copy of the corrupted file with a timestamp and rebuild a clean database from scratch.
  2. Implement repositories (`SessionRepository`, `JobRepository`, `CandidateRepository`, `PartitionRepository`) using atomic `ON CONFLICT(...) DO UPDATE SET` clauses to avoid unintentional cascade deletion of child records.
  3. Implement `JobManager` with thread-safe source locking and destination path collision checking, supporting cooperative cancellation tokens (`CancellationToken`).
  4. Implement `DeviceTriageService` categorizing devices into factual classifications: controller failure, readable with I/O errors (recommending imaging), BitLocker encryption, damaged partition table, or supported filesystems.
  5. Implement `ScanCoordinator` executing the full 10-step sequence: source identification -> triage -> imaging recommendation -> partition analysis -> metadata recovery -> carving offer (never automatic) -> candidate merge and deduplication -> format validation -> factual reporting.
  6. Implement `SessionService` providing high-level session creation, scan execution, and candidate extraction.
  7. Implement `ReportService` exporting forensic reports in both structured JSON and standalone, self-contained HTML formats.
* **Rationale:** Satisfies CLAUDE.md Rules 1, 2, 4, 7, and Milestone M8 acceptance criteria.

---

## ADR 014: Desktop User Interface Architecture with PySide6, Non-Blocking Worker Threads, and Accessibility

* **Status:** Accepted
* **Context:** RecoverX requires a professional, high-performance Windows 10/11 x64 desktop GUI built with PySide6. Under CLAUDE.md Rules 1-7 and Section 14 of MASTER_PROMPT.md:
  1. UI responsiveness: Scans, disk imaging, and file recoveries must run in dedicated background worker threads (`QThread` with signals and slots only; never touch widgets directly from worker threads).
  2. Source safety: Source storage media remains strictly read-only by construction. The UI exposes no write, format, partition-wipe, or disk-repair options.
  3. Destination separation: The recovery destination picker must actively verify separation against the source device and volume (`VolumeIdentityResolver`), immediately disabling confirmation if separation cannot be established.
  4. Untrusted file preview: Recovered files are untrusted. Previews run with strict resource limits (5 MiB ceiling, dimension limits, safe Qt decoding, no crash on corrupt files).
  5. Honest progress & factual status: Real-time progress displays factual metrics (bytes processed, sector numbers, elapsed time, throughput) with no fake progress or probabilistic recovery percentages.
  6. Accessibility: All interactive widgets and pages must define accessible names and descriptions (`setAccessibleName`, `setAccessibleDescription`).
  7. Simulation transparency: Demo mode is OFF by default. When enabled, a prominent warning banner is displayed indicating simulated synthetic storage.
* **Decision:**
  1. Implement `MainWindow(QMainWindow)` with a persistent sidebar (`QListWidget`), a central `QStackedWidget` hosting 7 modular pages, status bar, and top simulation banner.
  2. Implement background threads `ScanWorker` and `RecoveryWorker` inheriting from `QThread`. Workers communicate strictly via Qt signals (`progress_updated`, `scan_completed`, `scan_failed`, `scan_cancelled`). Thread lifecycles are gracefully managed on exit via `closeEvent(event)`.
  3. Implement modular pages:
     - `DashboardPage`: Overview, safety banner, action buttons, and recent sessions table.
     - `DeviceSelectionPage`: Raw disk image loader, device identity card, live hardware triage, and capability matrix.
     - `ScanConfigurationPage`: Metadata scan vs deep carving options, lost volume sweep toggle, and realistic duration notices.
     - `ScanProgressPage`: Progress bar, live throughput, candidate counters, sector offsets, and cancel button.
     - `RecoveryResultsPage`: Discovered candidates table, filename search filter, status dropdown, multi-selection actions, preview button, and recovery button.
     - `RecoveryReportPage`: Audit summary card, sector 0 SHA-256 fingerprint display, factual metrics, and JSON/HTML export buttons.
     - `SettingsPage`: Light/Dark theme selector, capability matrix, and demo mode toggle.
  4. Implement modal dialogs:
     - `FilePreviewDialog`: Resource-limited preview with safe image/text decoding and graceful failure notices.
     - `RecoveryDestinationDialog`: Enforces strict volume separation and provides collision policy choices (`rename`, `skip`, `never_overwrite`).
  5. Implement `demo.py` for synthetic FAT16 disk images showcasing deleted file recovery without accessing physical drives.
  6. Add `recoverx gui` CLI subcommand and application factory `create_application()`.
* **Rationale:** Satisfies CLAUDE.md Rules 1-7 and Milestone M9 acceptance criteria.

---

## ADR 015: Windows Physical Block Device Access, Audited ctypes Win32 Abstraction, and Elevated Helper Named Pipe Protocol

* **Status:** Accepted
* **Context:** Under Windows 10/11 x64, physical block devices (`\\.\PhysicalDrive0..N`) and raw partition volumes require administrative privileges and strictly sector-aligned unbuffered I/O. Under CLAUDE.md Rules 1, 2, 3, 5 and Section 2, 3, 5 of MASTER_PROMPT.md:
  1. The source storage medium is strictly read-only by construction.
  2. No shell-outs (PowerShell, diskpart, wmic) are permitted for device handling or volume enumeration.
  3. The main application (GUI/CLI) must run with standard user privileges. When elevated privileges are needed to access physical drives, an out-of-process elevated worker must be spawned on demand over a local IPC channel.
  4. The elevated worker must expose the narrowest possible interface: open-by-validated-identity, read_at(offset, length), metadata/geometry, close, and cancel. It must strictly reject writes, modifications, formatting, or repair requests.
  5. Windows volume identity and separation checks must resolve drive letters and UNC paths to their backing physical disk number and volume serial to prevent data collisions and enforce separation rules.
* **Decision:**
  1. Implement `recoverx.infrastructure.storage.win32.api` providing audited ctypes wrappers for `kernel32` APIs (`CreateFileW`, `CloseHandle`, `ReadFile`, `SetFilePointerEx`, `DeviceIoControl`, `CancelIoEx`, `CreateNamedPipeW`, `ConnectNamedPipe`, `DisconnectNamedPipe`). Enforce an immediate `ValueError` assertion in `win32_create_file` if `GENERIC_WRITE` (0x40000000) is ever supplied.
  2. Map Win32 error codes (`ERROR_ACCESS_DENIED`, `ERROR_SHARING_VIOLATION`, `ERROR_DEVICE_NOT_CONNECTED`, `ERROR_NOT_READY`, `ERROR_INVALID_HANDLE`, `ERROR_OPERATION_ABORTED`) to specific, actionable domain `StorageError` subclasses.
  3. Implement `WindowsRawDeviceReader(ReadOnlyBlockDevice)` opening physical devices or volumes with `GENERIC_READ`, `FILE_SHARE_READ | FILE_SHARE_WRITE`, computing sector 0 SHA-256 fingerprints, transparently handling sector-aligned unbuffered I/O slicing, and supporting `revalidate_identity()` and `cancel()`.
  4. Implement `WindowsDeviceEnumerator` using pure Win32 APIs (`IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS`, `IOCTL_STORAGE_QUERY_PROPERTY`, `IOCTL_DISK_GET_DRIVE_GEOMETRY_EX`) to enumerate physical drives, bus types, capacity, and associated volume drive letters.
  5. Implement `WindowsVolumeIdentityResolver(VolumeIdentityResolver)` resolving filesystem paths to volume serials and physical disk numbers to enforce Rules 2 & 3.
  6. Implement elevated read helper IPC:
     - `HelperRequest` and `HelperResponse` JSON-lines message wire protocol with base64 data framing.
     - `ElevatedReadHelperService` running on a local Win32 named pipe, validating request bounds and executing strictly read-only commands (`PING`, `OPEN`, `READ`, `CANCEL`, `CLOSE`, `EXIT`).
     - `NamedPipeClient` and `WindowsElevatedDeviceReader(ReadOnlyBlockDevice)` client proxy.
     - `launch_elevated_helper` utilizing `ShellExecuteW` with verb `"runas"` to elevate on demand without running the main application as Administrator.
  7. Integrate physical device selection and live hardware enumeration into `DeviceSelectionPage` in PySide6 GUI.
* **Rationale:** Satisfies CLAUDE.md Rules 1-7 and Milestone M10 acceptance criteria.

---

## ADR 016: Second-Set File Carving Validators, Subprocess-Sandboxed Preview Architecture, and Forensic Report Polish

* **Status:** Accepted
* **Context:** Milestone M11 requires expanding file carving capabilities beyond baseline formats (JPEG, PNG, PDF, ZIP) to cover a comprehensive second set: ISOBMFF multimedia containers (MP4, MOV, M4A, HEIC, AVIF), graphics (GIF87a/GIF89a, BMP), audio/video streams (RIFF WAVE/AVI, MP3 with ID3v2 and MPEG frame sync chains), camera RAW (TIFF, CR2, NEF, ARW, DNG), and databases (SQLite 3). Furthermore, recovered files represent untrusted, often corrupted or adversarial binary payloads. In-process decoding in the GUI main thread risks application crashes, unhandled segfaults in image/media decoders, memory exhaustion, or freezing the UI event loop. Forensic reports also require structured format breakdowns and explicit, auditable factual limitations.
* **Decision:**
  1. **Second-Set Format Validators:**
     - `IsoBmffValidator`: Box hierarchy parser (`ftyp`, `moov`, `mdat`, `meta`), classifying `mp4`, `mov`, `m4a`, `heic`, `avif`. Added `magic_offset: int = 0` to `FileSignature` to handle non-zero signature offsets (such as `ftyp` at offset 4).
     - `GifValidator`: Screen descriptor parser, GCT size calculator, sub-block walker, and trailer `0x3B` verifier.
     - `BmpValidator`: BITMAPFILEHEADER and DIB BITMAPINFOHEADER (12, 40, 52, 56, 108, 124 bytes) validator, 4-byte row padding calculator, exact extent calculation.
     - `RiffValidator`: RIFF container walker (`WAVE`, `AVI `), parsing `fmt `, `data`, `LIST`, `hdrl`, `movi` chunks with 2-byte word padding.
     - `Mp3Validator`: ID3v2 syncsafe header decoder, MPEG Layer III frame sync scanner (`0xFFE0`) verifying continuous audio frame headers and bitrates.
     - `TiffRawValidator`: Dual-endian IFD parser walking tag directories, resolving `StripOffsets`/`StripByteCounts` and `TileOffsets`/`TileByteCounts`, identifying Canon CR2, Nikon NEF, Sony ARW, DNG, and TIFF.
     - `SqliteValidator`: 100-byte SQLite 3 header parser, page size power-of-two check, page count validation, and B-tree page 1 leaf/interior table header verification.
  2. **Out-of-Process Preview Sandbox (`recoverx.presentation.preview`):**
     - `PreviewWorker`: Dedicated CLI subprocess entry point (`python -m recoverx.presentation.preview.worker <file_path> <max_bytes>`) that parses input files with a strict 10 MiB limit, downscales images exceeding 4096px, extracts audio/video metadata, previews SQLite tables/schema, and inspects ZIP archives with path traversal (`../`) protection. Communicates over stdout using typed JSON.
     - `PreviewSandbox`: Spawns the worker subprocess with a hard 3.0s execution timeout and process-killing guarantees. Any parser crash, segfault, or hang is isolated to the subprocess and safely translated into an informative `PreviewResult(kind="error", ...)` without impacting the host GUI.
     - `FilePreviewDialog`: Rewritten to utilize `PreviewSandbox`, presenting rich metadata cards, sanitized text, structured archive listings, and security disclaimers.
  3. **Report Polish:**
     - Updated `ReportService` to aggregate `format_breakdown` (counts and byte totals per extension) in JSON and display dedicated Format Breakdown and Verified Scope & Factual Limitations tables in HTML reports.
* **Rationale:** Satisfies CLAUDE.md Rules 1-7 and Milestone M11 acceptance criteria.

---

## ADR 017: NTFS Metadata Recovery, Update Sequence (Fixup) Verification, Non-Resident Data-Run Decoding, and Hierarchical Path Reconstruction

* **Status:** Accepted
* **Context:** Milestone M12 requires implementing NTFS filesystem metadata recovery. Under Section 7 of MASTER_PROMPT.md and CLAUDE.md Rules 1-7:
  1. NTFS volume parameters must be read from the primary boot sector with automatic fallback to the backup boot sector at the end of the volume.
  2. MFT records must be verified and updated in memory using the update sequence (fixup) array, rejecting torn writes and `BAAD` signatures without modifying the source medium.
  3. Attributes (`$STANDARD_INFORMATION`, `$FILE_NAME`, `$DATA`, `$VOLUME_NAME`, `$BITMAP`) must be parsed with strict bounds checking.
  4. Non-resident data runs with relative cluster deltas must be decoded with cluster count and LCN limits.
  5. Deleted file records (`flags & 0x0001 == 0`) must be detected and verified against `$Bitmap` (Record 6) to detect cluster reallocation.
  6. Hierarchical directory paths must be reconstructed by resolving parent record references up to Root Record 5 with cycle detection.
* **Decision:**
  1. Implement `recoverx.filesystems.ntfs`:
     - `NtfsBootSector` (`boot.py`): Parses OEM ID `NTFS    `, sector/cluster geometry, total sectors, `$MFT` start LCN, and negative power-of-two MFT record sizes (`-10` -> 1024 bytes). Supports backup boot sector fallback.
     - `apply_fixups` (`fixup.py`): Verifies and applies update sequence arrays in memory, validating sector-end USNs and raising `NtfsFixupError` on torn writes or `BAAD` records.
     - `parse_data_runs` and `parse_attribute` (`attributes.py`): Decodes compressed data runs with signed delta LCNs, validates bounds, parses resident attributes and non-resident extents, and extracts `$FILE_NAME` metadata (Win32, DOS, POSIX namespaces).
     - `MftRecord` (`mft_record.py`): Parses 1024-byte record headers, detects deleted records, prioritizes Win32 names, and resolves default `$DATA` streams.
     - `MftReader` (`mft.py`): Resolves Record 0's non-resident data runs to translate record numbers to device byte offsets, supporting sequential record iteration with bounds limits.
     - `NtfsBitmap` (`bitmap.py`): Parses `$Bitmap` (Record 6) to verify whether deleted file clusters remain unallocated or were overwritten.
     - `NtfsPathResolver` (`directory.py`): Reconstructs hierarchical directory paths up to Record 5 (`Root`), guarding against loops with cycle detection.
     - `NtfsDataStreamReader` (`data_recovery.py`): Extracts resident and non-resident file payloads up to declared real sizes.
     - `NtfsFileSystem` (`parser.py`): Implements `FileSystemParser` interface, detecting NTFS, providing `FileSystemInfo`, and extracting `RecoveryCandidate` objects with factual statuses.
  2. Implement `MemoryBlockDevice` (`src/recoverx/infrastructure/storage/memory.py`): Provides an in-memory `ReadOnlyBlockDevice` backed by immutable byte buffers for testing and payload validation.
  3. Integrated `NtfsFileSystem` into `ScanCoordinator` (Step 5) and `cli.py` (`recoverx scan` and `recoverx recover`).
* **Rationale:** Satisfies CLAUDE.md Rules 1-7 and Milestone M12 acceptance criteria.




