#!/usr/bin/env bash
# ARM64 (Raspberry Pi 5) build — RUN ON THE PI, not cross-compiled.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
python3 -m venv .venv-arm && . .venv-arm/bin/activate
python -m pip install --disable-pip-version-check "PySide6==6.12.0" "PySide6-Addons==6.12.0" "PySide6-Essentials==6.12.0" "PySide6-WebEngine==6.12.0.140" pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --onedir --name TihuluFlightRadar --collect-data tihulu_flight_radar --paths . tihulu_flight_radar/launcher.py
mkdir -p AppDir/usr/bin AppDir/usr/share/applications
cp -a dist/TihuluFlightRadar/. AppDir/usr/bin/
install -m 0644 packaging/linux/tihulu-flight-radar.desktop AppDir/tihulu-flight-radar.desktop
install -m 0644 packaging/linux/tihulu-flight-radar.svg AppDir/tihulu-flight-radar.svg
printf '#!/bin/sh\nexec "$(dirname "$0")/usr/bin/TihuluFlightRadar" "$@"\n' > AppDir/AppRun
chmod +x AppDir/AppRun
curl -sSLo appimagetool "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-aarch64.AppImage"
chmod +x appimagetool
ARCH=aarch64 ./appimagetool --no-appstream AppDir Tihulu_Flight_Radar-aarch64.AppImage
echo "Created Tihulu_Flight_Radar-aarch64.AppImage (verify on real Pi 5 hardware)"
