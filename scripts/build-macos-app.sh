#!/bin/zsh

set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
INSTALL_DIR="/Applications/Beta Dashboard Finanziaria.app"
APP_VERSION="1.14.0"
APP_BUILD="61"
# Beta releases update only the separately installed beta application.
if [[ -f "$INSTALL_DIR/Contents/Info.plist" ]]; then
  INSTALLED_BUILD=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$INSTALL_DIR/Contents/Info.plist")
  if (( APP_BUILD <= INSTALLED_BUILD )); then
    if /usr/bin/codesign --verify --deep --strict "$INSTALL_DIR" 2>/dev/null; then
      print -u2 "Incrementare APP_VERSION e APP_BUILD prima di pubblicare un aggiornamento (installata build $INSTALLED_BUILD)."
      exit 1
    fi
    print -u2 "Riparo l'installazione incompleta della build $INSTALLED_BUILD."
  fi
fi
VENV_DIR="$PROJECT_DIR/.venv"
"${NODE_BIN:-node}" "$PROJECT_DIR/scripts/build-web.cjs"
APP_DIR="$PROJECT_DIR/dist/Beta Dashboard Finanziaria.app"
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
elif [[ -f "$INSTALL_DIR/Contents/Resources/AppIcon.icns" ]]; then
  cp "$INSTALL_DIR/Contents/Resources/AppIcon.icns" "$ICON_FILE"
else
  print -u2 "Errore: impossibile creare AppIcon.icns e non esiste un'icona precedente."
  exit 1
fi

CLANG_MODULE_CACHE_PATH="$PROJECT_DIR/.build/module-cache" /usr/bin/clang \
  -fobjc-arc -arch arm64 -mmacosx-version-min=13.0 \
  -framework Cocoa \
  -framework WebKit \
  "$PROJECT_DIR/macos/DashboardFinanziaria.m" \
  -o "$MACOS_DIR/BetaDashboardFinanziaria"

cat > "$CONTENTS_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key><string>it</string>
  <key>CFBundleDisplayName</key><string>Beta Dashboard Finanziaria</string>
  <key>CFBundleExecutable</key><string>BetaDashboardFinanziaria</string>
  <key>CFBundleIdentifier</key><string>it.alemaro.dashboard-finanziaria.beta</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>CFBundleName</key><string>Beta Dashboard Finanziaria</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.11.2</string>
  <key>CFBundleVersion</key><string>21</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$CONTENTS_DIR/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_BUILD" "$CONTENTS_DIR/Info.plist"

rm -rf "$RESOURCES_DIR/runtime"
mkdir -p "$RESOURCES_DIR/runtime/python"
cp "$PROJECT_DIR/ibkr_paper_bridge.py" "$PROJECT_DIR/local_security.py" "$PROJECT_DIR/enable_banking_sync.py" "$RESOURCES_DIR/runtime/"
cp -R "$PROJECT_DIR/web-build" "$RESOURCES_DIR/runtime/"
mkdir -p "$RESOURCES_DIR/runtime/vendor"
cp "$PROJECT_DIR/vendor/react-18.3.1.min.js" "$PROJECT_DIR/vendor/react-dom-18.3.1.min.js" "$PROJECT_DIR/vendor/REACT-LICENSE.txt" "$RESOURCES_DIR/runtime/vendor/"
cp "$PROJECT_DIR/salary-planner-react.html" "$RESOURCES_DIR/runtime/"
cp -R "$IBAPI_DIR" "$RESOURCES_DIR/runtime/python/"
/usr/bin/codesign --force --deep --sign - "$APP_DIR"
/usr/bin/codesign --verify --deep --strict "$APP_DIR"

# Close the running app normally before executing this installer.
if /usr/bin/pgrep -x BetaDashboardFinanziaria >/dev/null; then
  print -u2 "Chiudere Beta Dashboard Finanziaria prima di sostituire l'app."
  exit 1
fi
INSTALL_STAGING="/Applications/.Beta-Dashboard-Finanziaria-update.app"
rm -rf "$INSTALL_STAGING"
/usr/bin/ditto "$APP_DIR" "$INSTALL_STAGING"
rm -rf "$INSTALL_DIR"
mv "$INSTALL_STAGING" "$INSTALL_DIR"
/usr/bin/codesign --verify --deep --strict "$INSTALL_DIR"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP_DIR" "$PROJECT_DIR/dist/Beta-Dashboard-Finanziaria-$APP_VERSION-build$APP_BUILD.zip"
rm -rf "$APP_DIR"

echo "$INSTALL_DIR — versione $APP_VERSION, build $APP_BUILD"
