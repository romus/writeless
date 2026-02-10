#!/bin/bash
set -e

echo "==> Cleaning previous build..."
rm -rf build dist

echo "==> Building Write Less.app with py2app..."
python setup.py py2app

echo "==> Creating DMG..."
rm -rf dmg_temp
mkdir -p dmg_temp
cp -R "dist/Write Less.app" dmg_temp/
hdiutil create -volname "Write Less" -srcfolder dmg_temp -ov -format UDZO "Write Less.dmg"
rm -rf dmg_temp

echo "==> Done! Write Less.dmg is ready."
