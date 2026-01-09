#!/usr/bin/env python3
"""
Build script for creating a standalone Windows executable using PyInstaller.

This script automates the process of building the Dry Eye Blink Detector
into a standalone Windows application.

Usage:
    python build_windows.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    """Build the Windows executable using PyInstaller."""
    print("=" * 70)
    print("Building Dry Eye Blink Detector for Windows")
    print("=" * 70)
    
    # Check if we're on Windows
    if sys.platform != "win32":
        print("\n⚠️  Warning: This script is designed for Windows builds.")
        print("   Building on a non-Windows platform may result in errors.")
        response = input("   Do you want to continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Build cancelled.")
            return 1
    
    # Get the project root directory
    project_root = Path(__file__).parent.absolute()
    spec_file = project_root / "DryEyeBlinkDetector.spec"
    
    print(f"\nProject root: {project_root}")
    print(f"Spec file: {spec_file}")
    
    # Check if spec file exists
    if not spec_file.exists():
        print(f"\n❌ Error: Spec file not found: {spec_file}")
        return 1
    
    # Clean previous build artifacts
    print("\n🧹 Cleaning previous build artifacts...")
    dirs_to_clean = ["build", "dist"]
    for dir_name in dirs_to_clean:
        dir_path = project_root / dir_name
        if dir_path.exists():
            print(f"   Removing {dir_path}")
            shutil.rmtree(dir_path)
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"\n✓ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("\n❌ Error: PyInstaller is not installed.")
        print("   Please install it with: pip install pyinstaller")
        return 1
    
    # Check if required dependencies are installed
    print("\n📦 Checking dependencies...")
    required_packages = ['mediapipe', 'cv2', 'numpy']
    missing_packages = []
    
    for package in required_packages:
        try:
            if package == 'cv2':
                import cv2
                print(f"   ✓ opencv-python: {cv2.__version__}")
            elif package == 'mediapipe':
                import mediapipe
                print(f"   ✓ mediapipe: {mediapipe.__version__}")
            elif package == 'numpy':
                import numpy
                print(f"   ✓ numpy: {numpy.__version__}")
        except ImportError:
            missing_packages.append(package)
            print(f"   ❌ {package}: not installed")
    
    if missing_packages:
        print("\n❌ Error: Missing required packages.")
        print("   Please install them with: pip install -r requirements.txt")
        return 1
    
    # Run PyInstaller
    print("\n🔨 Building executable with PyInstaller...")
    print("   This may take several minutes...\n")
    
    try:
        result = subprocess.run(
            ["pyinstaller", "--clean", str(spec_file)],
            cwd=project_root,
            check=True
        )
        
        print("\n✅ Build completed successfully!")
        
        # Check if executable was created
        exe_path = project_root / "dist" / "DryEyeBlinkDetector" / "DryEyeBlinkDetector.exe"
        if exe_path.exists():
            exe_size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"\n📦 Executable created: {exe_path}")
            print(f"   Size: {exe_size_mb:.2f} MB")
            print(f"\n   The executable and all required files are in:")
            print(f"   {exe_path.parent}")
        else:
            print(f"\n⚠️  Warning: Expected executable not found at {exe_path}")
        
        return 0
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with error code {e.returncode}")
        return 1
    except FileNotFoundError:
        print("\n❌ Error: PyInstaller command not found.")
        print("   Please ensure PyInstaller is installed and in your PATH.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
