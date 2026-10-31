; RecoverX Inno Setup Script
; Generates standard Windows installer with Inno Setup Compiler (ISCC)

#define MyAppName "RecoverX"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "RecoverX Open Source"
#define MyAppURL "https://github.com/SriRamkunamsetty/data-recovery-software"
#define MyAppExeName "recoverx.exe"

[Setup]
AppId={{E582A9C0-8B31-419F-B43E-9102927C6C42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=RecoverX-Setup-v{#MyAppVersion}-Inno
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\recoverx\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; IconFilename: "{app}\assets\icon.ico"
Name: "{autoprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; Tasks: desktopicon; IconFilename: "{app}\assets\icon.ico"

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "gui"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
