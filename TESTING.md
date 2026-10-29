# RecoverX Test Strategy and Verification Guide

RecoverX employs a multi-tiered test harness designed to guarantee data recovery correctness, parser stability, memory safety, and read-only invariants.

---

## 1. Test Suite Architecture

```
tests/
|-- fixtures/               # Synthetic filesystem and media generators
|   |-- exfat_builder.py    # Synthetic exFAT disk image builder
|   |-- fat_builder.py      # Synthetic FAT12/16/32 image builder
|   |-- ntfs_builder.py     # Synthetic NTFS MFT/volume builder
|   +-- sample_files.py     # Valid & corrupted file payload generators
|-- integration/            # End-to-end integration workflows
|   +-- test_end_to_end_session.py
|-- property/               # Property-based fuzzing tests (Hypothesis)
|   |-- test_exfat_hypothesis.py
|   |-- test_fat_hypothesis.py
|   |-- test_imaging_hypothesis.py
|   |-- test_ntfs_hypothesis.py
|   |-- test_partition_hypothesis.py
|   |-- test_storage_hypothesis.py
|   +-- test_validators_hypothesis.py
+-- unit/                   # Isolated component and service tests
    |-- test_carving_*.py   # Carving scanners and 17+ format validators
    |-- test_destination_*.py # Path sanitization and separation guards
    |-- test_ntfs_*.py      # NTFS MFT, fixup, data-runs, directory walk
    |-- test_fat_*.py       # FAT BPB, root directory, cluster chains
    |-- test_exfat_*.py     # exFAT VBR, allocation bitmap, stream sets
    |-- test_gpt.py / test_mbr.py # Partition table parsers
    |-- test_preview_sandbox.py # Sandboxed subprocess limits and crashes
    |-- test_ui_*.py        # Headless PySide6 GUI tests (pytest-qt)
    +-- test_win32_*.py     # Win32 kernel32 and named-pipe helper tests
```

---

## 2. Running the Test Suite

### Full Test Suite Execution
```bash
# Activate your virtual environment
.venv\Scripts\activate

# Run full pytest suite (305 collected tests)
pytest
```

### Running Specific Test Categories
```bash
# Run only property-based tests (Hypothesis)
pytest tests/property

# Run only NTFS filesystem tests
pytest tests/unit/test_ntfs_* tests/property/test_ntfs_hypothesis.py

# Run only UI tests offscreen
set QT_QPA_PLATFORM=offscreen
pytest tests/unit/test_ui_*
```

---

## 3. Property-Based Testing (Hypothesis)

Binary parsers (MBR, GPT, FAT BPB, exFAT VBR, NTFS MFT records, and carving validators) are fuzz-tested against randomized, truncated, and adversarial byte sequences using Hypothesis.

**Core Invariants Tested:**
1. **Crash Freedom:** Parsers must never raise unhandled exceptions or segfault on arbitrary input.
2. **Termination:** Parsers must never loop infinitely on cyclic directory chains or corrupt cluster runs.
3. **Bounds Preservation:** Parsers must never access memory beyond provided buffer boundaries or request out-of-range device offsets.

---

## 4. Synthetic Media Fixtures

To ensure deterministic, reproducible tests without requiring physical disks:
- **`SyntheticImageBuilder`:** Generates raw disk images with synthetic partition tables and injected file payloads.
- **`SyntheticFatBuilder`:** Generates valid FAT12, FAT16, and FAT32 filesystems with active and deleted directory entries.
- **`SyntheticExFatBuilder`:** Generates exFAT volumes with volume boot records, checksum blocks, and allocation bitmaps.
- **`SyntheticNtfsBuilder`:** Generates NTFS volumes with `$Boot`, `$MFT`, `$Bitmap`, deleted resident files, and non-resident cluster runs.
- **`FaultInjectionReader`:** Wraps a `ReadOnlyBlockDevice` to simulate bad sectors, device timeouts, and short reads at specified sector intervals.

---

## 5. Hardware Testing Policy

> [!WARNING]
> Hardware tests communicate with physical storage devices (`\\.\PhysicalDriveX`).
> These tests are **strictly opt-in**, require explicit administrative privileges, and are **NEVER** run as part of automated CI.
> Use disposable, sacrificial USB flash drives only. Never run hardware tests against disks containing valuable data.
