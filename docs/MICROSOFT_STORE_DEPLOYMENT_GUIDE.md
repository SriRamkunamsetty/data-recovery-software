# Microsoft Store Deployment Guide for RecoverX

This guide provides the end-to-end instructions for deploying **RecoverX** to the **Microsoft Store** as a certified modern Windows application (`.msix`).

---

## 1. Overview of Architecture

RecoverX is built as a **Win32 Full-Trust Desktop Application** packaged in the modern **MSIX Container format**:
* **Package Format:** MSIX (`.msix` / AppX)
* **Application Architecture:** Windows x64 (compatible with Windows 10 build 17763+ and Windows 11)
* **Capability:** `<rescap:Capability Name="runFullTrust"/>` (standard for Win32 apps distributed on Microsoft Store)
* **Identity:** Defined in [`packaging/AppxManifest.xml`](file:///d:/Projects/data%20recovery%20Software/packaging/AppxManifest.xml)

---

## 2. Pre-Requisites

1. **Microsoft Partner Center Account:**
   * Register a Microsoft Developer account at [partner.microsoft.com](https://partner.microsoft.com/dashboard).
   * Pay the one-time registration fee ($19 for individual accounts, $99 for company accounts).
2. **Windows 10/11 SDK:**
   * `MakeAppx.exe` (located on your system at `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\makeappx.exe`)
   * `SignTool.exe` (located on your system at `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`)

---

## 3. How to Package the MSIX File

We have automated the complete packaging process with [`packaging/build_msix.py`](file:///d:/Projects/data%20recovery%20Software/packaging/build_msix.py):

```powershell
.venv\Scripts\python packaging/build_msix.py
```

This script performs the following automatically:
1. Gathers all binaries from `dist/recoverx/`.
2. Generates all required Microsoft Store asset icons (`Square44x44Logo`, `Square150x150Logo`, `StoreLogo`, `SplashScreen`, `Wide310x150Logo`).
3. Embeds `AppxManifest.xml` with the declared `runFullTrust` capability.
4. Invokes Microsoft's `MakeAppx.exe` to produce `dist/RecoverX-v0.1.0-Store.msix`.

---

## 4. Microsoft Store Submission Walkthrough

### Step 1: Reserve the Application Name
1. Sign in to the [Microsoft Partner Center](https://partner.microsoft.com/dashboard).
2. Click **Apps and games** > **New product** > **MSIX or PWA app**.
3. Enter your app name: `RecoverX` (or `RecoverX Forensic Data Recovery`).
4. Click **Reserve product name**.

### Step 2: Update Package Identity with Your Partner Center Credentials
1. In Partner Center, go to **Product management** > **Package identity**.
2. Copy your unique values:
   * **Package/Identity/Name:** e.g., `YourCompany.RecoverX`
   * **Package/Identity/Publisher:** e.g., `CN=12345678-ABCD-EF01-2345-6789ABCDEF01`
   * **Package/Properties/PublisherDisplayName:** e.g., `Your Name`
3. Update these 3 fields in [`packaging/AppxManifest.xml`](file:///d:/Projects/data%20recovery%20Software/packaging/AppxManifest.xml):
   ```xml
   <Identity
     Name="YOUR_PARTNER_CENTER_NAME"
     ProcessorArchitecture="x64"
     Publisher="YOUR_PARTNER_CENTER_PUBLISHER_CN"
     Version="0.1.0.0" />
   ```
4. Re-run `.venv\Scripts\python packaging/build_msix.py` to regenerate the production package.

### Step 3: Run Windows App Certification Kit (WACK)
Before uploading, test your `.msix` with the official certification kit:
```powershell
# Launch WACK GUI or run from command line:
appcert.exe test -apptype desktop -packagepath "D:\Projects\data recovery Software\dist\RecoverX-v0.1.0-Store.msix" -reportoutputpath "D:\Projects\data recovery Software\dist\wack_report.xml"
```
Ensure all tests (Manifest compliance, Security features, Binary analysis) pass.

### Step 4: Complete the Store Listing
In Partner Center, complete the required submission sections:
1. **Pricing & Availability:**
   * Price: Free (Base).
   * Markets: Worldwide (All markets).
2. **Properties:**
   * Category: **Utilities & Tools** > **File Management** (or **Security & Privacy**).
   * Display catalog hardware requirements: Minimum 4 GB RAM, 64-bit CPU.
3. **Store Listing (Visuals & Copy):**
   * Description: Copy the high-impact summary from [`website/index.html`](file:///d:/Projects/data%20recovery%20Software/website/index.html).
   * Screenshots: Upload the 7 generated UI screenshots from [`website/assets/`](file:///d:/Projects/data%20recovery%20Software/website/assets/).
   * App icon: Upload `packaging/msix_assets/StoreLogo.png`.
4. **Packages:**
   * Drag and drop `dist/RecoverX-v0.1.0-Store.msix`.
   * Partner Center will validate the manifest and virus scan the binary.

### Step 5: Submit for Certification
* Click **Submit to the Store**.
* Microsoft's automated and manual review typically completes within 24 to 72 hours.
* Once approved, RecoverX will be directly installable from the Windows 10 & 11 Microsoft Store app by anyone in the world!

---

## 5. Local Sideloading / Testing (Without Store)

To install and test the `.msix` package on your local computer before submitting to the Store:

1. Enable Developer Mode in Windows:
   * **Settings** > **System** > **For developers** > Turn on **Developer Mode**.
2. Create and trust a local test certificate:
   ```powershell
   # Create test cert
   $cert = New-SelfSignedCertificate -Type Custom -Subject "CN=RecoverXForensics" -KeyUsage DigitalSignature -FriendlyName "RecoverX Test Cert" -CertStoreLocation "Cert:\CurrentUser\My"

   # Export certificate
   Export-Certificate -Cert $cert -FilePath "dist\RecoverXTest.cer"

   # Install into Trusted People (Admin)
   Import-Certificate -FilePath "dist\RecoverXTest.cer" -CertStoreLocation "Cert:\LocalMachine\TrustedPeople"

   # Sign the MSIX
   & "C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe" sign /fd SHA256 /a /f "dist\RecoverXTest.pfx" "dist\RecoverX-v0.1.0-Store.msix"
   ```
3. Double-click `dist\RecoverX-v0.1.0-Store.msix` and click **Install** in the native Windows App Installer window!
