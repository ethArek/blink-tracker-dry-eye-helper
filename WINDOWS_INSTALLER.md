# Windows Installer for Dry Eye Blink Detector

## For End Users (Non-Technical)

### What is this?
Dry Eye Blink Detector is a free application that uses your webcam to monitor how often you blink. It can help prevent dry eyes when working at a computer by reminding you to blink more frequently.

### How to Install

1. **Download** the installer file: `DryEyeBlinkDetectorSetup.msi`

2. **Double-click** the MSI file to start installation

3. **Follow the wizard**:
   - Click "Next" through the installation screens
   - Choose where to install (default location is fine)
   - Optionally choose to create a desktop shortcut
   - Click "Install"

4. **Launch the app**:
   - Find "Dry Eye Blink Detector" in your Start Menu
   - Or click the desktop shortcut if you created one

5. **Grant camera permission** when prompted (required for the app to work)

### System Requirements

- **Operating System**: Windows 10 or Windows 11
- **Webcam**: Any working webcam
- **Disk Space**: ~250 MB
- **No Python Required**: Everything is included in the installer

### How to Use

1. Launch the application from the Start Menu
2. A window will open showing your camera feed
3. The app automatically detects your face and monitors your blinks
4. Statistics are shown on the right side of the window
5. Press **ESC** or close the window to exit

### Uninstalling

1. Open **Windows Settings** (Windows key + I)
2. Go to **Apps** → **Installed apps**
3. Find "Dry Eye Blink Detector"
4. Click the three dots and select **Uninstall**
5. Confirm the uninstallation

---

## For Developers

If you want to build the installer yourself or modify the application, see [BUILD_WINDOWS.md](BUILD_WINDOWS.md) for detailed instructions.

### Quick Start for Developers

```powershell
# Clone the repository
git clone https://github.com/ethArek/dry-eye-blink.git
cd dry-eye-blink

# Install dependencies
pip install -r requirements.txt

# Build everything (requires WiX Toolset)
build_all.bat
```

This will create:
- `dist/DryEyeBlinkDetector/DryEyeBlinkDetector.exe` - Standalone executable
- `DryEyeBlinkDetectorSetup.msi` - Windows installer

### What's Included

The Windows installer build system includes:

- **PyInstaller configuration** (`DryEyeBlinkDetector.spec`)
  - Builds standalone executable with Python runtime
  - Includes all dependencies (MediaPipe, OpenCV, NumPy)
  - Bundles required data files

- **WiX Toolset configuration** (`DryEyeBlinkDetector.wxs`)
  - Creates professional MSI installer
  - Adds Start Menu and desktop shortcuts
  - Registers with Windows Add/Remove Programs
  - Supports clean uninstallation

- **Build automation scripts**
  - `build_windows.py` - Builds the executable
  - `build_msi.py` - Creates the MSI installer
  - `build_all.bat` - Runs both steps

### Build Requirements

To build the installer yourself:

1. **Python 3.10+**
2. **WiX Toolset 3.11+** (Windows-only)
   - Download: https://wixtoolset.org/releases/
   - Or: `winget install WiXToolset.WiX`

3. **Python dependencies**:
   ```
   pip install -r requirements.txt
   ```

See [BUILD_WINDOWS.md](BUILD_WINDOWS.md) for complete documentation.

### Testing

Before distributing the installer:

1. Build the executable and test it directly
2. Build the MSI and test on a clean Windows VM
3. Test installation, running, and uninstallation
4. Verify shortcuts work correctly
5. Test on both Windows 10 and Windows 11

### Distribution

Once built, distribute `DryEyeBlinkDetectorSetup.msi` to users:

- Upload to GitHub Releases
- Share download link
- No additional files needed - MSI is self-contained

### Code Signing (Recommended for Production)

For production releases, code sign both the executable and MSI:

```powershell
# Sign the executable
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com dist\DryEyeBlinkDetector\DryEyeBlinkDetector.exe

# Sign the MSI
signtool sign /f certificate.pfx /p password /t http://timestamp.digicert.com DryEyeBlinkDetectorSetup.msi
```

This prevents Windows SmartScreen warnings and builds user trust.

## Troubleshooting

### Installation Issues

**Problem**: "Windows protected your PC" message
- **Solution**: Click "More info" then "Run anyway"
- **Better solution**: Code sign the MSI (see above)

**Problem**: Installation fails with error
- **Solution**: Ensure you have administrator privileges
- Try right-click → "Run as administrator"

### Running Issues

**Problem**: App doesn't start from Start Menu
- **Solution**: Check if antivirus is blocking it
- Try running from: `C:\Program Files\DryEyeBlinkDetector\DryEyeBlinkDetector.exe`

**Problem**: Camera doesn't open
- **Solution**: Grant camera permissions in Windows Settings
- Check if another app is using the camera

**Problem**: "MSVCP140.dll missing" error
- **Solution**: Install Visual C++ Redistributable
- Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe

## Support

- **Issues**: https://github.com/ethArek/dry-eye-blink/issues
- **Documentation**: See README.md for app usage details
- **Build docs**: See BUILD_WINDOWS.md for developer info

## License

See LICENSE file in the repository.
