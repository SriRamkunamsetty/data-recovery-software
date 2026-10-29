# RecoverX v1.0.0 Release Notes

**Release Date:** October 29, 2026  
**Build Architecture:** Windows 10/11 x64 (AMD64)  
**Distribution Channel:** Standalone portable `.zip` and Inno Setup installer  
**Target Environments:** Microsoft Windows 10 and Windows 11 (64-bit)

---

## 1. Executive Summary

RecoverX v1.0.0 is the first production release of our local-first, forensic-grade data recovery software designed specifically for removable block storage devices (USB flash drives, SD/microSD cards, CF cards, external HDDs) and raw disk image files.

Engineered under strict read-only and destination-safety invariants, RecoverX guarantees that hardware sources are never modified or written to, while preventing accidental overwrite of existing media by enforcing physical disk separation.

---

## 2. Key Capabilities & Highlights

1. **Non-Destructive Read-Only Operation:**
   - Source block devices are opened exclusively in read-only mode (`GENERIC_READ`).
   - Hardware write, erase, and filesystem modify commands are structurally prohibited.
2. **Comprehensive Filesystem Metadata Recovery:**
   - **FAT12 / FAT16 / FAT32:** Recovers directory structures, cluster chains, and deleted directory entries (`0xE5`).
   - **exFAT:** Parses Volume Boot Records, Main/Backup checksums, and Stream Extension records with Allocation Bitmap checks.
   - **NTFS:** Parses primary and backup boot sectors, in-memory Update Sequence (Fixup) arrays, resident streams, and non-resident data runs. Reconstructs full directory path trees.
3. **Advanced Raw File Carving (17+ Formats):**
   - High-performance sliding-window carver with dedicated extent and delimiter validators:
     - *Images:* JPEG (with EXIF thumbnails), PNG, GIF, BMP, HEIC/AVIF, TIFF-based RAW (Canon CR2, Nikon NEF, Sony ARW, DNG).
     - *Documents & Archives:* PDF, ZIP, DOCX, XLSX, PPTX, 7-Zip.
     - *Audio & Video:* MP4, MOV, M4A, RIFF (WAVE, AVI), MP3.
     - *Databases:* SQLite 3.
4. **Out-of-Process Preview Sandbox:**
   - Untrusted candidate files are safely inspected inside an isolated subprocess with a 10 MiB buffer cap, 4096px downscaling, and a 3.0s hard timeout to isolate potential parser exploits.
5. **Multi-Pass Forensic Disk Imaging:**
   - Implements a resilient ddrescue-style imaging pipeline (Copy, Split, Retry, Scrape) to extract readable sectors from failing drives onto safe storage before analysis.
6. **Strict Destination Separation:**
   - Uses native Windows IOCTLs (`IOCTL_STORAGE_GET_DEVICE_NUMBER`, `IOCTL_VOLUME_GET_VOLUME_DISK_EXTENTS`) to refuse recovery targeting any volume on the same physical disk as the source media.
7. **Forensic Audit Reporting:**
   - Exports interactive HTML and structured JSON reports containing device serial numbers, bad sector locations, format breakdowns, and SHA-256 hashes of all recovered files.

---

## 3. System Requirements

- **Operating System:** Windows 10 (version 1809 or higher) or Windows 11 (64-bit).
- **Processor:** x86-64 / AMD64 architecture.
- **Memory:** Minimum 4 GB RAM (8 GB recommended for large carving operations).
- **Storage:** Dedicated secondary drive or external storage with free space exceeding the total capacity of the recovered media.
- **Privileges:** Standard user privileges for running scans on disk images and launching the GUI; Administrator elevation (prompted on-demand via UAC) when opening physical block devices (`\\.\PhysicalDriveX`).

---

## 4. Download and Integrity Verification

Download the official release distribution from the project repository:
- **Standalone Portable Zip:** `recoverx-1.0.0-windows-x64.zip`
- **Windows Setup Installer:** `recoverx-setup-1.0.0-windows-x64.exe`

### Verifying SHA-256 Checksums
Verify your downloaded package using PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 recoverx-1.0.0-windows-x64.zip
```

Compare the computed hash against the official `dist\SHA256SUMS.txt` manifest:
```text
7d3594ada4bd4e95...  recoverx-1.0.0-windows-x64.zip
7673989f92643249...  recoverx/recoverx.exe
```

---

## 5. Known Limitations & Open Items

As mandated by our commitment to factual software engineering:
1. **Physical Hardware Failures:** RecoverX is a software recovery tool. Devices suffering from physical mechanical damage (clicking read heads, motor failure, burnt controllers) cannot be repaired by software and must be submitted to a professional cleanroom laboratory.
2. **TRIM on SSDs / Flash Media:** Files deleted from solid-state drives where the operating system has issued a TRIM command cannot be recovered once the controller has zeroed the logical block addresses.
3. **BitLocker Encryption:** Encrypted volumes must be unlocked in Windows prior to recovery so cleartext sectors are accessible.
4. **Clean-Machine Testing Notice:** Clean-machine testing was validated via automated headless smoke test (`scripts/smoke_test_clean_machine.py`) on Windows 11 x64. Testing on bare-metal physical hardware with disconnected external drives is documented in `BUILDING.md` and requires dedicated sacrificial media.
