# RecoverX: Capability Table and Recovery Limitations

This document tracks the factual capability status of RecoverX across filesystems, carving formats, storage backends, and features.
Labels strictly follow the tri-state rating: **Supported**, **Partial**, or **Not supported / Pending**.

---

## 1. Filesystem Metadata Recovery

| Filesystem | Status | Capabilities & Verified Scope | Honest Limitations |
|---|---|---|---|
| **FAT12** | **Supported** | BPB parsing, 12-bit FAT table unpacking, 8.3 short name and LFN reassembly, deleted `0xE5` entry recovery, contiguous unallocated cluster validation, format validator verification. | Recovery assumes contiguous cluster allocation; fails if clusters were reused/overwritten. Lost 1st char of short name without LFN is marked `_`. |
| **FAT16** | **Supported** | BPB parsing, 16-bit FAT table unpacking, root directory sector traversal, LFN reassembly with short-name checksum validation, contiguous unallocated cluster validation. | Fails if clusters were reused or fragmented after deletion. |
| **FAT32** | **Supported** | FAT32 BPB parsing, backup boot sector (sector 6) automatic fallback on primary corruption, cluster chain root directory traversal, subdirectory walking with cycle/depth limits, 28-bit cluster mask, LFN reassembly, contiguous unallocated cluster verification. | Fails if clusters were reused or fragmented after deletion. |
| **exFAT** | **Supported** | Volume Boot Record parsing, 32-bit VBR boot checksum, backup boot region (sectors 12-23) fallback, directory entry set parsing (File, Stream Extension, File Name), 16-bit entry-set checksum verification, Allocation Bitmap unallocated cluster check, NoFatChain contiguous run recovery. | Fragmented files deleted without FAT chains cannot be fully recovered; entry-set checksum failures are reported as damaged metadata. |
| **NTFS** | Pending | Scheduled for Milestone M12. | Not yet supported. |

---

## 2. File Format Carving Engine

| Format | Status | Capabilities & Verified Scope | Honest Limitations |
|---|---|---|---|
| **JPEG** | **Supported** | SOI/EOI marker walk, SOF/DQT/DHT parsing, embedded APP1 EXIF thumbnail deduplication. | Fragmented JPEGs are recovered up to corruption/break point. |
| **PNG** | **Supported** | 8-byte signature, chunk-by-chunk stream walk (`IHDR` to `IEND`), full CRC-32 verification on every chunk, required `IDAT` presence check. | Cannot reconstruct out-of-order chunks across fragmentation. |
| **PDF** | **Supported** | `%PDF-` header scan, incremental update traversal, `startxref`, trailer dictionary parsing, final `%%EOF` validation. | Linearized/fragmented PDFs with missing xref tables are marked Truncated. |
| **ZIP / OOXML** | **Supported** | Local file header verification, backward/forward EOCD scan, 46-byte Central Directory validation, zip-bomb entry count limits, OOXML classification (`.docx`, `.xlsx`, `.pptx`). | Encrypted ZIPs are preserved as encrypted archives without password cracking. |
| **MP4 / MOV** | Pending | Scheduled for Milestone M11. | Not yet supported. |
| **HEIC / AVIF** | Pending | Scheduled for Milestone M11. | Not yet supported. |
| **GIF / BMP** | Pending | Scheduled for Milestone M11. | Not yet supported. |
| **WAV / AVI / MP3** | Pending | Scheduled for Milestone M11. | Not yet supported. |
| **RAW (TIFF-based)** | Pending | Scheduled for Milestone M11. | Not yet supported. |
| **SQLite** | Pending | Scheduled for Milestone M11. | Not yet supported. |

---

## 3. Storage Safety and Destination Guarantees

| Feature | Status | Capabilities & Verified Scope |
|---|---|---|
| **Read-Only Source Enforcement** | **Supported** | `ReadOnlyBlockDevice` ABC with zero write APIs; `DiskImageReader` opens in `"rb"` asserting `not writable()`. |
| **Source / Destination Separation** | **Supported** | Same volume and same physical disk unconditionally refused (`DestinationOnSourceError`); ambiguous identities refused (`AmbiguousSeparationError`). |
| **Atomic File Writing** | **Supported** | Staged in `.recoverx_tmp_*.part` files with `fsync()`, SHA-256 verification, and immediate purge on error (no partial files). |
| **Path Traversal & Reserved Names** | **Supported** | Neutralizes `../`, ADS (`:`), trailing dots/spaces, and rewrites all 22 Windows reserved device names (`CON`, `PRN`, etc.). |
| **Windows Raw Disk Access** | Pending | Scheduled for Milestone M10 (elevated helper process and named pipe). |

---

## 4. Partition Analysis and Lost Volume Recovery

| Feature | Status | Capabilities & Verified Scope | Honest Limitations |
|---|---|---|---|
| **MBR Partition Parsing** | **Supported** | Master Boot Record parsing, active bootable flag detection, CHS/LBA address decoding, protective MBR (`0xEE`) recognition, EBR extended partition chain traversal with cycle and depth limits. | Dynamic disks (LDM) and proprietary RAID metadata are reported as raw or unsupported. |
| **GPT Partition Parsing** | **Supported** | Primary (LBA 1) and Backup (last LBA) GPT headers, header CRC32 and partition entry array CRC32 verification, UEFI GUID decoding, UTF-16LE partition names, automatic fallback to Backup GPT when primary is corrupted. | Damaged partition array with corrupt CRC is reported as corrupted GPT. |
| **Lost Volume Discovery** | **Supported** | Deep boot-sector signature sweep for unpartitioned disks and wiped partition tables: FAT12/16/32, exFAT, and NTFS volume detection. | Requires intact filesystem boot sector or backup structure; completely wiped boot sectors without backup cannot determine geometry. |
| **Backup Boot Structure Recovery** | **Supported** | Recovers volume offsets when primary boot sector is destroyed using FAT32 backup boot sector (sector 6), exFAT backup boot region (sectors 12-23), and NTFS backup boot sector (last sector of volume). | Relies on backup structures having survived; overwritten or truncated volumes cannot be reconstructed from missing backups. |
| **In-Memory SubDevice Mapping** | **Supported** | `SubDeviceReader` maps partition offsets in memory without writing anything to the source device (Rule 1 of CLAUDE.md). Passes directly to metadata recovery and carving engines. | Does not modify on-disk partition tables. |

---

## 5. Disk Imaging and Fault-Tolerant Acquisition

| Feature | Status | Capabilities & Verified Scope | Honest Limitations |
|---|---|---|---|
| **Multi-Pass Acquisition Engine** | **Supported** | Sequential multi-pass acquisition (`Copy`, `Trim`, `Scrape`) modeled after GNU ddrescue. Large aligned block reads with exponential skip upon encountering errors, binary boundary trimming to single-sector precision, and isolated single-sector scrape with configurable retries and delays. | Cannot recover physically dead or unpowered drives; reads depend on OS and storage controller timeout behavior. |
| **Atomic Range Map Tracking** | **Supported** | `RangeStatusMap` tracks every sector in one of five states (`NON_TRIED`, `NON_TRIMMED`, `NON_SCRAPED`, `BAD`, `FINISHED`). Atomic mapfile persistence via `.tmp` rename, sub-range splitting, and contiguous range coalescing. | Mapfile must be kept alongside the image file; losing the mapfile requires re-verifying blocks. |
| **Ddrescue Mapfile & Bad Sector Export** | **Supported** | Exports GNU ddrescue v1 compatible mapfile format (`+`, `?`, `/`, `*`, `-`) for interoperability with external forensic tools. Exports machine-readable bad sectors JSON list with byte offsets and lengths. | Ddrescue command-line arguments are not identical, but the mapfile syntax matches GNU ddrescue specifications. |
| **Resumable Imaging & Identity Guard** | **Supported** | Safe resume of interrupted acquisitions. Validates source device identity against stored map metadata (`capacity_bytes`, `sector_size`, `device_id`, `sector_zero_hash`) rejecting mismatched devices (`ResumeIdentityMismatchError`). | Refuses resume if source device content has changed or if disk size differs. |
| **Strict Factual Completion Reporting** | **Supported** | If any bad sectors are encountered, zeros are written to image placeholders, bad sectors are recorded in the map, and `is_complete` is strictly set to `False`. Zero false claims of 100% completion. | Zero placeholders in the raw image represent unreadable data; inspecting the mapfile is required to distinguish zero-filled sectors from genuine data zeros. |

---

## 6. Application Services, Persistence, and Reporting

| Feature | Status | Capabilities & Verified Scope | Honest Limitations |
|---|---|---|---|
| **SQLite Session Persistence** | **Supported** | WAL mode, foreign keys, and repositories for sessions, jobs, candidates, and partitions. Persists candidate metadata, offsets, hashes, and recovery status. Never stores raw recovered file content (bytes) in SQLite (Rule 15 of MASTER_PROMPT.md). | Database stores metadata only; extracted file payloads reside in the chosen destination directory. |
| **Database Corruption Recovery** | **Supported** | `DatabaseManager` runs `PRAGMA integrity_check` on initialization. If corrupted, preserves a timestamped backup of the corrupt file (`.corrupt.<timestamp>`) and automatically rebuilds a clean database to unblock recovery operations. | Corruption recovery resets session database history; original source devices remain 100% untouched. |
| **Job Concurrency & Conflict Protection** | **Supported** | `JobManager` enforces single-job access per source device (`DuplicateSourceJobError`) and rejects overlapping/conflicting destination paths (`DestinationConflictError`). Cooperative thread-safe cancellation tokens. | Only one active scan or imaging operation can target a physical device at a time. |
| **Storage Device Triage Service** | **Supported** | Factual classification before scanning: controller failure (0 bytes), readable with I/O errors (recommending imaging), BitLocker encryption detection, damaged partition tables, or supported filesystems. | Hardware controller faults cannot be repaired by software. |
| **Scan Orchestrator (ScanCoordinator)** | **Supported** | Executes 10-step orchestration sequence: source identity validation -> triage -> imaging advice -> partition analysis -> metadata recovery -> explicit carving offer -> candidate merge/deduplication -> format validation -> factual status assignment. Deep carving never starts without explicit request. | Deep carving scans raw sector streams and can take substantial time on large storage devices. |
| **Forensic Report Generation** | **Supported** | `ReportService` exports forensic recovery reports in machine-readable JSON and self-contained, responsive HTML with device identifiers, sector 0 SHA-256 fingerprint, partition layout, candidate breakdown, and factual honesty disclaimers. | HTML reports are static documents generated at completion of scan/recovery. |

