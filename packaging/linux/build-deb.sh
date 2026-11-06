#!/bin/sh
set -eu
NAME=tihulu-flight-radar_0.3.2.dev1_amd64.deb
test -x dist/TihuluFlightRadar/TihuluFlightRadar || {
  echo "PyInstaller executable not found" >&2
  exit 1
}
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/tihulu-flight-radar" \
  "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
  "$STAGE/usr/share/icons/hicolor/scalable/apps" "$STAGE/etc/sudoers.d"
cp -a dist/TihuluFlightRadar "$STAGE/opt/tihulu-flight-radar/"
ln -s /opt/tihulu-flight-radar/TihuluFlightRadar/TihuluFlightRadar \
  "$STAGE/usr/bin/tihulu-flight-radar"
install -m 0644 packaging/linux/tihulu-flight-radar.desktop \
  "$STAGE/usr/share/applications/tihulu-flight-radar.desktop"
install -m 0644 packaging/linux/tihulu-flight-radar.svg \
  "$STAGE/usr/share/icons/hicolor/scalable/apps/tihulu-flight-radar.svg"
install -m 0440 packaging/linux/sudoers.conf \
  "$STAGE/etc/sudoers.d/tihulu-flight-radar"
cat > "$STAGE/DEBIAN/control" <<'EOF'
Package: tihulu-flight-radar
Version: 0.3.2~dev1
Section: hamradio
Priority: optional
Architecture: amd64
Maintainer: Tihulu Project
Depends: sudo, libegl1, libgl1, libglib2.0-0, libxkbcommon0, libxcb-cursor0, libdbus-1-3, libnss3, libnspr4, libxcomposite1, libxdamage1, libxrandr2, libgbm1, libxtst6, libxkbfile1, libasound2, libxss1, libxshmfence1
Description: Local-first ADS-B and Mode S aircraft monitor
 English-language receiver dashboard with local map and real JSON export.
 The ADS-B decoder and RTL-SDR drivers are installed separately.
EOF
dpkg-deb --root-owner-group --build "$STAGE" "dist/$NAME"
echo "Created dist/$NAME"
