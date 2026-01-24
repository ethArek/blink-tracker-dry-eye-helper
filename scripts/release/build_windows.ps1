$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "..\..")

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "BlinkTracker.spec") { Remove-Item -Force "BlinkTracker.spec" }

$PythonExe = "python"
if (Test-Path ".venv\\Scripts\\python.exe") {
  $PythonExe = ".venv\\Scripts\\python.exe"
}

$null = & $PythonExe -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller is not installed for '$PythonExe'. Install it with: pip install pyinstaller (in the same environment), then rerun."
}

$PyInstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "BlinkTracker",
  "--hidden-import", "mediapipe"
)

$WindowsIconPath = "scripts\\release\\windows\\BlinkTracker.ico"
$WindowsPngPath = "scripts\\release\\windows\\BlinkTracker.png"
$LinuxSvgPath = "scripts\\release\\linux\\BlinkTracker.svg"
$IconScriptPath = "scripts\\release\\windows\\make_ico_from_svg.py"

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

& $PythonExe -m PyInstaller @PyInstallerArgs main.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed (exit code $LASTEXITCODE)."
}

New-Item -ItemType Directory -Force -Path "dist\release" | Out-Null

$ReleaseOutputPath = $null
if (Test-Path "dist\\BlinkTracker") {
  Copy-Item -Path "dist\\BlinkTracker" -Destination "dist\\release\\BlinkTracker" -Recurse -Force
  $ReleaseOutputPath = "dist\\release\\BlinkTracker"
} elseif (Test-Path "dist\\BlinkTracker.exe") {
  Copy-Item -Path "dist\\BlinkTracker.exe" -Destination "dist\\release\\BlinkTracker.exe" -Force
  $ReleaseOutputPath = "dist\\release\\BlinkTracker.exe"
} else {
  throw "PyInstaller did not produce 'dist\\BlinkTracker\\' or 'dist\\BlinkTracker.exe'. Check the build output for errors."
}

if ($ReleaseOutputPath -like "*BlinkTracker.exe") {
  Write-Host "PyInstaller output staged at dist\\release\\BlinkTracker.exe"
} else {
  Write-Host "PyInstaller output staged at dist\\release\\BlinkTracker\\BlinkTracker.exe"
}

$InnoScriptPath = "scripts\\release\\windows\\BlinkTracker.iss"
$IsccExe = $null
$IsccCommand = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
if ($IsccCommand) {
  $IsccExe = $IsccCommand.Source
} else {
  $IsccCandidates = @(
    "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe",
    "C:\\Program Files\\Inno Setup 6\\ISCC.exe"
  )
  foreach ($candidate in $IsccCandidates) {
    if (Test-Path $candidate) {
      $IsccExe = $candidate
      break
    }
  }
}

if ($IsccExe -and (Test-Path $InnoScriptPath)) {
  & $IsccExe $InnoScriptPath
  if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup build failed (exit code $LASTEXITCODE)."
  }

  if (Test-Path "dist\\release\\BlinkTrackerSetup.exe") {
    Write-Host "Installer staged at dist\\release\\BlinkTrackerSetup.exe"
  } else {
    Write-Host "Inno Setup finished; check dist\\release for the installer."
  }
} else {
  Write-Host "Inno Setup not found or script missing. Install Inno Setup to build a Setup.exe."
}

exit 0
