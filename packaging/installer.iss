; =====================================================================
; RecoverX - Inno Setup 6 Installer Script for Windows 10/11 x64
; Forensics-grade removable media data recovery
; Compliant with LGPLv3 onedir dynamically linked Qt distribution
; =====================================================================

#define MyAppName "RecoverX"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "RecoverX Team"
#define MyAppURL "https://github.com/SriRamkunamsetty/data-recovery-software"
#define MyAppExeName "recoverx.exe"

[Setup]
; Basic Application Details
AppId={{D37F8E8A-9A4B-4E7B-8B1D-6F4A8C5D3E2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Destination Directories and 64-bit Architecture Enforcement
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Output Configuration
OutputDir=..\dist\installer
OutputBaseFilename=recoverx-setup-{#MyAppVersion}-windows-x64
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; Licensing & Informational Pages
LicenseFile=..\LICENSE

; Security & Least-Privilege Execution
; Installs for Current User or All Users (dialog prompted if elevated)
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest

; Clean Uninstaller Metadata
UninstallDisplayName={#MyAppName} Data Recovery {#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Distribute full onedir bundle produced by PyInstaller
Source: "..\dist\recoverx\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu and Desktop Shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\{#MyAppName} Command Prompt"; Filename: "{cmd}"; Parameters: "/k ""set PATH={app};%PATH% && recoverx --help"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; Option to launch GUI after setup completes
Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Clean up runtime caches and temporary logs, NEVER delete recovered user files
Type: filesandordirs; Name: "{localappdata}\RecoverX\logs"
Type: filesandordirs; Name: "{localappdata}\RecoverX\cache"
Type: dirifempty; Name: "{localappdata}\RecoverX"
Type: dirifempty; Name: "{app}"
