#!/bin/bash
set -e

WITH_DMG=false
for arg in "$@"; do
  [ "$arg" = "--dmg" ] && WITH_DMG=true
done

BUILD_ROOT="build"
PY2APP_BUILD_DIR="$BUILD_ROOT/py2app"
DIST_DIR="$BUILD_ROOT/dist"
TEMP_DIR="$BUILD_ROOT/temp_"

if [ ! -d ".venv" ]; then
  echo "==> Creating virtual environment..."
  python3 -m venv .venv
fi

VENV_PYTHON=$(.venv/bin/python3 --version 2>/dev/null | awk '{print $2}')
SYSTEM_PYTHON=$(python3 --version 2>/dev/null | awk '{print $2}')

if [ "$VENV_PYTHON" != "$SYSTEM_PYTHON" ]; then
  echo "==> Python version mismatch (venv: $VENV_PYTHON, system: $SYSTEM_PYTHON). Recreating venv..."
  rm -rf .venv
  python3 -m venv .venv
fi

source .venv/bin/activate

# Avoid macOS metadata copy issues (xattrs/resource forks) during build/copy steps.
export COPYFILE_DISABLE=1

echo "==> Installing dependencies..."
pip install -r requirements.txt

echo "==> Cleaning previous build..."
# Best-effort cleanup of sticky flags/ACL/xattrs from previous failed runs.
if [ -e "$BUILD_ROOT" ]; then
  chflags -R nouchg,noschg "$BUILD_ROOT" 2>/dev/null || true
  chmod -R u+rwX "$BUILD_ROOT" 2>/dev/null || true
  xattr -rc "$BUILD_ROOT" 2>/dev/null || true
fi
rm -rf "$BUILD_ROOT"

echo "==> Building Write Less.app with py2app..."
python3 setup.py py2app --bdist-base="$PY2APP_BUILD_DIR" --dist-dir="$DIST_DIR"

if ! $WITH_DMG; then
  echo "==> Done! $DIST_DIR/Write Less.app is ready."
  exit 0
fi

echo "==> Creating DMG..."
mkdir -p "$TEMP_DIR"

restore_app() {
  if [ -d "$TEMP_DIR/Write Less.app" ] && [ ! -d "$DIST_DIR/Write Less.app" ]; then
    mv "$TEMP_DIR/Write Less.app" "$DIST_DIR/"
  fi
}

trap restore_app EXIT
mv "$DIST_DIR/Write Less.app" "$TEMP_DIR/"
hdiutil create -volname "Write Less" -srcfolder "$TEMP_DIR" -ov -format UDZO "$DIST_DIR/Write Less.dmg"
mv "$TEMP_DIR/Write Less.app" "$DIST_DIR/"
rm -rf "$TEMP_DIR"
trap - EXIT

echo "==> Done! $DIST_DIR/Write Less.dmg is ready."
