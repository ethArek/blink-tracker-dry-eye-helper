#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "hdiutil is required to build a DMG on macOS." >&2
  exit 1
fi

rm -rf build dist

python -m pyinstaller \
  --noconfirm \
  --windowed \
  --name "BlinkTracker" \
  --icon "scripts/release/linux/BlinkTracker.svg" \
  --add-data "scripts/release/linux/BlinkTracker.svg:scripts/release/linux" \
  --hidden-import "mediapipe" \
  main.py

mkdir -p dist/release
hdiutil create \
  -volname "Blink Tracker" \
  -srcfolder "dist/BlinkTracker.app" \
  -ov \
  -format UDZO \
  "dist/release/BlinkTracker.dmg"

echo "Installer staged at dist/release/BlinkTracker.dmg"
