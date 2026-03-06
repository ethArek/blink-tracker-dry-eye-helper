$ErrorActionPreference = "Stop"

function Get-RepositoryUrl {
  $remoteUrl = $null
  try {
    $remoteUrl = git config --get remote.origin.url 2>$null
  } catch {
    return $null
  }

  if ([string]::IsNullOrWhiteSpace($remoteUrl)) {
    return $null
  }

  $trimmedUrl = $remoteUrl.Trim()
  if ($trimmedUrl -match "^git@github\.com:(?<owner>[^/]+)/(?<repo>[^.]+?)(?:\.git)?$") {
    return "https://github.com/$($matches.owner)/$($matches.repo)"
  }

  if ($trimmedUrl -match "^https?://") {
    return ($trimmedUrl -replace "\.git$", "")
  }

  return $trimmedUrl
}

function Get-RepositoryOwner {
  param(
    [string]$RepositoryUrl
  )

  if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
    return $null
  }

  if ($RepositoryUrl -match "github\.com[:/](?<owner>[^/]+)/") {
    return $matches.owner
  }

  return $null
}

function Get-PackageVersion {
  param(
    [string]$PythonCommand
  )

  $version = & $PythonCommand -c "from blink_app import __version__; print(__version__)"
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) {
    throw "Could not read blink_app.__version__ using '$PythonCommand'."
  }

  return $version.Trim()
}

function Convert-ToWindowsVersionParts {
  param(
    [string]$Version
  )

  $parts = @()
  foreach ($match in [regex]::Matches($Version, "\d+")) {
    if ($parts.Count -ge 4) {
      break
    }
    $parts += [int]$match.Value
  }

  if ($parts.Count -eq 0) {
    throw "Version '$Version' does not contain any numeric components."
  }

  while ($parts.Count -lt 4) {
    $parts += 0
  }

  return $parts
}

function Escape-PythonVersionString {
  param(
    [string]$Value
  )

  if ($null -eq $Value) {
    return ""
  }

  return $Value.Replace("\", "\\").Replace('"', '\"')
}

function Get-SignToolPath {
  if (-not [string]::IsNullOrWhiteSpace($env:BLINK_TRACKER_SIGNTOOL_PATH)) {
    if (Test-Path $env:BLINK_TRACKER_SIGNTOOL_PATH) {
      return $env:BLINK_TRACKER_SIGNTOOL_PATH
    }

    throw "BLINK_TRACKER_SIGNTOOL_PATH points to '$($env:BLINK_TRACKER_SIGNTOOL_PATH)', but that file does not exist."
  }

  $signToolCommand = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
  if ($signToolCommand) {
    return $signToolCommand.Source
  }

  $windowsKitRoots = @()
  if ($env:ProgramFiles) {
    $windowsKitRoots += (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
  }
  if (${env:ProgramFiles(x86)}) {
    $windowsKitRoots += (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin")
  }

  foreach ($root in $windowsKitRoots) {
    if (-not (Test-Path $root)) {
      continue
    }

    $candidate = Get-ChildItem -Path $root -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -like "*\x64\signtool.exe" } |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) {
      return $candidate.FullName
    }
  }

  return $null
}

function Get-SigningConfig {
  $thumbprint = $env:BLINK_TRACKER_SIGN_CERT_SHA1
  $pfxPath = $env:BLINK_TRACKER_SIGN_PFX_PATH
  $pfxPassword = $env:BLINK_TRACKER_SIGN_PFX_PASSWORD
  $timestampUrl = $env:BLINK_TRACKER_TIMESTAMP_URL
  if ([string]::IsNullOrWhiteSpace($timestampUrl)) {
    $timestampUrl = "http://timestamp.digicert.com"
  }

  $hasSigningMaterial = -not [string]::IsNullOrWhiteSpace($thumbprint) -or -not [string]::IsNullOrWhiteSpace($pfxPath)
  if (-not $hasSigningMaterial) {
    return $null
  }

  if (-not [string]::IsNullOrWhiteSpace($pfxPath) -and -not (Test-Path $pfxPath)) {
    throw "BLINK_TRACKER_SIGN_PFX_PATH points to '$pfxPath', but that file does not exist."
  }

  $signToolPath = Get-SignToolPath
  if (-not $signToolPath) {
    throw "Signing was requested, but signtool.exe could not be found. Install the Windows SDK or set BLINK_TRACKER_SIGNTOOL_PATH."
  }

  return [pscustomobject]@{
    SignToolPath = $signToolPath
    Thumbprint = $thumbprint
    PfxPath = $pfxPath
    PfxPassword = $pfxPassword
    TimestampUrl = $timestampUrl
  }
}

function Sign-ReleaseBinary {
  param(
    [string]$Path,
    [pscustomobject]$SigningConfig
  )

  if (-not $SigningConfig) {
    return
  }

  if (-not (Test-Path $Path)) {
    throw "Cannot sign '$Path' because it does not exist."
  }

  $signArgs = @("sign", "/fd", "SHA256", "/td", "SHA256")
  if (-not [string]::IsNullOrWhiteSpace($SigningConfig.TimestampUrl)) {
    $signArgs += @("/tr", $SigningConfig.TimestampUrl)
  }
  if (-not [string]::IsNullOrWhiteSpace($SigningConfig.Thumbprint)) {
    $signArgs += @("/sha1", $SigningConfig.Thumbprint)
  } else {
    $signArgs += @("/f", $SigningConfig.PfxPath)
    if (-not [string]::IsNullOrWhiteSpace($SigningConfig.PfxPassword)) {
      $signArgs += @("/p", $SigningConfig.PfxPassword)
    }
  }
  $signArgs += $Path

  & $SigningConfig.SignToolPath @signArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Code signing failed for '$Path' (exit code $LASTEXITCODE)."
  }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "..\..")

if (Test-Path "build") {
  Remove-Item -Recurse -Force "build"
}
if (Test-Path "dist") {
  Remove-Item -Recurse -Force "dist"
}
if (Test-Path "BlinkTracker.spec") {
  Remove-Item -Force "BlinkTracker.spec"
}

$PythonExe = "python"
if (Test-Path ".venv\Scripts\python.exe") {
  $PythonExe = ".venv\Scripts\python.exe"
}

$null = & $PythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed for '$PythonExe'. Install it with: pip install pyinstaller (in the same environment), then rerun."
}

& $PythonExe -c "import mediapipe as mp; import sys; print(f'Using mediapipe {mp.__version__}'); sys.exit(0 if hasattr(mp, 'solutions') else 1)"
if ($LASTEXITCODE -ne 0) {
  throw "Installed mediapipe for '$PythonExe' does not expose mp.solutions. Install mediapipe==0.10.21 in that environment, then rerun."
}

$AppName = "Blink Tracker"
$AppExeName = "BlinkTracker.exe"
$RepositoryUrl = Get-RepositoryUrl
$RepositoryOwner = Get-RepositoryOwner -RepositoryUrl $RepositoryUrl
$AppVersion = Get-PackageVersion -PythonCommand $PythonExe
$WindowsVersionParts = Convert-ToWindowsVersionParts -Version $AppVersion
$WindowsVersion = $WindowsVersionParts -join "."
$VersionTuple = ($WindowsVersionParts | ForEach-Object { $_.ToString() }) -join ", "
$AppPublisher = $env:BLINK_TRACKER_PUBLISHER
if ([string]::IsNullOrWhiteSpace($AppPublisher)) {
  if (-not [string]::IsNullOrWhiteSpace($RepositoryOwner)) {
    $AppPublisher = $RepositoryOwner
  } else {
    $AppPublisher = $AppName
  }
}
$AppPublisherUrl = $env:BLINK_TRACKER_PUBLISHER_URL
if ([string]::IsNullOrWhiteSpace($AppPublisherUrl)) {
  $AppPublisherUrl = $RepositoryUrl
}
$AppSupportUrl = $env:BLINK_TRACKER_SUPPORT_URL
if ([string]::IsNullOrWhiteSpace($AppSupportUrl)) {
  $AppSupportUrl = $RepositoryUrl
}
$AppUpdatesUrl = $env:BLINK_TRACKER_UPDATES_URL
if ([string]::IsNullOrWhiteSpace($AppUpdatesUrl)) {
  if ([string]::IsNullOrWhiteSpace($RepositoryUrl)) {
    $AppUpdatesUrl = $null
  } else {
    $AppUpdatesUrl = "$RepositoryUrl/releases"
  }
}
$AppDescription = $env:BLINK_TRACKER_FILE_DESCRIPTION
if ([string]::IsNullOrWhiteSpace($AppDescription)) {
  $AppDescription = "Blink Tracker webcam app for blink counting and dry-eye reminders"
}
$AppCopyright = $env:BLINK_TRACKER_COPYRIGHT
if ([string]::IsNullOrWhiteSpace($AppCopyright)) {
  $AppCopyright = "Copyright (c) $(Get-Date -Format yyyy) $AppPublisher"
}

$SigningConfig = Get-SigningConfig
if (-not $SigningConfig) {
  Write-Warning "No code-signing certificate configured. Windows may still show 'Unknown publisher' for unsigned EXE or Setup.exe files."
}

$VersionPublisher = Escape-PythonVersionString -Value $AppPublisher
$VersionDescription = Escape-PythonVersionString -Value $AppDescription
$VersionCopyright = Escape-PythonVersionString -Value $AppCopyright
$VersionAppName = Escape-PythonVersionString -Value $AppName
$VersionAppVersion = Escape-PythonVersionString -Value $AppVersion
$VersionExeName = Escape-PythonVersionString -Value $AppExeName

New-Item -ItemType Directory -Force -Path "build" | Out-Null
$VersionInfoPath = "build\windows-version-info.txt"
@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($VersionTuple),
    prodvers=($VersionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          "040904B0",
          [
            StringStruct("CompanyName", "$VersionPublisher"),
            StringStruct("FileDescription", "$VersionDescription"),
            StringStruct("FileVersion", "$VersionAppVersion"),
            StringStruct("InternalName", "BlinkTracker"),
            StringStruct("LegalCopyright", "$VersionCopyright"),
            StringStruct("OriginalFilename", "$VersionExeName"),
            StringStruct("ProductName", "$VersionAppName"),
            StringStruct("ProductVersion", "$VersionAppVersion")
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct("Translation", [1033, 1200])])
  ]
)
"@ | Set-Content $VersionInfoPath -Encoding utf8

$PyInstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "BlinkTracker",
  "--version-file", $VersionInfoPath,
  "--hidden-import", "mediapipe",
  "--collect-data", "mediapipe"
)

$WindowsIconPath = "scripts\release\windows\BlinkTracker.ico"
$WindowsPngPath = "scripts\release\windows\BlinkTracker.png"
$LinuxSvgPath = "scripts\release\linux\BlinkTracker.svg"
$IconScriptPath = "scripts\release\windows\make_ico_from_svg.py"

if (Test-Path $WindowsPngPath) {
  if (Test-Path $IconScriptPath) {
    & $PythonExe $IconScriptPath --png $WindowsPngPath --out $WindowsIconPath
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Icon generation failed (exit code $LASTEXITCODE) - building without an EXE icon."
    }
  } else {
    Write-Host "Icon generator script not found at '$IconScriptPath' - building without an EXE icon."
  }
} elseif (Test-Path $LinuxSvgPath) {
  if (Test-Path $IconScriptPath) {
    & $PythonExe $IconScriptPath --svg $LinuxSvgPath --out $WindowsIconPath
    if ($LASTEXITCODE -ne 0) {
      Write-Host "Icon generation failed (exit code $LASTEXITCODE) - building without an EXE icon."
    }
  } else {
    Write-Host "Icon generator script not found at '$IconScriptPath' - building without an EXE icon."
  }
} else {
  Write-Host "Source PNG not found at '$WindowsPngPath' and SVG not found at '$LinuxSvgPath' - building without an EXE icon."
}

if (Test-Path $WindowsIconPath) {
  $PyInstallerArgs += @("--icon", $WindowsIconPath)
}

Write-Host "Building $AppName $AppVersion"
Write-Host "Publisher: $AppPublisher"
if (-not [string]::IsNullOrWhiteSpace($AppPublisherUrl)) {
  Write-Host "Publisher URL: $AppPublisherUrl"
}

& $PythonExe -m PyInstaller @PyInstallerArgs main.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed (exit code $LASTEXITCODE)."
}

New-Item -ItemType Directory -Force -Path "dist\release" | Out-Null

$ReleaseOutputPath = $null
if (Test-Path "dist\BlinkTracker") {
  Copy-Item -Path "dist\BlinkTracker" -Destination "dist\release\BlinkTracker" -Recurse -Force
  $ReleaseOutputPath = "dist\release\BlinkTracker"
} elseif (Test-Path "dist\BlinkTracker.exe") {
  Copy-Item -Path "dist\BlinkTracker.exe" -Destination "dist\release\BlinkTracker.exe" -Force
  $ReleaseOutputPath = "dist\release\BlinkTracker.exe"
} else {
  throw "PyInstaller did not produce 'dist\\BlinkTracker\\' or 'dist\\BlinkTracker.exe'. Check the build output for errors."
}

$ReleaseExePath = $null
if ($ReleaseOutputPath -like "*BlinkTracker.exe") {
  $ReleaseExePath = $ReleaseOutputPath
  Write-Host "PyInstaller output staged at dist\\release\\BlinkTracker.exe"
} else {
  $ReleaseExePath = Join-Path $ReleaseOutputPath $AppExeName
  Write-Host "PyInstaller output staged at dist\\release\\BlinkTracker\\BlinkTracker.exe"
}

Sign-ReleaseBinary -Path $ReleaseExePath -SigningConfig $SigningConfig

$InnoScriptPath = "scripts\release\windows\BlinkTracker.iss"
$IsccExe = $null
$IsccCommand = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
if ($IsccCommand) {
  $IsccExe = $IsccCommand.Source
} else {
  $IsccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
  )
  if ($env:LOCALAPPDATA) {
    $IsccCandidates += Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
  }
  foreach ($candidate in $IsccCandidates) {
    if (Test-Path $candidate) {
      $IsccExe = $candidate
      break
    }
  }
}

if ($IsccExe -and (Test-Path $InnoScriptPath)) {
  $InnoArgs = @(
    "/DAppName=$AppName",
    "/DAppVersion=$AppVersion",
    "/DAppVersionNumeric=$WindowsVersion",
    "/DAppPublisher=$AppPublisher",
    "/DAppExeName=$AppExeName",
    "/DAppPublisherURL=$AppPublisherUrl",
    "/DAppSupportURL=$AppSupportUrl",
    "/DAppUpdatesURL=$AppUpdatesUrl",
    "/DAppDescription=$AppDescription",
    "/DAppCopyright=$AppCopyright",
    $InnoScriptPath
  )

  & $IsccExe @InnoArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed (exit code $LASTEXITCODE)."
  }

  if (Test-Path "dist\release\BlinkTrackerSetup.exe") {
    Sign-ReleaseBinary -Path "dist\release\BlinkTrackerSetup.exe" -SigningConfig $SigningConfig
    Write-Host "Installer staged at dist\\release\\BlinkTrackerSetup.exe"
  } else {
    Write-Host "Inno Setup finished; check dist\\release for the installer."
  }
} else {
  Write-Host "Inno Setup not found or script missing. Install Inno Setup to build a Setup.exe."
}

exit 0
