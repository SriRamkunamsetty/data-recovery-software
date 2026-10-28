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




