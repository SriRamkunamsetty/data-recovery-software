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
| **exFAT** | Pending | Scheduled for Milestone M5b. | Not yet supported. |
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
