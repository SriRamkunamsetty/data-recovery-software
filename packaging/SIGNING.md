# Windows Authenticode Code Signing Guide

## 1. Why Authenticode Signing is Mandatory for RecoverX

RecoverX performs raw physical block device enumeration and block reads (`\\\\.\\PhysicalDriveX`, `FSCTL_LOCK_VOLUME`, `IOCTL_DISK_GET_DRIVE_GEOMETRY_EX`) using Windows kernel APIs, and spawns an elevated read helper subprocess.

On modern Windows 10 and Windows 11 systems:
1. **Windows SmartScreen:** Unsigned executables that request administrative elevation or open raw physical drive handles trigger aggressive SmartScreen warnings (*"Windows protected your PC - Microsoft Defender SmartScreen prevented an unrecognized app from starting"*).
2. **Antivirus Heuristics:** Low-level sector access from unpackaged or unsigned PyInstaller executables is frequently misclassified by heuristic scanners as suspicious raw disk activity.
3. **User Account Control (UAC):** When the elevated read helper launches, a valid digital signature provides an authenticated publisher name rather than a scary "Unknown Publisher" prompt.

---

## 2. Certificate Requirements

- **Type:** Commercial Authenticode Code Signing Certificate.
  - **EV (Extended Validation) Certificate (Recommended):** Provides immediate Windows SmartScreen trust reputation without an initial reputation ramp-up period. Requires hardware security token (HSM or FIPS 140-2 Level 2 USB token) or cloud key service (Azure Key Vault, AWS CloudHSM).
  - **Standard OV (Organization Validation) Certificate:** Valid, but requires an initial download volume reputation buildup before SmartScreen warnings dissipate.
- **Hashing Algorithm:** Modern Windows builds strictly require **SHA-256** digests. Do not use SHA-1.
- **Timestamping:** Every signature must include an **RFC 3161** compliant timestamp so the binary remains valid and trusted even after the signing certificate expires.

---

## 3. Tooling Setup

Use `signtool.exe` from the official Windows SDK (installed with Visual Studio or the standalone Windows 10/11 SDK):
- Typical path: `C:\Program Files (x86)\Windows Kits\10\bin\<version>\x64\signtool.exe`

Ensure `signtool.exe` is in your `PATH` or define an environment variable:
```powershell
$SignTool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe"
```

---

## 4. Signing Step-by-Step

### Step 1: Sign All DLLs and Extension Modules in `dist\recoverx`
All dynamically linked libraries bundled in the PyInstaller `onedir` folder should be signed before creating the installer:

```powershell
# Sign all binaries in the distribution directory
Get-ChildItem -Path "dist\recoverx" -Include *.exe, *.dll, *.pyd -Recurse | ForEach-Object {
    & $SignTool sign /fd SHA256 `
        /tr "http://timestamp.digicert.com" `
        /td SHA256 `
        /d "RecoverX Data Recovery" `
        /du "https://github.com/SriRamkunamsetty/data-recovery-software" `
        /sha1 "<YOUR_CERT_THUMBPRINT>" `
        $_.FullName
}
```

### Step 2: Build the Installer
Compile `packaging\installer.iss` using Inno Setup Compiler (`iscc.exe`):
```powershell
& "C:\Program Files (x86)\Inno Setup 6\iscc.exe" packaging\installer.iss
```

### Step 3: Sign the Setup Installer Executable
Sign the final installer executable generated in `dist\installer`:
```powershell
& $SignTool sign /fd SHA256 `
    /tr "http://timestamp.digicert.com" `
    /td SHA256 `
    /d "RecoverX Setup" `
    /du "https://github.com/SriRamkunamsetty/data-recovery-software" `
    /sha1 "<YOUR_CERT_THUMBPRINT>" `
    "dist\installer\recoverx-setup-1.0.0-windows-x64.exe"
```

---

## 5. Signature Verification

Verify the digital signature and timestamp chain:
```powershell
& $SignTool verify /pa /v "dist\installer\recoverx-setup-1.0.0-windows-x64.exe"
```

Expected output:
```text
Verifying: dist\installer\recoverx-setup-1.0.0-windows-x64.exe
Hash of file (sha256): ...
Signing Certificate Chain:
    ...
Successfully verified: dist\installer\recoverx-setup-1.0.0-windows-x64.exe
```

---

## 6. Antivirus False-Positive Dispute Protocol

If an unsigned development build is flagged by Microsoft Defender:
1. Submit false-positive analysis at: [Microsoft Security Intelligence Sample Submission](https://www.microsoft.com/en-us/wdsi/filesubmission).
2. Select **Software developer** -> **Incorrectly detected as malware (false positive)**.
3. Attach the binary and specify: *"Forensics data recovery tool packaged with PyInstaller onedir mode; opens block devices in strict read-only mode (`GENERIC_READ`)."*
