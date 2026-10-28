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
| **M7: Disk imaging** | Pending | - | Next milestone |
| **M8: Application services & SQLite** | Pending | - | - |
| **M9: Desktop UI (PySide6)** | Pending | - | - |
| **M10: Windows device access** | Pending | - | - |
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




