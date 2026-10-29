# Security Policy and Threat Model

RecoverX is designed to operate safely in forensic environments and handle untrusted, damaged, or adversarial data inputs without endangering the host system or compromising user privacy.

---

## 1. Threat Model and Trust Boundaries

```
+--------------------------------------------------------------------------+
| UNTRUSTED EXTERNAL ENVIRONMENT                                           |
| (Damaged USB flash drives, SD cards, disk images, adversarial files)     |
+--------------------------------------------------------------------------+
                                    |
                    [Strict Read-Only Access Gate]
                    (GENERIC_READ / No writes / Bounds checked)
                                    v
+--------------------------------------------------------------------------+
| STANDARD PRIVILEGE APPLICATION BOUNDARY (asInvoker)                      |
|                                                                          |
|  [Filesystem & Carving Parsers]  --> Overflow-safe integer math          |
|  [Destination Safety Guard]      --> Enforces physical disk separation   |
|  [Path Sanitizer]                --> Neutralizes .. and reserved names   |
|                                                                          |
|       | (Untrusted candidate data)      | (Elevated disk handle requests)
|       v                                 v
|  +---------------------------+    +----------------------------------+   |
|  | Out-of-Process Preview    |    | Local Named Pipe IPC             |   |
|  | Sandbox (Killable worker) |    | (\\.\pipe\recoverx_read_helper)  |   |
|  +---------------------------+    +----------------------------------+   |
+---------------------------------------------------|----------------------+
                                                    | UAC "runas" Elevation
                                                    v
                                    +----------------------------------+
                                    | ELEVATED READ HELPER PROCESS     |
                                    | (Read-only, bounds-verified I/O) |
                                    +----------------------------------+
```

### A. Untrusted Inputs
- Any data read from a storage device or disk image is treated as potentially adversarial.
- Filesystems may contain intentional corruptions, recursive directory loops, torn writes, or crafted partition boundaries.
- **Defenses:**
  - Strict bounds validation on all header sizes, cluster counts, and record offsets.
  - Recursion depth limits and cycle detection when reconstructing directory paths.
  - Integer overflow prevention using Python's arbitrary-precision integers and explicit length checks before allocating memory.
  - No unsafe deserialization (the `pickle` module is completely prohibited; only typed JSON and strict binary structs are used).

### B. Untrusted File Previews
- Opening or decoding untrusted files (e.g. malformed JPEGs, crafted PDFs, corrupted ZIP archives) inside the main application could trigger memory corruption vulnerabilities in media codecs.
- **Defenses:**
  - All preview decoding is isolated inside a dedicated subprocess (`PreviewSandbox`).
  - Worker processes have a hard 10 MiB input cap, downscale images exceeding 4096px, and are subjected to a 3.0s hard execution timeout.
  - If a worker crashes, hangs, or encounters an out-of-memory exception, it is immediately terminated by the host process. The GUI displays an "Unverified / Corrupted" badge and never crashes.

### C. Elevation Boundary (Least Privilege)
- RecoverX GUI and core recovery engines run at standard user level (`asInvoker`).
- Administrative privileges are required on Windows only to acquire low-level `CreateFileW` handles to physical block devices (`\\.\PhysicalDriveX`).
- **Defenses:**
  - Elevation is isolated to a standalone, minimal read helper service (`ElevatedReadHelperService`).
  - Communication occurs over a local Windows named pipe (`\\.\pipe\recoverx_read_helper_*`).
  - The helper accepts only read commands (`OPEN`, `READ`, `CANCEL`, `CLOSE`, `EXIT`) and strictly verifies offset and length ranges against the declared device capacity. It has zero capability to issue write commands.

### D. Data Privacy and Zero Network Access
- RecoverX performs data recovery locally.
- **Network Invariant:** The core recovery engine contains zero networking calls. It does not transmit telemetry, analytics, file hashes, filenames, or recovered data to any external server.
- The software requires no internet connection to function.

---

## 2. Destination Safety and Write Protection

- **Read-Only Source Invariant:** `ReadOnlyBlockDevice` and `WindowsRawDeviceReader` never request `GENERIC_WRITE` access or issue modifying `DeviceIoControl` commands (`FSCTL_LOCK_VOLUME`, `FSCTL_DISMOUNT_VOLUME`).
- **Physical Disk Separation:** `validate_destination_directory` verifies that the target path does not share a volume or physical disk with the source medium.
- **Safe Staging:** Recovered files are written to `.recoverx_partial_*.tmp` temporary files and validated by SHA-256 before being atomically moved into place with `os.replace`.
- **Path Sanitization:** Filenames are sanitized to neutralize Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`), Alternate Data Streams (`:`), illegal characters, and directory traversal sequences (`../`).

---

## 3. Reporting a Vulnerability

If you discover a security vulnerability or data-integrity issue in RecoverX:
1. **Do not disclose the issue publicly.**
2. Send a detailed report with reproduction steps to the security team or open a private security advisory on the GitHub repository:
   - GitHub Security Advisory: https://github.com/SriRamkunamsetty/data-recovery-software/security/advisories
3. Include:
   - Operating system and version.
   - Exact steps or synthetic image file triggering the behavior.
   - Impact assessment (e.g., denial-of-service, sandbox bypass, memory exhaustion).
4. The team will acknowledge receipt within 48 hours and coordinate a coordinated disclosure timeline.
