#!/usr/bin/env bash
# Bundle the REAL upstream tar1090 web application and public aircraft metadata
# into the Flight Radar static Pages artifact. Runs in GitHub Actions, not on
# the viewer's computer. GPL-2.0-or-later source/attribution is retained.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/tihulu_flight_radar/web/tar1090"
UPSTREAM_COMMIT="5d59b1ba2c5e30eb23f1161940367b7767f10ad5"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
git init -q "$WORK/tar1090"
git -C "$WORK/tar1090" fetch -q --depth=1 https://github.com/wiedehopf/tar1090.git "$UPSTREAM_COMMIT"
git -C "$WORK/tar1090" checkout -q --detach FETCH_HEAD
[[ "$(git -C "$WORK/tar1090" rev-parse HEAD)" == "$UPSTREAM_COMMIT" ]]
mkdir -p "$OUT"
rsync -a --delete \
  --exclude=tihulu-browser-bridge.js \
  "$WORK/tar1090/html/" "$OUT/"
cp "$WORK/tar1090/LICENSE" "$OUT/UPSTREAM-GPL-LICENSE.txt"
printf '%s\n' \
  "tar1090 copyright original authors; source: https://github.com/wiedehopf/tar1090" \
  "Pinned source commit: $UPSTREAM_COMMIT" \
  "GPL-2.0-or-later; license: ./UPSTREAM-GPL-LICENSE.txt" \
  "TIHULU adapter source: ../tar1090-adapter.js" \
  > "$OUT/UPSTREAM-ATTRIBUTION.txt"
# Aircraft metadata: the same open tar1090 database used for type and
# operator/registration details. Static only; no fake aircraft observations.
git clone -q --depth=1 https://github.com/wiedehopf/tar1090-db.git "$WORK/db"
mkdir -p "$OUT/db2"
rsync -a --delete "$WORK/db/db/" "$OUT/db2/"
# Upstream tar1090-db stores several .js JSON shards as GZIP bytes even
# though the filename ends with .js. A static GitHub Pages host does not
# promise Content-Encoding:gzip for those .js paths. Decode at build time.
python3 - "$OUT/db2" <<'PY'
from pathlib import Path
import gzip, sys
root = Path(sys.argv[1])
converted = 0
for file in root.glob("*.js"):
    data = file.read_bytes()
    if data.startswith(bytes([0x1f, 0x8b])):
        file.write_bytes(gzip.decompress(data))
        converted += 1
    # Do not publish compressed files with a JSON suffix.
    if file.read_bytes().startswith(bytes([0x1f, 0x8b])):
        raise SystemExit(f"Unexpanded gzip aircraft database shard: {file}")
print(f"Decompressed {converted} aircraft JSON shards for GitHub Pages.")
PY
printf '%s\n' \
  "Aircraft metadata © tar1090-db contributors, see https://github.com/wiedehopf/tar1090-db" \
  "Metadata is NOT a live air traffic observation." \
  > "$OUT/db2/DATA-SOURCE.txt"
# Keep adapter code maintained in this repo, not in an inaccessible build.
cp "$ROOT/tihulu_flight_radar/web/tar1090-adapter.js" "$OUT/tihulu-browser-bridge.js"
python3 - "$OUT/index.html" <<'PY'
from pathlib import Path
import sys
file = Path(sys.argv[1])
html = file.read_text()
jq = '<script src="libs/jquery-3.6.1.min.js"></script>'
assert html.count(jq) == 1, 'tar1090 upstream jQuery markup changed'
# Register the JSON AJAX transport before tar1090's early startup scripts.
html = html.replace(jq, jq + '\n    <script src="tihulu-browser-bridge.js"></script>')
file.write_text(html)
PY
test -s "$OUT/index.html"
test -s "$OUT/planeObject.js"
test -s "$OUT/db2/operators.js"
test -s "$OUT/tihulu-browser-bridge.js"
echo "Bundled exact GPL tar1090 frontend, aircraft metadata and same-origin live-data bridge."
