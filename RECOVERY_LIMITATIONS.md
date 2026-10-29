# RecoverX Recovery Capabilities and Technical Limitations

This document provides a factual, forensic-grade explanation of RecoverX capabilities, boundary conditions, data loss mechanics, and critical user safety procedures.

---

## 1. Supported Capabilities Matrix

RecoverX adheres strictly to factual reporting. Statuses are never probabilistic percentages.

### A. Filesystem Metadata Recovery
| Filesystem | Status | What Can Be Recovered | Technical Limitations |
| :--- | :--- | :--- | :--- |
| **FAT12 / FAT16 / FAT32** | **Supported** | Original filenames, directory paths, file sizes, creation/modification timestamps, deleted directory entries (`0xE5`), contiguous and single-cluster data streams. | Fragmented deleted files with zeroed FAT clusters cannot have cluster chains reconstructed beyond the first cluster without carving heuristics. |
| **exFAT** | **Supported** | Full Unicode filenames up to 255 UTF-16 characters, folder hierarchies, timestamps, file sizes up to exFAT limits, non-fragmented flag (`NoFatChain=1`) streams. | Deleted files where the Allocation Bitmap has been reused by new writes cannot be recovered without corruption. |
| **NTFS** | **Supported** | Standard Information & File Name attributes (Win32 & DOS namespaces), hierarchical directory reconstruction, deleted MFT records, resident streams (<700 bytes), non-resident data runs. | Heavily fragmented files whose run-lists exceed available MFT record extents or compressed/sparse NTFS attributes are not yet decoded. EFS-encrypted files cannot be decrypted without original Windows certificate keys. |
| **ext4 / APFS / Btrfs** | **Not Supported** | N/A | Linux and macOS native filesystems are not parsed for filesystem metadata. Raw carving still functions over the block device. |

### B. Raw File Carving Formats
| Format Group | Extensions | Status | Carving & Validation Mechanism |
| :--- | :--- | :--- | :--- |
| **Images & Photos** | JPEG / JPG | **Supported** | SOI (`FF D8`), SOF segment geometry, SOS Huffman scanning, APP1 EXIF thumbnail extraction, EOI (`FF D9`) delimiter verification. |
| | PNG | **Supported** | 8-byte signature, chunk walker (`IHDR`, `IDAT`, `PLTE`), CRC32 verification, `IEND` delimiter. |
| | GIF | **Supported** | Header (`GIF87a`/`GIF89a`), screen descriptor, sub-block walker, trailer (`0x3B`). |
| | BMP | **Supported** | `BM` magic, DIB header (12, 40, 52, 56, 108, 124 bytes), row padding calculation. |
| | HEIC / AVIF | **Supported** | ISO base media `ftyp` box with `heic`/`mif1`/`msf1`/`avif` brand parsing. |
| | RAW (Canon/Nikon/Sony/DNG) | **Supported** | TIFF IFD directory walker, `StripOffsets`/`TileOffsets` bounds checks. |
| **Documents & Archives** | PDF | **Supported** | `%PDF-` header version check, xref / trailer resolution, `%%EOF` verification. |
| | ZIP / DOCX / XLSX / PPTX | **Supported** | Local file header (`PK\x03\x04`), Central Directory (`PK\x01\x02`), End of Central Directory (`PK\x05\x06`). |
| | 7-Zip (7z) | **Supported** | `7z\xBC\xAF\x27\x1C` magic, header CRC32, next header offset calculation. |
| **Audio & Video** | MP4 / MOV / M4A | **Supported** | Atom hierarchy walker (`ftyp`, `moov`, `mdat`), 64-bit atom sizes. |
| | WAV / AVI (RIFF) | **Supported** | RIFF chunk container walker (`WAVE`, `AVI `), 2-byte alignment padding. |
| | MP3 | **Supported** | ID3v2 syncsafe header decoder, MPEG Layer III frame sync (`0xFFE0`) validation. |
| **Databases** | SQLite 3 | **Supported** | 100-byte header, page size power-of-two check, B-tree page 1 verification. |

---

## 2. Fundamental Data Recovery Mechanics

Understanding why files can or cannot be recovered requires understanding the physical and logical layers of digital storage:

```
+-----------------------------------------------------------------------+
| 1. LOGICAL DELETION (High Recovery Likelihood)                        |
|    - Filesystem marks directory entry deleted (e.g. 0xE5 or MFT flag) |
|    - Allocation bitmap clears cluster bits                            |
|    - Actual file content remains untouched on disk sectors            |
+-----------------------------------------------------------------------+
                                  |
                                  v
+-----------------------------------------------------------------------+
| 2. DATA OVERWRITE (Zero Recovery Likelihood)                          |
|    - New files written to unallocated clusters                        |
|    - TRIM command issued on SSD / flash drives                        |
|    - Overwritten magnetic or NAND cells cannot be reconstructed       |
+-----------------------------------------------------------------------+
```

### A. Logical Deletion vs. Data Overwrite
- **Logical Deletion:** When a file is deleted in Windows, the operating system typically does not erase the actual file bytes. Instead, it marks the directory entry or MFT record as inactive and marks the clusters as available in the allocation bitmap. **As long as no new data is written to those clusters, the file is 100% recoverable.**
- **Overwritten Data:** Once a cluster has been reallocated and written over with new data, the previous data is permanently lost. Modern magnetic hard drives and flash memory drives cannot reconstruct previously overwritten data through software.

### B. Solid-State Drives (SSDs) and TRIM / Wear-Leveling
- On modern SSDs, USB flash drives with active controllers, and SD cards supporting TRIM/Deallocate:
- When a file is deleted, the operating system issues a `TRIM` command. The flash memory controller immediately wipes the logical block address or returns all zeroes upon read, even if the background garbage collection has not yet physically recycled the block.
- For SSDs with TRIM enabled, deleted file recovery via software carvers is often impossible unless the drive was disconnected immediately before TRIM commands were dispatched.

### C. File Fragmentation
- File carvers identify files by scanning for contiguous byte signatures.
- If a file was fragmented across non-contiguous clusters (common on heavily used FAT32 drives), file carving can only recover the first contiguous segment up to the next fragment.
- Filesystem metadata recovery (FAT, exFAT, NTFS) can recover fragmented files only if the cluster runlists or FAT chains survived deletion.

### D. Encryption and BitLocker
- Volumes encrypted with BitLocker, VeraCrypt, or hardware full-disk encryption present random-looking high-entropy bytes.
- RecoverX cannot bypass encryption. To recover data from an encrypted volume, the volume must be unlocked in Windows with the legitimate recovery key/password so the decrypted virtual volume is presented.

### E. Physical Hardware Failure
- Software tools cannot fix physical damage. Symptoms of physical drive failure include:
  - Clicking, grinding, or buzzing noises.
  - Device disconnecting repeatedly or dropping off USB bus.
  - Read timeouts and escalating I/O device errors (`ERROR_DEVICE_NOT_CONNECTED`, `ERROR_CRC`).
  - Freezing the entire operating system when sector reads are attempted.

> [!CAUTION]
> **WARNING: STOP IMMEDIATELY ON PHYSICAL FAILURE**
> Running software scans on a physically degrading drive rapidly grinds the read heads and destroys the magnetic media or flash controller.
> If your drive is making unusual noises or failing to respond, **DISCONNECT IT IMMEDIATELY** and send it to a professional cleanroom data recovery lab.

---

## 3. The 5-Step Recovery Safety Checklist

Before running any recovery operation, follow these golden rules to avoid permanent data loss:

1. **Stop Using the Device Immediately:**
   Do not save new files, browse the web, or install software onto the affected drive. Every second of disk activity risks overwriting deleted files.
2. **Never Format or Run CHKDSK:**
   Never format the drive, create new partitions, or run Windows `chkdsk`. CHKDSK attempts to make the filesystem structurally consistent by truncating orphaned clusters and deleting corrupted directory entries, destroying recoverable data in the process.
3. **Acquire a Raw Disk Image First:**
   Always use RecoverX's **Disk Image** tool (`recoverx image` or Dashboard -> Image Disk) to clone the entire drive into a raw `.raw`/`.img` image file before performing extensive carving scans. Scans can then be performed risk-free against the disk image without stressing the original media.
4. **Enforce Separate Destination:**
   Never recover files onto the same drive or physical disk you are recovering from. RecoverX strictly enforces this rule and blocks any destination on the same physical disk.
5. **Seek Professional Services for Hardware Damage:**
   If the drive has bad sectors, severe read errors, or mechanical issues, use multi-pass imaging with scraping disabled (`--no-scrape`) to acquire as many good sectors as possible, or refer the device to a cleanroom recovery laboratory.
