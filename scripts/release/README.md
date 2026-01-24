# Release installers

This folder contains platform-specific scripts to build release installers for
Dry Eye Blink Detector.

## Prerequisites

- Python 3.10+
- `pip install -r requirements.txt`
- `pip install pyinstaller`

PyInstaller notes:

- The scripts include a baseline set of PyInstaller flags to bundle the app icon
  and include MediaPipe as a hidden import.
- If you hit runtime errors (missing Qt plugins or MediaPipe data), add additional
  `--hidden-import` or `--add-data` entries in the platform script.

Platform-specific dependencies:

- **Windows:** Inno Setup 6 is optional if you want a `Setup.exe` installer.
- **macOS:** `hdiutil` (ships with macOS).
- **Linux (AppImage):**
  - `appimagetool` (https://github.com/AppImage/AppImageKit)
  - `linuxdeploy` (https://github.com/linuxdeploy/linuxdeploy)
  - `patchelf` and `desktop-file-utils` recommended by linuxdeploy.

## Build outputs

The scripts emit installers into `dist/release`:

- Windows: `dist/release/DryEyeBlink/` (folder containing `DryEyeBlink.exe`), plus `dist/release/DryEyeBlinkSetup.exe` if Inno Setup is installed
- macOS: `dist/release/DryEyeBlink.dmg`
- Linux: `dist/release/DryEyeBlink.AppImage`

## Usage

Run the script that matches your operating system:

```powershell
# Windows (PowerShell)
.\scripts\release\build_windows.ps1

# macOS (bash/zsh)
./scripts/release/build_macos.sh

# Linux (bash)
./scripts/release/build_linux_appimage.sh
```

## Windows icon note

Windows executables require an `.ico` file for `--icon`. If a PNG exists at
`scripts/release/windows/DryEyeBlink.png`, the Windows build script renders it
to `scripts/release/windows/DryEyeBlink.ico` automatically (using `PySide6`).
Otherwise it falls back to the SVG at `scripts/release/linux/DryEyeBlink.svg`.

If you see a "permission denied" error when running the `.sh` scripts, either:

- Make them executable once:

  ```bash
  chmod +x scripts/release/build_macos.sh scripts/release/build_linux_appimage.sh
Each script cleans previous `build/` and `dist/` directories before rebuilding.

## Verification note

These scripts must be executed on their target platforms (Windows/macOS/Linux)
with the required tooling available. They are not validated automatically in this
repository; run the commands above on the appropriate OS to confirm the installers
build correctly.
