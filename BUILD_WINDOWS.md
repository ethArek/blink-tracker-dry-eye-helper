# Building the Windows Installer

This document provides step-by-step instructions for building the Dry Eye Blink Detector Windows installer.

## Overview

The build process consists of two main steps:
1. **Build the executable**: Use PyInstaller to create a standalone `.exe` from the Python application
2. **Build the MSI installer**: Use WiX Toolset to package the executable into a Windows installer

## Prerequisites

### Required Software

1. **Python 3.10 or higher**
   - Download from: https://www.python.org/downloads/
   - Make sure to check "Add Python to PATH" during installation

2. **Git** (optional, for cloning the repository)
   - Download from: https://git-scm.com/downloads/

3. **WiX Toolset 3.11 or higher**
   - Download from: https://wixtoolset.org/releases/
   - Or install via Windows Package Manager: `winget install WiXToolset.WiX`
   - Or install via Chocolatey: `choco install wixtoolset`
   - **Important**: After installation, ensure WiX tools are in your PATH

### Verify Installation

Open a Command Prompt or PowerShell and verify:

```powershell
# Check Python
python --version

# Check PyInstaller (after installing requirements)
pyinstaller --version

# Check WiX Toolset
candle.exe -?
light.exe -?
heat.exe -?
```

## Step 1: Set Up the Development Environment

### Clone the Repository

```powershell
git clone https://github.com/ethArek/dry-eye-blink.git
cd dry-eye-blink
```

### Create a Virtual Environment (Recommended)

```powershell
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate

# On PowerShell, if you get an error about execution policy:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Install Dependencies

```powershell
pip install -r requirements.txt
```

This will install:
- `mediapipe` - Face mesh detection
- `opencv-python` - Computer vision and camera access
- `numpy` - Numerical operations
- `pyinstaller` - Executable builder

## Step 2: Build the Executable

Run the build script:

```powershell
python build_windows.py
```

This script will:
- Check that all dependencies are installed
- Clean previous build artifacts
- Run PyInstaller with the configured spec file
- Create `dist/DryEyeBlinkDetector/DryEyeBlinkDetector.exe`

### What Gets Built

The executable is created in `dist/DryEyeBlinkDetector/` along with all required DLLs and data files. The entire folder is needed for the application to run.

### Build Time

The first build typically takes 5-10 minutes, depending on your system. Subsequent builds are faster.

### Troubleshooting Executable Build

**Problem**: `ImportError` for mediapipe or cv2
- **Solution**: Ensure all dependencies are installed: `pip install -r requirements.txt`

**Problem**: PyInstaller not found
- **Solution**: Install PyInstaller: `pip install pyinstaller`

**Problem**: Build fails with "ModuleNotFoundError"
- **Solution**: The spec file may need to include additional hidden imports. Check the error message and add the missing module to `hiddenimports` in `DryEyeBlinkDetector.spec`.

## Step 3: Test the Executable

Before building the installer, test the executable:

```powershell
cd dist\DryEyeBlinkDetector
.\DryEyeBlinkDetector.exe
```

The application should:
- Open a camera preview window
- Detect your face and blinks
- Display statistics on the right side

Press ESC to close the application.

## Step 4: Build the MSI Installer

Once the executable is working, create the MSI installer:

```powershell
# Return to project root if needed
cd ..\..

# Build the MSI
python build_msi.py
```

This script will:
- Check that WiX Toolset is installed
- Verify the PyInstaller build exists
- Use `heat.exe` to harvest all files from `dist/DryEyeBlinkDetector/`
- Compile the WXS configuration with `candle.exe`
- Link and create the MSI with `light.exe`
- Create `DryEyeBlinkDetectorSetup.msi` in the project root

### What Gets Created

The MSI installer (`DryEyeBlinkDetectorSetup.msi`) includes:
- The application executable and all dependencies
- Start Menu shortcut
- Desktop shortcut (optional during installation)
- Uninstall support via Windows Settings

### Installer Size

The MSI is typically 150-250 MB, depending on the dependencies.

### Troubleshooting MSI Build

**Problem**: WiX tools not found
- **Solution**: Install WiX Toolset and ensure it's in your PATH. You may need to restart your terminal or add the WiX bin directory to PATH manually.

**Problem**: "Cannot find dist/DryEyeBlinkDetector"
- **Solution**: Run `python build_windows.py` first to create the executable.

**Problem**: Light.exe fails with "unresolved reference"
- **Solution**: The WXS file may have incorrect component references. This is usually auto-fixed by the build_msi.py script using heat.exe.

## Step 5: Test the Installer

### Install

1. Double-click `DryEyeBlinkDetectorSetup.msi`
2. Follow the installation wizard
3. Choose installation location (default: `C:\Program Files\DryEyeBlinkDetector\`)
4. Complete the installation

### Verify

1. Check the Start Menu for "Dry Eye Blink Detector"
2. Launch the application from the Start Menu
3. Verify the application runs correctly

### Uninstall

1. Open Windows Settings → Apps → Installed apps
2. Find "Dry Eye Blink Detector"
3. Click Uninstall
4. Verify all files are removed from Program Files

## Customization

### Changing the Version Number

Edit the version in `DryEyeBlinkDetector.wxs`:

```xml
<Product Id="*" 
         Name="Dry Eye Blink Detector" 
         Version="1.0.0.0"
         ...>
```

### Adding an Icon

1. Create or obtain a `.ico` file
2. Place it in the project root (e.g., `icon.ico`)
3. Edit `DryEyeBlinkDetector.spec`:
   ```python
   icon='icon.ico'
   ```
4. Rebuild the executable and MSI

### Customizing the Installer UI

The current installer uses `WixUI_InstallDir`, which is a standard installation dialog. To customize:

1. Read about WiX UI: https://wixtoolset.org/documentation/manual/v3/wixui/
2. Modify the `UIRef` element in `DryEyeBlinkDetector.wxs`

### Code Signing (Optional)

For production releases, you should sign both the executable and the MSI:

1. Obtain a code signing certificate
2. Sign the EXE:
   ```powershell
   signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\DryEyeBlinkDetector\DryEyeBlinkDetector.exe
   ```
3. Sign the MSI:
   ```powershell
   signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com DryEyeBlinkDetectorSetup.msi
   ```

## Automated Build Script

For convenience, you can create a batch file to run both build steps:

**`build_all.bat`**:
```batch
@echo off
echo Building Dry Eye Blink Detector for Windows
echo.

echo Step 1: Building executable...
python build_windows.py
if %ERRORLEVEL% NEQ 0 (
    echo Failed to build executable
    exit /b %ERRORLEVEL%
)

echo.
echo Step 2: Building MSI installer...
python build_msi.py
if %ERRORLEVEL% NEQ 0 (
    echo Failed to build MSI
    exit /b %ERRORLEVEL%
)

echo.
echo Build complete!
echo Installer: DryEyeBlinkDetectorSetup.msi
pause
```

Run it with:
```powershell
build_all.bat
```

## Distribution

Once built, you can distribute `DryEyeBlinkDetectorSetup.msi` to users. They can:

1. Double-click the MSI to install
2. No Python required
3. No command-line usage needed
4. Find the app in their Start Menu

## Continuous Integration

To automate builds in CI/CD (e.g., GitHub Actions), you'll need a Windows runner with:
- Python installed
- Dependencies installed from requirements.txt
- WiX Toolset installed

Example GitHub Actions workflow snippet:

```yaml
- name: Install WiX
  run: |
    choco install wixtoolset

- name: Install Python dependencies
  run: |
    pip install -r requirements.txt

- name: Build executable
  run: |
    python build_windows.py

- name: Build MSI
  run: |
    python build_msi.py

- name: Upload installer
  uses: actions/upload-artifact@v3
  with:
    name: installer
    path: DryEyeBlinkDetectorSetup.msi
```

## Support

If you encounter issues:
1. Check the Troubleshooting sections above
2. Ensure all prerequisites are installed and in PATH
3. Review error messages carefully
4. Open an issue on GitHub with details about your environment and the error

## License

The build process and installer configuration are part of the Dry Eye Blink Detector project. Refer to the project's LICENSE file for terms.
