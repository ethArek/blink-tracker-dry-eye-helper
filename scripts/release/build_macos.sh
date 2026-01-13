#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT_DIR"

if ! command -v hdiutil >/dev/null 2>&1; then
  echo "hdiutil is required to build a DMG on macOS." >&2
  exit 1
fi

rm -rf build dist

python -m pyinstaller --noconfirm --windowed --name "DryEyeBlink" main.py

mkdir -p dist/release
hdiutil create \
  -volname "Dry Eye Blink" \
  -srcfolder "dist/DryEyeBlink.app" \
  -ov \
  -format UDZO \
  "dist/release/DryEyeBlink.dmg"

echo "Installer staged at dist/release/DryEyeBlink.dmg"
