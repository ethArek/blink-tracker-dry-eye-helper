#define AppName "Blink Tracker"
#define AppVersion "1.0.0"
#define AppPublisher "Blink Tracker"
#define AppExeName "BlinkTracker.exe"
#define RepoRoot "..\\..\\.."
#define ReleaseDir RepoRoot + "\\dist\\release"
#define IconPath RepoRoot + "\\scripts\\release\\windows\\BlinkTracker.ico"

[Setup]
AppId={{B2B13869-4EA5-474B-9F47-684B8EDE6F32}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#ReleaseDir}
OutputBaseFilename=BlinkTrackerSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExeName}

#if FileExists(IconPath)
SetupIconFile={#IconPath}
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked

[Files]
#if DirExists(ReleaseDir + "\\BlinkTracker")
Source: "{#ReleaseDir}\\BlinkTracker\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#elif FileExists(ReleaseDir + "\\BlinkTracker.exe")
Source: "{#ReleaseDir}\\BlinkTracker.exe"; DestDir: "{app}"; Flags: ignoreversion
#else
#error "Build output not found. Run scripts\\release\\build_windows.ps1 first."
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
