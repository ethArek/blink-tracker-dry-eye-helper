#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

LINUXDEPLOY=${LINUXDEPLOY:-linuxdeploy}
APPIMAGETOOL=${APPIMAGETOOL:-appimagetool}

if ! command -v "$LINUXDEPLOY" >/dev/null 2>&1; then
  echo "linuxdeploy is required (set LINUXDEPLOY to its path)." >&2
  exit 1
fi

if ! command -v "$APPIMAGETOOL" >/dev/null 2>&1; then
  echo "appimagetool is required (set APPIMAGETOOL to its path)." >&2
  exit 1
fi

rm -rf build dist

python -m pyinstaller \
  --noconfirm \
  --name "BlinkTracker" \
  --onedir \
  --icon "scripts/release/linux/BlinkTracker.svg" \
  --add-data "scripts/release/linux/BlinkTracker.svg:scripts/release/linux" \
  --hidden-import "mediapipe" \
  main.py

APPDIR="dist/appimage/BlinkTracker.AppDir"
DESKTOP_FILE="scripts/release/linux/BlinkTracker.desktop"
ICON_FILE="scripts/release/linux/BlinkTracker.svg"

rm -rf "$APPDIR"
mkdir -p "dist/release"

"$LINUXDEPLOY" \
  --appdir "$APPDIR" \
  -e "dist/BlinkTracker/BlinkTracker" \
  -d "$DESKTOP_FILE" \
  -i "$ICON_FILE"

"$APPIMAGETOOL" "$APPDIR" "dist/release/BlinkTracker.AppImage"

chmod +x "dist/release/BlinkTracker.AppImage"

echo "Installer staged at dist/release/BlinkTracker.AppImage"
