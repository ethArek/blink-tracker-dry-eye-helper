# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Dry Eye Blink Detector.
This file configures how PyInstaller builds the standalone executable.

To build the executable, run:
    pyinstaller DryEyeBlinkDetector.spec
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect MediaPipe data files
mediapipe_datas = collect_data_files('mediapipe')

# Collect all mediapipe submodules
mediapipe_hidden_imports = collect_submodules('mediapipe')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=mediapipe_datas,
    hiddenimports=[
        'mediapipe',
        'cv2',
        'numpy',
        'sqlite3',
        'winsound',  # Windows audio support
    ] + mediapipe_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'PIL',
        'pandas',
        'scipy',
        'torch',
        'tensorflow',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DryEyeBlinkDetector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to False to hide console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='icon.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DryEyeBlinkDetector',
)
