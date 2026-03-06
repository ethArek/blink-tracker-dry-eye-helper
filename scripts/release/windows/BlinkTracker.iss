#ifndef AppName
  #define AppName "Blink Tracker"
#endif
#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif
#ifndef AppVersionNumeric
  #define AppVersionNumeric "1.1.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Blink Tracker"
#endif
#ifndef AppPublisherURL
  #define AppPublisherURL "https://github.com/ethArek/dry-eye-blink"
#endif
#ifndef AppSupportURL
  #define AppSupportURL "https://github.com/ethArek/dry-eye-blink"
#endif
#ifndef AppUpdatesURL
  #define AppUpdatesURL "https://github.com/ethArek/dry-eye-blink/releases"
#endif
#ifndef AppDescription
  #define AppDescription "Blink Tracker installer"
#endif
#ifndef AppCopyright
  #define AppCopyright "Copyright (c) 2026 Blink Tracker"
#endif
#ifndef AppExeName
  #define AppExeName "BlinkTracker.exe"
#endif
#define RepoRoot "..\\..\\.."
#define ReleaseDir RepoRoot + "\\dist\\release"
#define IconPath RepoRoot + "\\scripts\\release\\windows\\BlinkTracker.ico"

[Setup]
AppId={{B2B13869-4EA5-474B-9F47-684B8EDE6F32}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppPublisherURL}
AppSupportURL={#AppSupportURL}
AppUpdatesURL={#AppUpdatesURL}
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
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright={#AppCopyright}
VersionInfoDescription={#AppDescription}
VersionInfoProductName={#AppName}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoVersion={#AppVersionNumeric}

#if FileExists(IconPath)
SetupIconFile={#IconPath}
#endif

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked

[Files]
#if DirExists(ReleaseDir + "\\BlinkTracker")
Source: "{#ReleaseDir}\\BlinkTracker\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "*.log,blinks.db"
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
