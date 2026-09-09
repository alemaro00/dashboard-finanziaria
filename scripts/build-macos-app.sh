#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
VENV_DIR="$PROJECT_DIR/.venv"
APP_DIR="$PROJECT_DIR/dist/Dashboard Finanziaria.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"
IBAPI_DIR="$("$VENV_DIR/bin/python" -c 'import pathlib, ibapi; print(pathlib.Path(ibapi.__file__).parent)')"
ICON_SOURCE="$PROJECT_DIR/assets/dashboard-app-icon-source.png"
ICONSET_DIR="$PROJECT_DIR/.build/AppIcon.iconset"

mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"

render_icon() {
  /usr/bin/sips -z "$1" "$1" "$ICON_SOURCE" --out "$ICONSET_DIR/$2" >/dev/null
}

render_icon 16 icon_16x16.png
render_icon 32 icon_16x16@2x.png
render_icon 32 icon_32x32.png
render_icon 64 icon_32x32@2x.png
render_icon 128 icon_128x128.png
render_icon 256 icon_128x128@2x.png
render_icon 256 icon_256x256.png
render_icon 512 icon_256x256@2x.png
render_icon 512 icon_512x512.png
render_icon 1024 icon_512x512@2x.png
ICON_FILE="$RESOURCES_DIR/AppIcon.icns"
ICON_BUILD="$PROJECT_DIR/.build/AppIcon.icns"
if /usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$ICON_BUILD"; then
  cp "$ICON_BUILD" "$ICON_FILE"
elif [[ -f "$ICON_FILE" ]]; then
  print -u2 "Avviso: iconutil non ha rigenerato l'icona; mantengo l'icona esistente."
else
  print -u2 "Errore: impossibile creare AppIcon.icns e non esiste un'icona precedente."
  exit 1
fi

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
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>Dashboard Finanziaria</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.5</string>
  <key>CFBundleVersion</key><string>6</string>
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
