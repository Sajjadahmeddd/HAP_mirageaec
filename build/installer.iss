; Inno Setup script for MAEC HAPExt.
;
; Produces a single Setup.exe for SharePoint distribution. Deliberately a
; PER-USER install (PrivilegesRequired=lowest): it needs no admin rights,
; which matters on locked-down company machines where engineers cannot
; write to Program Files.
;
; Build:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" build\installer.iss
; Input:  build\app\MAEC_HAPExt\   (PyInstaller --onedir output)
; Output: dist\MAEC_HAPExt_Setup_v1.0.exe

#define AppName "MAEC HAPExt"
#define AppVersion "1.0"
#define AppPublisher "Mirage AEC"
#define AppExeName "MAEC_HAPExt.exe"

[Setup]
AppId={{8C4B2E71-9A3D-4F55-B0E2-HAPEXT000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MAEC_HAPExt_Setup_v{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "app\MAEC_HAPExt\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
