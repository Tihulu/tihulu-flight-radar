#!/bin/sh
set -eu
ARCH="${DEB_ARCH:-amd64}"
NAME="tihulu-flight-radar_0.3.2.dev4_${ARCH}.deb"
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
cat > "$STAGE/DEBIAN/control" <<EOF
Package: tihulu-flight-radar
Version: 0.3.2~dev4
Section: hamradio
Priority: optional
Architecture: ${ARCH}
Maintainer: Tihulu Project
Depends: sudo, libc6, libstdc++6, libegl1, libgl1, libdrm2, libgbm1, libx11-6, libx11-xcb1, libxcomposite1, libxdamage1, libxext6, libxfixes3, libxrandr2, libxtst6, libasound2t64, libbrotli1, libdbus-1-3, libexpat1, libfontconfig1, libfreetype6, libglib2.0-0, libgssapi-krb5-2, libnspr4, libnss3, libudev1, libxcb1, libxcb-cursor0, libxcb-dri3-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-util1, libxcb-xfixes0, libxcb-xkb1, libxkbcommon0, libxkbcommon-x11-0, libxkbfile1, libxshmfence1, zlib1g, libzstd1, libsnappy1v5, libopus0, liblcms2-2, libminizip1t64, libwebp7, libwebpdemux2, libwebpmux3
Description: Local-first ADS-B and Mode S aircraft monitor
 English-language receiver dashboard with local map and real JSON export.
 The ADS-B decoder and RTL-SDR drivers are installed separately.
EOF
dpkg-deb --root-owner-group --build "$STAGE" "dist/$NAME"
echo "Created dist/$NAME"
