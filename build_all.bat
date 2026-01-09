@echo off
REM Build script for Dry Eye Blink Detector Windows installer
REM This script runs both the executable build and MSI build steps

echo ========================================================================
echo Building Dry Eye Blink Detector for Windows
echo ========================================================================
echo.

REM Step 1: Build the executable
echo Step 1/2: Building standalone executable...
echo.
python build_windows.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================================
    echo ERROR: Failed to build executable
    echo ========================================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================================
echo Executable build complete!
echo ========================================================================
echo.
timeout /t 3 /nobreak >nul

REM Step 2: Build the MSI installer
echo Step 2/2: Building MSI installer...
echo.
python build_msi.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================================
    echo ERROR: Failed to build MSI installer
    echo ========================================================================
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ========================================================================
echo SUCCESS! Build complete!
echo ========================================================================
echo.
echo The installer is ready:
echo   - DryEyeBlinkDetectorSetup.msi
echo.
echo You can now distribute this MSI file to users.
echo.
pause
