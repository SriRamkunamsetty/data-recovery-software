# RecoverX: Implementation Progress

This document tracks milestone progress, verification results, and known issues across all development sessions.

---

## Milestone Summary

| Milestone | Status | Acceptance Checks | Notes |
|---|---|---|---|
| **M1: Project foundation** | **Completed** | `pytest` (31/31), `ruff`, `mypy` strict passing | Core architecture, domain models, config, logging, CI |
| **M2: Read-only storage & fixtures** | **Completed** | `pytest` (53/53), `ruff`, `mypy` strict passing | `ReadOnlyBlockDevice`, `DiskImageReader`, `FaultInjectionReader`, fixtures, Hypothesis |
| **M3: Carving engine & first formats** | **Completed** | `pytest` (76/76), `ruff`, `mypy` strict passing | `CarvingScanner`, JPEG, PNG, PDF, ZIP/OOXML, `recoverx scan` CLI |
| **M4: Destination safety & recovery** | **Completed** | `pytest` (99/99), `ruff`, `mypy` strict passing | `VolumeIdentityResolver`, atomic writer, collision resolver, `recoverx recover` CLI |
| **M5a: FAT12/16/32 metadata recovery** | **Completed** | `pytest` (124/124), `ruff`, `mypy` strict passing | FAT12/16/32 BPB, backup boot sector, LFN reassembly, contiguous chain check, `recoverx scan` metadata-first |
| **M5b: exFAT metadata recovery** | **Completed** | `pytest` (142/142), `ruff`, `mypy` strict passing | exFAT VBR, backup VBR, entry-set checksum, NoFatChain, allocation bitmap, deleted entry recovery |
| **M6: Partition analysis & lost volumes** | **Completed** | `pytest` (174/174), `ruff`, `mypy` strict passing | MBR, GPT header/array CRC32 checks, backup GPT fallback, FAT/exFAT/NTFS lost volume sweep, in-memory subdevice |
| **M7: Disk imaging** | **Completed** | `pytest` (188/188), `ruff`, `mypy` strict passing | RangeStatusMap, copy/trim/scrape multi-pass imaging, ddrescue mapfile export, resume identity check, `recoverx image` CLI |
| **M8: Application services & SQLite** | **Completed** | `pytest` (208/208), `ruff`, `mypy` strict passing | SQLite repositories, corruption backup/rebuild, JobManager locking, DeviceTriageService, ScanCoordinator 10-step, ReportService JSON/HTML |
| **M9: Desktop UI (PySide6)** | **Completed** | `pytest` (224/224), `ruff`, `mypy` strict passing | Modern light/dark theme, QThread worker threads, preview & destination dialogs, 7 pages, demo mode |
| **M10: Windows device access** | Pending | - | Next milestone |
| **M11: Extra formats & previews** | Pending | - | - |
| **M12: NTFS metadata recovery** | Pending | - | - |
| **M13: Packaging & release checks** | Pending | - | - |

---

## Detailed Milestone Log

### Milestone M1: Project foundation
* **Date:** 2026-10-28
* **Scope Completed:**
  * Clean repository structure established with `src/recoverx/` and downward dependency layers (`domain`, `services`, `infrastructure`, `presentation`).
  * `pyproject.toml` created with pinned runtime and development dependencies, strict mypy configuration, Ruff linting/formatting rules, and pytest settings.
  * Cross-platform GitHub Actions workflow (`.github/workflows/ci.yml`) for Ubuntu and Windows runners.
  * Immutable, validated application configuration (`AppConfig`) with safe operational defaults.
  * Forensic structured logging (`StructuredJsonFormatter`, `StructuredLoggerAdapter`) with context attachment and content protection.
  * Comprehensive domain models implemented and strictly validated:
    * `DeviceIdentity` with sector size power-of-two validation, sector 0 SHA-256 checks, total sectors calculation, and identity comparison.
    * `StorageDevice` with triage classification and bus type metadata.
    * `PartitionInfo` with offset, byte size, and sector range calculations.
    * `FileSystemInfo` with cluster bounds verification.
    * `BadSectorRange` with range boundary tracking.
    * `SectorReadResult` with bounds protection.
    * `ScanProgress` with safe division for progress fraction and percentage.
    * `ScanJob` with lifecycle status tracking.
    * `RecoveryCandidate` strictly enforcing factual `CandidateStatus` enum (Rule 7 of `CLAUDE.md`).
    * `RecoveryResult` and `RecoveryReport`.
  * Stub `LICENSE` marked "owner to decide".
  * Architecture Decision Records in `docs/DECISIONS.md` covering Python 3.12 pinning, dependency rationale (PySide6, pytest, pytest-qt, Hypothesis, ruff, mypy, hatchling), named-pipe elevated helper architecture, factual candidate statuses, and licensing.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (0 errors).
  * `ruff format --check .`: Passed (30 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 24 source files in strict mode).
  * `pytest`: Passed (31 passed in 2.08s).
* **Scope Boundaries:**
  * Completed: Project foundation, configurations, CI, structured logging, all domain models, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M1): Any physical device I/O, filesystem parsing, carving, or UI code.
* **Blockers:**
  * None. Ready for Milestone M2.

---

### Milestone M2: Read-only storage and fixtures
* **Date:** 2026-10-28
* **Scope Completed:**
  * `ReadOnlyBlockDevice` abstract base class enforcing read-only safety by construction:
    * Exposes only `identity`, `device_info`, `size_bytes`, `logical_sector_size`, `read_at(offset, length)`, `close()`, and `__enter__` / `__exit__`.
    * Implements overflow-safe parameter validation (`validate_bounds`) raising `DeviceOutOfBoundsError` prior to any I/O.
    * Completely lacks write, truncate, erase, format, repair, or flush APIs.
  * `DiskImageReader` concrete implementation:
    * Opens disk images strictly in binary read-only mode (`"rb"`), asserting `not handle.writable()`.
    * Extracts sector 0 cryptographic SHA-256 fingerprint and creates `DeviceIdentity` and `StorageDevice`.
    * Bounds-checked, memory-safe `read_at` execution.
    * Idempotent `close()`.
  * `FaultInjectionReader` testing decorator:
    * Configurable unreadable ranges (simulates bad sectors raising `DeviceReadError`).
    * Configurable short read limits (simulates partial block transfers).
    * Configurable latency / delays (simulates hardware read timeouts and degradation).
    * Disconnect thresholds (by cumulative bytes read or target offset) and manual `disconnect()`, raising `DeviceDisconnectedError`.
  * Fixtures and Snapshot Helpers:
    * `SyntheticImageBuilder`: Generates disk images with known files at designated offsets, fill bytes, and produces a `SyntheticImageManifest` with per-file and whole-image SHA-256 hashes.
    * `ImageHashSnapshot`: Calculates and records initial image cryptographic hash, verifying 100% byte and hash immutability after test read operations.
  * Comprehensive Test Suite:
    * Safety tests (`test_storage_safety.py`) asserting absence of write methods via reflection and verifying file handles are read-only.
    * Unit tests (`test_disk_image_reader.py`, `test_fault_injection.py`, `test_fixtures.py`) testing edge cases, overflows, negative offsets, and simulated hardware faults.
    * Hypothesis property-based testing (`test_storage_hypothesis.py`) rigorously testing boundary invariants and end-of-disk reads across arbitrary integer strategies.
  * ADR 006 added to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (41 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 35 source files in strict mode).
  * `pytest`: Passed (53 passed in 1.41s).
* **Scope Boundaries:**
  * Completed: Read-only block storage abstractions, disk image reader, fault injection reader, synthetic image builders, image hash snapshot helper, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M2): Filesystem parsing (M5a, M5b, M12), carving engine (M3), Windows-specific raw device access (M10).
* **Blockers:**
  * None. Ready for Milestone M3.

---

### Milestone M3: Carving engine, first formats, `recoverx scan` CLI
* **Date:** 2026-10-28
* **Scope Completed:**
  * Structural format validators adhering to `FormatValidator` interface:
    * `JpegValidator`: Walks markers (SOI, DQT, SOF, DHT, SOS, EOI), entropy-coded scan data, and parses APP1 EXIF segment lengths to skip inner embedded thumbnails and prevent duplicate candidate generation.
    * `PngValidator`: Walks chunk streams from `IHDR` to `IEND`, verifying CRC-32 on every chunk payload.
    * `PdfValidator`: Scans forward with sliding overlap for `startxref`, trailer dictionaries, and final `%%EOF`, accounting for incremental updates.
    * `ZipValidator`: Scans backwards/forwards for EOCD, parses Central Directory headers, checks zip-bomb entry count ceilings, and classifies OOXML documents (`.docx`, `.xlsx`, `.pptx`) via `[Content_Types].xml`.
  * Declarative `SignatureRegistry`:
    * Configurable magic signatures, sector-alignment constraints, and default M3 format mappings.
  * Streaming `CarvingScanner`:
    * Bounded-memory streaming over `ReadOnlyBlockDevice` via sliding chunk window with configurable chunk size and overlap.
    * Fast binary pattern searching using C-speed `bytes.find`.
    * Candidate deduplication across chunk boundaries and container boundaries (skipping inner ZIP local entries and inner EXIF thumbnail ranges).
    * `CancellationToken` support halting execution within a single chunk.
    * Read-error continuation: automatically skips unreadable bad sectors, tracks bad sector count, and continues scanning without aborting.
    * Atomic `ScanProgress` callbacks reporting bytes scanned, percentage, candidates found, and time estimates.
  * Command-Line Interface (`recoverx scan IMAGE`):
    * Supports `--json` machine-readable output and tabular terminal output.
    * Allows custom `--chunk-size` and `--overlap` parameter configuration.
  * Testing Suite:
    * Unit tests for each validator on valid, truncated, and corrupt structures.
    * Integration tests on multi-file images, cross-chunk boundary placements, and read-error continuation.
    * Property-based fuzzing with Hypothesis over all 4 validators with random and corrupted byte streams ensuring no crashes or hangs.
  * ADR 007 added to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (55 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 49 source files in strict mode).
  * `pytest`: Passed (76 passed in 3.11s).
* **Scope Boundaries:**
  * Completed: Carving engine, first-set validators (JPEG, PNG, PDF, ZIP/OOXML), signature registry, CLI scan command, Hypothesis fuzz tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M3): Writing recovered files (M4), second-set formats (M11), filesystem metadata parsing (M5a, M5b, M12).
* **Blockers:**
  * None. Ready for Milestone M4.

---

### Milestone M4: Destination safety and `recoverx recover` CLI
* **Date:** 2026-10-28
* **Scope Completed:**
  * Defined `VolumeIdentityResolver` interface in `src/recoverx/infrastructure/storage/resolver.py`:
    * Concrete test double `FakeVolumeIdentityResolver` supporting programmatic mapping of block devices and filesystem paths to volume IDs and physical disk numbers.
    * Enforces `DestinationOnSourceError` if source and destination (or work directory) share the same volume ID or the same physical disk number.
    * Enforces `AmbiguousSeparationError` if volume or physical disk identity cannot be resolved with certainty (CLAUDE.md Rule 3).
  * Built destination directory and path sanitizer in `src/recoverx/services/destination_validator.py`:
    * Sanitizes all 22 reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) regardless of extension or casing.
    * Strips trailing dots and spaces, neutralizes Alternate Data Streams (`:`), and removes forbidden filesystem characters (`<`, `>`, `"`, `|`, `?`, `*`).
    * Neutralizes directory traversal attacks (`../`, `..\`) ensuring recovered paths remain strictly relative and sandboxed.
    * Implements case-insensitive duplicate collision resolution (`CollisionPolicy.RENAME`, `CollisionPolicy.SKIP`, `CollisionPolicy.NEVER_OVERWRITE`) preventing silent data loss.
  * Implemented atomic `RecoveryDestinationWriter` in `src/recoverx/services/destination_writer.py`:
    * Stages recovery output to temporary `.part` files (`.recoverx_tmp_*.part`) with strict `fsync()` flushing.
    * Computes SHA-256 during streaming write and validates against expected candidate hash.
    * Unlinks and purges staging file on any error (disk full, permission denied, source disconnect, hash mismatch) ensuring no partial file is left looking complete.
    * Atomically replaces staging file with target path via `os.replace`.
  * Implemented end-to-end `RecoveryService` in `src/recoverx/services/recovery_service.py`:
    * Coordinates separation validation, safe filename resolution, atomic extraction, and creates comprehensive `RecoveryReport`.
  * Command-Line Interface (`recoverx recover IMAGE DESTINATION`):
    * Runs carve-then-recover pipeline in headless/scriptable workflows with `--json` or formatted terminal reporting.
  * Testing Suite:
    * `test_destination_safety.py`: Tests Windows reserved name rewrites, ADS stripping, traversal prevention, same-volume and same-physical-disk refusal.
    * `test_collision_handling.py`: Tests case-insensitive collision numbering and collision policies.
    * `test_destination_writer.py`: Tests atomic replacement, hash mismatch purge, disk-full simulation, disconnect simulation, and permission-denied simulation leaving no partial file.
    * `test_recovery_service.py` & `test_cli_recover.py`: Tests end-to-end recovery workflows and CLI invocations.
  * ADR 008 added to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (64 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 58 source files in strict mode).
  * `pytest`: Passed (100 passed in 3.46s).
* **Scope Boundaries:**
  * Completed: Destination safety, path sanitization, atomic staging writer, collision resolution, recovery service, CLI recover command, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M4): Real Windows volume resolution via Win32 ctypes (M10), GUI destination selection (M9), filesystem metadata recovery (M5a, M5b, M12).
* **Blockers:**
  * None. Ready for Milestone M5a.

---

### Milestone M5a: FAT12/16/32 metadata recovery
* **Date:** 2026-10-28
* **Scope Completed:**
  * `FatBpb` in `src/recoverx/filesystems/fat/bpb.py`:
    * Robust BIOS Parameter Block parser and geometric validator for FAT12, FAT16, and FAT32.
    * Microsoft cluster count FAT classification algorithm (`CountofClusters < 4085` -> FAT12, `< 65525` -> FAT16, `>= 65525` -> FAT32).
    * Automatic backup boot sector (sector 6 on FAT32) fallback when primary sector 0 has corrupted signatures.
  * `FatDirEntry` and `parse_lfn_entry` in `src/recoverx/filesystems/fat/entry.py`:
    * 32-byte directory entry parser handling active entries and deleted (`0xE5`) files.
    * Microsoft standard 8-bit checksum calculation (`fat_lfn_checksum`) with 1-bit rotate and add.
    * Candidate original first-byte recovery (`verify_lfn_checksum_for_deleted_entry`) for deleted LFNs.
    * Reassembly of reverse-ordered LFN sequences into full Unicode filenames.
    * Safe packed MS-DOS datetime conversion to ISO 8601 strings.
  * `FatTableReader` in `src/recoverx/filesystems/fat/fat_table.py`:
    * Low-level FAT decoding for 12-bit (FAT12), 16-bit (FAT16), and 32-bit (FAT32, 28-bit mask) tables.
    * Allocation state assessment (`is_cluster_free`, `is_end_of_chain`, `is_bad_cluster`).
    * Contiguous cluster chain verification (`check_contiguous_chain`) verifying that deleted files' clusters remain unallocated.
  * `FatDirectoryWalker` in `src/recoverx/filesystems/fat/directory.py`:
    * Safe traversal of root directory and subdirectories.
    * Cycle detection via visited cluster sets stopping circular cluster pointer corruptions.
    * Depth limiting (64 levels) and entry limiting (100,000 entries) preventing infinite loops and memory exhaustion.
  * `FatFileSystem` in `src/recoverx/filesystems/fat/parser.py`:
    * Implementation of `FileSystemParser` ABC.
    * Geometry detection and `FileSystemInfo` reporting.
    * Candidate generation with factual statuses:
      * Unallocated contiguous chains verified with format validators -> `CandidateStatus.PREVIEW_VALIDATED`.
      * Overwritten clusters detected in FAT table -> reported as `CandidateStatus.OVERWRITTEN` (never recovered as corrupted data).
      * Formats without dedicated validators -> `CandidateStatus.METADATA_RECOVERED`.
  * Fixtures and Testing:
    * `SyntheticFatBuilder` in `tests/fixtures/fat_builder.py`: Pure-Python generator for genuine FAT12, FAT16, and FAT32 disk images with active, deleted, LFN, and overwritten files.
    * `test_fat_bpb.py`, `test_fat_entry.py`, `test_fat_table.py`, `test_fat_recovery.py`: Comprehensive unit tests.
    * `test_fat_hypothesis.py`: Property-based fuzzing of BPB and directory parsing with arbitrary byte streams.
    * `test_mkfs_fat.py`: Integration test with images formatted by official `mkfs.fat`.
  * CLI Integration:
    * `recoverx scan` and `recoverx recover` in `src/recoverx/cli.py` now run metadata-first discovery, deduplicating carved candidates against metadata entries, with `--no-carve` and `--include-active` options.
  * Capability Table:
    * Created `docs/CAPABILITIES.md` recording FAT12/16/32 as **Supported**.
  * ADR 009 added to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (80 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 73 source files in strict mode).
  * `pytest`: Passed (124 passed, 1 skipped in 5.88s).
* **Scope Boundaries:**
  * Completed: FAT12/16/32 metadata recovery, BPB parsing, backup boot sector fallback, LFN reassembly, contiguous cluster allocation checks, CLI metadata-first integration, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M5a): exFAT metadata recovery (M5b), partition table analysis (M6), NTFS (M12).
* **Blockers:**
  * None. Ready for Milestone M5b.

---

### Milestone M5b: exFAT metadata recovery
* **Date:** 2026-10-28
* **Scope Completed:**
  * `ExFatVbr` in `src/recoverx/filesystems/exfat/vbr.py`:
    * Volume Boot Record parser extracting geometry, power-of-two sector/cluster shifts, partition offset, volume length, FAT offset, cluster heap offset, and root directory cluster.
    * 32-bit VBR boot checksum calculation over sectors 0 to 10 (bytes 0 to `11 * bytes_per_sector - 1`), explicitly skipping `VolumeFlags` (bytes 106-107) and `PercentInUse` (byte 112) of Sector 0.
    * Automatic fallback to Backup Boot Region (sectors 12 to 23) when primary VBR has corrupted signatures or failed boot checksum.
  * `ExFatFileEntrySet` and entry parsers in `src/recoverx/filesystems/exfat/entry.py`:
    * File Directory Entry (`0x85` active, `0x05` deleted), Stream Extension Entry (`0xC0` active, `0x40` deleted), and File Name Entries (`0xC1` active, `0x41` deleted).
    * Unicode filename reassembly up to 255 UTF-16LE characters across secondary name entries.
    * 16-bit Entry-Set Checksum calculation (`exfat_entry_set_checksum`) with 1-bit rotate and add across all entries in the set (skipping the checksum field itself).
    * Deleted entry-set checksum verification: restores bit 7 on type bytes (`|= 0x80`) before calculating check, ensuring accurate detection of metadata corruption on deleted files.
    * `NoFatChain` flag handling (`GeneralFlags & 0x02`), identifying contiguously allocated files that bypass the FAT table.
    * Timestamps parsing (created, modified, accessed) with 10ms increments and UTC timezone offsets.
  * `ExFatAllocationBitmap` in `src/recoverx/filesystems/exfat/bitmap.py`:
    * Reads cluster allocation bits from the allocation bitmap cluster chain.
    * Contiguous cluster verification (`check_contiguous_chain`) verifying that deleted files' clusters remain unallocated (bit = 0).
  * `ExFatDirectoryWalker` in `src/recoverx/filesystems/exfat/directory.py`:
    * Safe traversal of root directory and subdirectories.
    * Automatic discovery and extraction of special root entries: Allocation Bitmap (`0x81`), Up-case Table (`0x82`), and Volume Label (`0x83`).
    * Cycle detection via visited cluster sets and entry/depth limits preventing infinite loops.
  * `ExFatFileSystem` in `src/recoverx/filesystems/exfat/parser.py`:
    * Implementation of `FileSystemParser` ABC for exFAT.
    * Candidate generation with factual statuses:
      * Checksum mismatch on entry set -> `CandidateStatus.CORRUPTED`.
      * Reallocated clusters detected in Allocation Bitmap -> `CandidateStatus.OVERWRITTEN`.
      * Intact unallocated cluster run validated with format validator -> `CandidateStatus.PREVIEW_VALIDATED`.
      * Intact unallocated cluster run without format validator -> `CandidateStatus.METADATA_RECOVERED`.
  * Fixtures and Testing:
    * `SyntheticExFatBuilder` in `tests/fixtures/exfat_builder.py`: Bit-perfect exFAT image builder with primary and backup VBRs, valid VBR checksums, allocation bitmaps, active, deleted, and overwritten files, and `NoFatChain` flags.
    * Unit tests: `test_exfat_vbr.py`, `test_exfat_entry.py`, `test_exfat_bitmap.py`, `test_exfat_recovery.py`.
    * Property testing: `test_exfat_hypothesis.py` fuzzing VBR and entry sets.
    * Integration testing: `test_mkfs_exfat.py` for validation against images formatted by official `mkfs.exfat`.
  * CLI Integration:
    * `recoverx scan` and `recoverx recover` automatically detect and parse exFAT volumes alongside FAT12/16/32, carving engine, and metadata-first deduplication.
  * Updated `docs/CAPABILITIES.md` recording exFAT as **Supported**.
  * ADR 010 added to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (93 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 86 source files in strict mode).
  * `pytest`: Passed (142 passed, 2 skipped in 6.87s).
* **Scope Boundaries:**
  * Completed: exFAT VBR parsing, backup boot region fallback, entry-set checksum, NoFatChain, allocation bitmap, deleted entry recovery, CLI integration, fixtures, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M5b): Partition table analysis (M6), disk imaging (M7), NTFS (M12).
* **Blockers:**
  * None. Ready for Milestone M6.

---

### Milestone M6: Partition analysis and lost-volume recovery
* **Date:** 2026-10-28
* **Scope Completed:**
  * In-Memory SubDevice Mapping (`SubDeviceReader` in `src/recoverx/infrastructure/storage/subdevice.py`):
    * Implements `ReadOnlyBlockDevice` representing an in-memory view of a partition slice at `base_offset` with `size_bytes`.
    * Translates offsets strictly in memory without ever writing to the source device (Rule 1 of CLAUDE.md).
    * Performs bounds validation; completely lacks write, truncate, erase, format, or repair APIs.
    * Allows metadata parsers (`FatFileSystem`, `ExFatFileSystem`) and carvers to operate directly on partition offsets.
  * MBR and EBR Parser (`src/recoverx/partitions/mbr.py`):
    * Parses sector 0 Master Boot Record, verifies boot signature `0x55 0xAA`, extracts 32-bit disk signature and 4 primary partition records.
    * Detects active/bootable flags (`0x80`), partition types (FAT12, FAT16, FAT32, NTFS/exFAT, Linux, etc.), and identifies Protective MBR (`0xEE`).
    * Safely traverses Extended Boot Record (EBR) chains for logical partitions with cycle detection and depth bounds.
    * Detects corrupted entries, non-standard boot indicators, and out-of-bounds sector ranges.
  * GPT Parser and CRC32 Validation (`src/recoverx/partitions/gpt.py`):
    * Parses Primary GPT (LBA 1) and Backup GPT (last LBA).
    * Computes standard IEEE 802.3 CRC32 over header bytes (with CRC field zeroed) and verifies against stored `HeaderCRC32`.
    * Reads full partition entry array (`num_entries * entry_size`) and verifies CRC32 against stored `PartitionEntryArrayCRC32`.
    * Evaluates `GptHeaderHealth` across `BOTH_VALID`, `PRIMARY_VALID_BACKUP_CORRUPT`, `BACKUP_VALID_PRIMARY_CORRUPT`, `BOTH_CORRUPT`, `NOT_FOUND`.
    * Automatic recovery from Backup GPT: when primary GPT is corrupted/invalid but backup GPT is intact, partition entries are automatically recovered from the backup copy.
  * Lost Volume Scanner (`src/recoverx/partitions/scanner.py`):
    * Scans block storage for lost, orphaned, or unpartitioned filesystem boot sectors.
    * Detects primary and backup boot structures across FAT12, FAT16, FAT32, exFAT, and NTFS.
    * Reconstructs original volume start offset when primary boot sectors are wiped/destroyed:
      * FAT32: Surviving backup boot sector at sector 6 reconstructs volume start at `S - 6`.
      * exFAT: Surviving backup boot region at sector 12 reconstructs volume start at `S - 12`.
      * NTFS: Surviving backup boot sector at the volume's last sector reconstructs volume start at `S - total_sectors`.
    * Forward-looking primary detection prevents duplicate candidate reporting when both primary and backup exist.
  * Partition Analyzer Orchestrator (`src/recoverx/partitions/analyzer.py`):
    * Evaluates disk layout: MBR -> GPT -> Lost Volume Sweep.
    * Produces structured `PartitionAnalysisResult` with factual evidence notes.
    * Provides `create_subdevice()` helper for seamless downstream analysis.
  * Command-Line Interface:
    * Added `recoverx partitions IMAGE [--json] [--scan-lost]` command.
    * Updated `recoverx scan` and `recoverx recover` to automatically discover and recover files from all detected partitions and lost volumes.
  * Fixtures and Comprehensive Testing:
    * `SyntheticPartitionBuilder` in `tests/fixtures/partition_builder.py`: builds MBR, EBR chains, healthy GPT, corrupted-primary GPT, and lost volume disk images with embedded filesystems.
    * Unit tests: `test_mbr.py`, `test_gpt.py`, `test_subdevice.py`, `test_lost_volume_scanner.py`, `test_partition_analyzer.py`, `test_cli_partitions.py`.
    * Property testing: `test_partition_hypothesis.py` fuzzing MBR and GPT parsers with arbitrary byte sequences.
    * Immutability verification: `ImageHashSnapshot` verifies source disk images are bit-for-bit unchanged after partition analysis and subdevice recovery.
  * Documentation:
    * Added Section 4 to `docs/CAPABILITIES.md` recording MBR, GPT, and lost volume discovery as **Supported**.
    * Added ADR 011 to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (108 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 101 source files in strict mode).
  * `pytest`: Passed (174 passed, 2 skipped in 9.39s).
* **Scope Boundaries:**
  * Completed: MBR parsing, EBR traversal, GPT primary and backup parsing, CRC32 checks, backup GPT fallback, FAT32/exFAT/NTFS lost volume discovery and backup boot structure recovery, in-memory SubDeviceReader mapping, CLI integration, tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M6): Raw disk imaging (M7), persistent SQLite scan database (M8), desktop GUI (M9), NTFS MFT parsing (M12).
* **Blockers:**
  * None. Ready for Milestone M7.

---

### Milestone M7: Disk imaging
* **Date:** 2026-10-28
* **Scope Completed:**
  * Domain & Persistence Models for Disk Acquisition (`src/recoverx/domain/imaging.py`):
    * `SectorStatus` enum (`NON_TRIED`, `NON_TRIMMED`, `NON_SCRAPED`, `BAD`, `FINISHED`).
    * `BlockRange` dataclass representing contiguous sector ranges with specific status.
    * `ImagingConfig` dataclass with strictly validated parameters: block size, exponential skip parameters, retry counts, scraping delays, and flags.
    * `ImagingProgress` and `ImagingResult` tracking real-time status, rates, byte counts, elapsed times, and cryptographic hashes.
  * Range Status Map & Mapfile Export (`src/recoverx/infrastructure/storage/range_map.py`):
    * `RangeStatusMap` tracks every sector across large media efficiently using disjoint sorted intervals.
    * Sub-range splitting and contiguous status-aware range coalescing.
    * Atomic mapfile persistence (`save_file` via `.tmp` rename / `load_file`).
    * `export_bad_sectors_json`: outputs machine-readable JSON list of bad sector ranges with byte offsets and lengths.
    * `export_ddrescue_mapfile`: generates standard GNU ddrescue v1 compatible mapfile format with header comments, status markers (`?`, `*`, `/`, `-`, `+`), and standard pos/size fields for seamless interoperability with third-party forensic tools.
  * Multi-Pass Forensic Disk Imaging Service (`src/recoverx/services/disk_imaging_service.py`):
    * Implements three sequential passes modeled after GNU ddrescue:
      * **Copy Pass:** Large block reads (default 64 KiB) advancing forward. Upon encountering I/O faults, dynamically skips ahead with exponential backoff (from 128 to 2048 sectors) and marks skipped regions `NON_TRIMMED`.
      * **Trim Pass:** Scans `NON_TRIMMED` boundaries from left and right edges with sector precision, trimming healthy data and marking bad interiors `NON_SCRAPED`.
      * **Scrape Pass:** Performs isolated single-sector reads on `NON_SCRAPED` sectors with user-configurable retries and delays.
    * Destination safety verification (`DestinationOnSourceError` if output is on source disk).
    * Pre-allocated sparse/raw image file creation.
    * Factual zero-fill on bad sectors with explicit recording in range map.
    * Strict factual completion reporting: `is_complete=False` if any bad sector exists (CLAUDE.md Rule 7).
    * Resumable imaging with strict source device identity verification (`ResumeIdentityMismatchError` if device size, sector size, or sector 0 hash differs).
    * SHA-256 integrity hashing of acquired image stream.
  * CLI Integration (`src/recoverx/cli.py`):
    * Added `recoverx image SOURCE DESTINATION [--block-size] [--retries] [--delay] [--resume] [--no-trim] [--no-scrape] [--no-hash] [--json]` command.
    * Displays structured tabular progress and acquisition summary or JSON output.
  * Comprehensive Testing:
    * `tests/unit/test_range_map.py`: Interval splitting, coalescing, JSON serialization round-trip, ddrescue format export.
    * `tests/unit/test_disk_imaging_service.py`: Healthy disk acquisition, fault-injected bad sector precision, incomplete flag verification, cancellation and resume identity checks, destination collision prevention.
    * `tests/unit/test_cli_image.py`: Command-line interface testing with JSON and table formatting.
    * `tests/property/test_imaging_hypothesis.py`: Hypothesis property fuzzing verifying range map partitioning and status invariants across random interval updates.
  * Documentation:
    * Added Section 5 to `docs/CAPABILITIES.md` recording Disk Imaging capabilities as **Supported**.
    * Added ADR 012 to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (115 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 108 source files in strict mode).
  * `pytest`: Passed (188 passed, 2 skipped in 9.70s).
* **Scope Boundaries:**
  * Completed: RangeStatusMap, copy/trim/scrape passes, ddrescue mapfile export, resume identity validation, bad-sector zero fill, SHA-256 calculation, CLI image command, comprehensive unit and property tests.
  * Partial: None.
  * Not implemented (intentionally out of scope for M7): Persistent SQLite scan session database (M8), desktop GUI (M9), elevated helper process (M10).
* **Blockers:**
  * None. Ready for Milestone M8.

---

### Milestone M8: Application services, persistence, workers
* **Date:** 2026-10-28
* **Scope Completed:**
  * Domain & Concurrency Models (`src/recoverx/domain/session.py`):
    * `RecoverySession` tracking session lifecycle, source path, device identity, triage status, and notes.
    * `ScanJobRecord` tracking individual scan, imaging, and extraction executions.
    * `DeviceTriageResult` encapsulating triage classification, recommendations, and scanning eligibility.
    * `CancellationToken` providing thread-safe cooperative cancellation and checkpoints.
    * Exceptions: `DuplicateSourceJobError`, `DestinationConflictError`, `DatabaseCorruptionError`, `ScanCancelledError`.
  * SQLite Persistence & Corruption Recovery (`src/recoverx/infrastructure/persistence/`):
    * `DatabaseManager`: WAL mode, foreign keys (`PRAGMA foreign_keys = ON`), synchronous=NORMAL, and automatic integrity verification (`PRAGMA integrity_check`).
    * Non-destructive corruption recovery: when database corruption is detected, preserves a timestamped backup of the corrupted file (`.corrupt.<timestamp>`) and automatically rebuilds a clean database to unblock operations.
    * Schema migrations tracking schema versions.
    * Strict forensic compliance: verified that no raw recovered file content (bytes) is stored in SQLite (Rule 15 of `MASTER_PROMPT.md`).
    * Repositories (`SessionRepository`, `JobRepository`, `CandidateRepository`, `PartitionRepository`) implemented with `INSERT INTO ... ON CONFLICT(...) DO UPDATE SET` clauses to avoid unintentional cascade deletion of child records.
  * Concurrency and Resource Locking (`src/recoverx/services/job_manager.py`):
    * `JobManager` enforces thread-safe mutual exclusion across active jobs.
    * Rejects duplicate concurrent jobs on the same physical source device (`DuplicateSourceJobError`).
    * Rejects concurrent operations targeting the same or nested destination paths (`DestinationConflictError`).
    * Manages job tokens and ensures lock cleanup upon completion, failure, or cancellation.
  * Storage Device Triage (`src/recoverx/services/device_triage_service.py`):
    * Evaluates device health before scanning across all 6 master categories: controller failure (0 bytes / implausible size), readable with I/O errors (recommending raw imaging), BitLocker encryption detection (`-FVE-FS-` signature), damaged/missing partition tables, and supported filesystems.
  * Forensic Orchestrator (`src/recoverx/services/scan_coordinator.py`):
    * Executes the full 10-step sequence: source identification -> triage -> imaging advice -> partition analysis -> metadata recovery -> explicit carving offer -> candidate merge and deduplication -> format validation -> factual status assignment.
    * Strict adherence: deep scan / carving NEVER starts without an explicit request (`enable_carving=False` by default).
    * Candidate merging preserves rich metadata (original filename, directory path, timestamps) while upgrading validation status if verified by carving.
  * Session Application Service (`src/recoverx/services/session_service.py`):
    * Coordinates sessions, jobs, scans, and recovery extractions with database persistence and resource locking.
  * Forensic Report Generator (`src/recoverx/services/report_service.py`):
    * Exports structured JSON reports and clean, self-contained HTML reports with embedded styling, device fingerprints (sector 0 SHA-256), partition tables, candidate breakdowns, and factual integrity statements.
  * Comprehensive Testing Suite:
    * `tests/unit/test_persistence.py`: Repositories CRUD, corruption recovery (deliberate binary corruption, backup verification, and clean rebuild), verification of no content in SQLite.
    * `tests/unit/test_job_manager.py`: Duplicate source job rejection, destination conflict rejection, cancellation signaling, lock cleanup.
    * `tests/unit/test_device_triage_service.py`: Controller failure, fault-injected read errors, BitLocker signature, supported FAT32, blank disk.
    * `tests/unit/test_scan_coordinator.py`: Deep scan never starts without request, carving when requested, candidate merging and status upgrading, cancellation token check.
    * `tests/unit/test_report_service.py`: JSON export structure, HTML standalone rendering.
    * `tests/integration/test_end_to_end_session.py`: Full end-to-end integration test from synthetic image with deleted FAT32 files -> session creation -> scan coordinator -> candidate persistence -> file recovery to safe destination -> hash verification -> report generation -> source immutability check.
  * Documentation:
    * Added Section 6 to `docs/CAPABILITIES.md` recording Application Services, Persistence, and Reporting as **Supported**.
    * Added ADR 013 to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (131 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 124 source files in strict mode).
  * `pytest`: Passed (208 passed, 2 skipped in 10.38s).
* **Scope Boundaries:**
  * Completed: DatabaseManager, schema migrations, repositories, JobManager, DeviceTriageService, ScanCoordinator, SessionService, ReportService, unit tests, end-to-end integration test.
  * Partial: None.
  * Not implemented (intentionally out of scope for M8): Desktop GUI with PySide6 (M9), Windows raw device helper (M10), additional carving formats (M11), NTFS MFT parsing (M12).
* **Blockers:**
  * None. Ready for Milestone M9.

---

### Milestone M9: Desktop User Interface (PySide6)
* **Date:** 2026-10-28
* **Scope Completed:**
  * Modern Theme & Stylesheets (`src/recoverx/presentation/theme.py`):
    * Light and Dark QSS theme definitions adhering to WCAG contrast standards.
    * Polished component styling for sidebar navigation, cards, tables, status boxes, primary/danger buttons, and simulation banner.
  * Worker Thread Architecture (`src/recoverx/presentation/workers.py`):
    * `ScanWorker` and `RecoveryWorker` inheriting from `QThread`.
    * Dedicated background execution with thread-safe Qt signals and slots (`progress_updated`, `scan_completed`, `scan_failed`, `scan_cancelled`, `recovery_completed`, `recovery_failed`).
    * Cooperative cancellation support via `CancellationToken`. Zero UI thread blocking.
  * Modal Dialogs (`src/recoverx/presentation/dialogs/`):
    * `FilePreviewDialog`: Untrusted candidate preview with a 5 MiB resource limit, safe image decoding via `QPixmap`, plain text renderer, and non-crashing error fallback.
    * `RecoveryDestinationDialog`: Real-time destination separation verification using `VolumeIdentityResolver`. Strictly refuses any destination on the same volume or physical disk (`DestinationOnSourceError`). Provides configurable collision policy options (`rename`, `skip`, `never_overwrite`).
  * Modular Pages (`src/recoverx/presentation/pages/`):
    * `DashboardPage`: Overview dashboard, safety banner, "Start New Recovery" action card, and SQLite recent sessions table.
    * `DeviceSelectionPage`: Raw disk image loader, device identity grid, real-time hardware triage, capability matrix, and selection confirmation.
    * `ScanConfigurationPage`: Fast metadata scan vs deep carving options, lost volume boot sweep toggle, and explicit deep carving time warnings.
    * `ScanProgressPage`: Progress bar, live throughput calculation, candidate discovery counters, sector offsets, and graceful scan cancellation.
    * `RecoveryResultsPage`: Discovered candidates table, filename search filter, status dropdown, multi-select operations ("Select Validated Only", "Select All", "Deselect All"), file preview trigger, and batch recovery launch.
    * `RecoveryReportPage`: Forensic audit summary card, sector 0 SHA-256 fingerprint, factual honesty notice, and one-click JSON/HTML export buttons with file dialogs.
    * `SettingsPage`: Light/Dark theme selector, engine capability matrix, and demo mode simulation toggle (OFF by default).
  * Application Shell & Navigation (`src/recoverx/presentation/main_window.py`):
    * `MainWindow(QMainWindow)` with persistent sidebar navigation (`QListWidget`), `QStackedWidget` routing across all 7 pages, status bar, and simulation banner.
    * Safe `closeEvent` lifecycle management ensuring active background worker threads are gracefully terminated on window close.
  * Simulation Demo Mode (`src/recoverx/presentation/demo.py`):
    * Synthetic in-memory FAT16 disk image generator with deleted files (JPEG, text files) for zero-risk testing and demonstration.
  * App Factory & CLI Integration:
    * `src/recoverx/presentation/app.py`: `create_application()` and `main()` factory wiring services to the UI shell.
    * `src/recoverx/cli.py`: Integrated `recoverx gui` CLI subcommand.
  * Comprehensive UI Test Suite:
    * `tests/unit/test_ui_workers.py`: ScanWorker execution, cancellation, and RecoveryWorker candidate extraction.
    * `tests/unit/test_ui_dialogs.py`: Text preview, JPEG preview, size ceiling check, destination separation enforcement, and collision policy options.
    * `tests/unit/test_ui_pages.py`: Page rendering, button signals, image loading, triage updates, search/filtering, selection helpers, and accessible attributes.
    * `tests/unit/test_ui_main_window.py`: Window launch, sidebar routing, demo mode toggle, and full end-to-end smoke test from image selection to scan, results, and forensic report.
  * Documentation:
    * Added Section 7 to `docs/CAPABILITIES.md`.
    * Added ADR 014 to `docs/DECISIONS.md`.
* **Verification Checks (Real Output):**
  * `ruff check .`: Passed (All checks passed).
  * `ruff format --check .`: Passed (151 files already formatted).
  * `mypy src tests`: Passed (Success: no issues found in 144 source files in strict mode).
  * `pytest`: Passed (224 passed, 2 skipped in 15.61s).
* **Scope Boundaries:**
  * Completed: Modern PySide6 desktop UI, worker threads, dialogs, pages, demo mode, tests, docs.
  * Partial: None.
  * Not implemented (intentionally out of scope for M9): Windows elevated physical device helper (M10), additional carving formats (M11), NTFS MFT parsing (M12).
* **Blockers:**
  * None. Ready for Milestone M10.







