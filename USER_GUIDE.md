# RecoverX User Manual & Operation Guide

RecoverX is a local-first, forensic-grade data recovery tool for Windows 10 and 11 x64, engineered specifically for removable media (USB flash drives, SD cards, external HDDs) and raw disk images.

---

## 1. Quick Start Walkthrough

```
[1. Select Source] ---> [2. Acquire Image] ---> [3. Scan Media] ---> [4. Preview Files] ---> [5. Recover Data]
(USB or .raw file)     (Safety First)          (Metadata + Carve)   (Sandboxed Decoder)   (Separate Disk)
```

### Step 1: Launching RecoverX
- **Desktop Application:** Double-click the `RecoverX` desktop shortcut or launch `recoverx.exe gui`.
- **Command-Line Interface:** Open Command Prompt or PowerShell and type `recoverx --help`.

### Step 2: Device Selection
1. Navigate to the **Devices** page from the left sidebar.
2. RecoverX automatically lists connected removable drives, USB flash drives, and SD cards, displaying their vendor, serial number, capacity, and current triage status.
3. If your drive requires elevated hardware access, RecoverX will request permission to start the secure elevated read helper.
4. *Alternatively:* Click **Open Disk Image** to inspect an existing `.img` or `.raw` forensic image.

### Step 3: The Golden Rule — Image First
If you suspect physical wear or bad sectors:
1. Select the device and click **Image Disk**.
2. Choose a destination folder on your primary drive (separate from the USB drive).
3. RecoverX will execute a multi-pass acquisition (copying readable sectors first, then splitting and retrying difficult blocks).
4. Perform all subsequent recovery scans against the resulting `.raw` image file to protect the original drive from mechanical fatigue.

### Step 4: Configuring and Running a Scan
1. Select the drive or image and click **Start Scan**.
2. **Scan Pipeline:**
   - *Phase 1:* Partition analysis (MBR and GPT).
   - *Phase 2:* Lost volume search (scans unpartitioned space for orphaned boot sectors).
   - *Phase 3:* Filesystem metadata recovery (FAT12, FAT16, FAT32, exFAT, NTFS).
   - *Phase 4:* Signature-based file carving (scans clusters for JPEG, PNG, PDF, DOCX, ZIP, MP4, SQLite, etc.).
   - *Phase 5:* Deduplication (eliminates redundant carved duplicates when metadata exists).

### Step 5: Filtering and Sandboxed File Previews
1. Review discovered files on the **Recovery Results** page.
2. Filter candidates by file extension, recovery status, or filename.
3. Select any candidate and click **Preview**.
4. The file is safely decoded inside an isolated sandbox subprocess. You can inspect:
   - High-resolution image renders (auto-scaled).
   - Extracted EXIF camera metadata and creation dates.
   - Video container dimensions and audio codec specs.
   - SQLite database schema and table row samples.
   - Text and hexadecimal payload samples.

### Step 6: Safe Recovery Extraction
1. Select the files you want to restore.
2. Click **Recover Selected Files**.
3. **Choose Destination:** Select a folder on a **separate physical disk**. RecoverX will block any attempt to save files back to the source drive.
4. **Collision Policy:** Choose how to handle existing filenames:
   - *Auto-Rename (Default):* Saves as `filename (1).ext`.
   - *Skip:* Skips extraction if a file with the same name exists.
   - *Never Overwrite:* Guarantees existing files are never replaced.
5. RecoverX stages files atomically and validates each file with SHA-256 before finalizing.

### Step 7: Exporting Forensic Reports
- Click **Export Report** to generate a forensic audit report in interactive HTML or machine-readable JSON.
- Reports detail the hardware serial number, sector geometry, scan duration, bad sector count, format breakdown, and SHA-256 hashes of all recovered files.

---

## 2. Command-Line Interface (CLI) Reference

RecoverX provides a scriptable CLI for automated pipelines and forensic triage.

### Scan a Disk Image
```bash
recoverx scan C:\forensics\usb_dump.raw
```
*Options:*
- `--json`: Output discovered candidates as structured JSON.
- `--no-carve`: Perform metadata-only recovery (faster scan).
- `--chunk-size <bytes>`: Carving buffer size (default: 1 MiB).

### Recover Files to a Destination
```bash
recoverx recover C:\forensics\usb_dump.raw D:\recovered_files --collision-policy rename
```
*Options:*
- `--collision-policy [rename|skip|never_overwrite]`: Invariant file collision behavior.
- `--include-active`: Recover both active and deleted files.
- `--json`: Output per-file recovery outcomes as JSON.

### Analyze Partition Tables
```bash
recoverx partitions C:\forensics\usb_dump.raw --json
```

### Acquire Multi-Pass Disk Image
```bash
recoverx image \\.\PhysicalDrive1 D:\images\drive1_backup.raw
```
*Options:*
- `--no-scrape`: Skip aggressive scraping of untried bad sectors.
- `--no-hash`: Skip SHA-256 computation of destination image.

---

## 3. Troubleshooting & FAQ

### Q: Why is my USB drive showing "Access Denied"?
- **Cause:** Windows requires administrative privileges to open raw drive handles (`\\.\PhysicalDriveX`).
- **Solution:** Run RecoverX as Administrator, or click "Authorize Elevation" when prompted by the read helper UAC dialog.

### Q: Why does RecoverX refuse to recover to my selected destination?
- **Cause:** RecoverX enforces **strict destination separation** (CLAUDE.md Rule 2). You cannot save recovered files onto any volume on the same physical disk as the source device.
- **Solution:** Connect an external drive or choose a folder on a different internal SSD/HDD.

### Q: Can RecoverX recover files from a BitLocker drive?
- If the BitLocker drive is locked, its sectors contain encrypted high-entropy data that cannot be carved. Unlock the drive in Windows first using your recovery password or key, then select the decrypted volume drive letter.

### Q: Can RecoverX recover overwritten files?
- No software can recover data that has been physically overwritten by new files or cleared via SSD TRIM commands. See [RECOVERY_LIMITATIONS.md](RECOVERY_LIMITATIONS.md) for details.
