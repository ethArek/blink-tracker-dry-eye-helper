$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $scriptDir "..\..")

if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

$PyInstallerArgs = @(
  "--noconfirm",
  "--windowed",
  "--name", "DryEyeBlink",
  "--icon", "scripts\\release\\linux\\DryEyeBlink.svg",
  "--add-data", "scripts\\release\\linux\\DryEyeBlink.svg;scripts\\release\\linux",
  "--hidden-import", "mediapipe"
)

python -m pyinstaller @PyInstallerArgs main.py

New-Item -ItemType Directory -Force -Path "dist\release" | Out-Null
Copy-Item -Path "dist\DryEyeBlink.exe" -Destination "dist\release\DryEyeBlink.exe" -Force

Write-Host "Installer staged at dist\\release\\DryEyeBlink.exe"
