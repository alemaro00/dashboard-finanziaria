#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
VENV_DIR="$PROJECT_DIR/.venv"
APP_DIR="$PROJECT_DIR/dist/Dashboard Finanziaria.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
IBAPI_DIR="$("$VENV_DIR/bin/python" -c 'import pathlib, ibapi; print(pathlib.Path(ibapi.__file__).parent)')"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

CLANG_MODULE_CACHE_PATH="$PROJECT_DIR/.build/module-cache" /usr/bin/clang \
  -fobjc-arc \
  -framework Cocoa \
  -framework WebKit \
  "$PROJECT_DIR/macos/DashboardFinanziaria.m" \
  -o "$MACOS_DIR/DashboardFinanziaria"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>it</string>
  <key>CFBundleDisplayName</key><string>Dashboard Finanziaria</string>
  <key>CFBundleExecutable</key><string>DashboardFinanziaria</string>
  <key>CFBundleIdentifier</key><string>it.alemaro.dashboard-finanziaria</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>Dashboard Finanziaria</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

rm -rf "$RESOURCES_DIR/runtime"
mkdir -p "$RESOURCES_DIR/runtime/python"
cp "$PROJECT_DIR/ibkr_paper_bridge.py" "$RESOURCES_DIR/runtime/"
cp "$PROJECT_DIR/salary-planner-react.html" "$RESOURCES_DIR/runtime/"
cp -R "$IBAPI_DIR" "$RESOURCES_DIR/runtime/python/"
/usr/bin/codesign --force --deep --sign - "$APP_DIR"

echo "$APP_DIR"
