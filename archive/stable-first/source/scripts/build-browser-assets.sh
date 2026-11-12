#!/usr/bin/env bash
# GitHub Actions build-time only. The end user needs NO npm, installer,
# Python, local service or CDN; WebUSB code is served by static GitHub Pages.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB="$ROOT/tihulu_flight_radar/web"
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
mkdir -p "$WEB/vendor"
# Exact versions. npm dependencies never install on the viewer's computer.
npm install --prefix "$BUILD" --no-audit --no-fund --no-package-lock \
  --save-exact @jtarrio/webrtlsdr@3.0.7 esbuild@0.25.12
DRIVER="$BUILD/node_modules/@jtarrio/webrtlsdr/dist/rtlsdr.js"
if [[ ! -s "$DRIVER" ]]; then
  echo "Pinned @jtarrio/webrtlsdr browser entrypoint not found: $DRIVER" >&2
  exit 1
fi
"$BUILD/node_modules/.bin/esbuild" "$DRIVER" \
  --bundle --format=esm --platform=browser --target=es2022 \
  --minify --legal-comments=linked \
  --outfile="$WEB/vendor/rtlsdr.mjs"
test -s "$WEB/vendor/rtlsdr.mjs"
# Comply with original Apache-2.0 license and any third-party notices.
if [[ -s "$BUILD/node_modules/@jtarrio/webrtlsdr/LICENSE" ]]; then
  cp "$BUILD/node_modules/@jtarrio/webrtlsdr/LICENSE" "$WEB/vendor/RTLSDR-LICENSE.txt"
else
  printf '%s\n' 'RTL-SDR browser library © Jacobo Tarrio, Apache-2.0' \
    'https://github.com/jtarrio/webrtlsdr/blob/master/LICENSE' \
    > "$WEB/vendor/RTLSDR-LICENSE.txt"
fi
echo "Built static same-origin WebUSB driver; user installs nothing."
