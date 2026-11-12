#!/usr/bin/env bash
# Upgrade the user's Tihulu Flight Radar without modifying receiver services.
set -Eeuo pipefail

if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Debian, Ubuntu and Pop!_OS only." >&2
  exit 1
fi
if [[ "$EUID" == 0 ]]; then
  echo "Run as your regular desktop user, without sudo." >&2
  exit 1
fi
if [[ -z "${HOME:-}" || ! -d "$HOME" ]]; then
  echo "HOME is not a valid user directory." >&2
  exit 1
fi

# Default to stable main after the release. Preview installers explicitly pass
# TIHULU_REF=feature/github-pages-local-bridge-2026-11-06.
ref="${TIHULU_REF:-main}"
if [[ ! "$ref" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || [[ "$ref" == *..* ]]; then
  echo "Invalid repository ref." >&2
  exit 1
fi

echo "Tihulu Flight Radar — install or update from '$ref'"
echo "The existing readsb/tar1090 services, receiver settings and recordings stay untouched."
echo "System packages require sudo. No service-control sudoers grants will be created."
sudo apt-get update
# Ubuntu 24.04 uses libasound2t64; Debian 12 uses libasound2.
if apt-cache show libasound2t64 >/dev/null 2>&1; then
  audio_lib=libasound2t64
else
  audio_lib=libasound2
fi
sudo apt-get install -y --no-install-recommends \
  "$audio_lib" libxss1 libxshmfence1 \
  pipx python3-venv git curl sudo \
  libegl1 libgl1 libxkbcommon0 libxcb-cursor0 libdbus-1-3 libglib2.0-0 \
  libnss3 libnspr4 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libxtst6 libxkbfile1

# pipx --force replaces a previously installed version with the selected ref.
# Do not uninstall first: a failed download must not remove the existing app.
pipx install --force "git+https://github.com/Tihulu/tihulu-flight-radar.git@$ref"

app_binary="$HOME/.local/bin/tihulu-flight-radar"
bridge_binary="$HOME/.local/bin/tihulu-flight-bridge"
classic_binary="$HOME/.local/bin/tihulu-flight-radar-classic"
for binary in "$app_binary" "$bridge_binary" "$classic_binary"; do
  if [[ ! -x "$binary" ]]; then
    echo "Installation incomplete: missing executable $binary" >&2
    exit 1
  fi
done

py="$HOME/.local/share/pipx/venvs/tihulu-flight-radar/bin/python"
# Cache the complete original tar1090 frontend locally for no-antenna operation.
# The desktop's 127.0.0.1 bridge serves these read-only static assets, while
# the parent supplies real Internet/RF data. No readsb, USB or systemd needed.
# If GitHub's optional assets are unavailable, keep the app installed and
# its hosted HTTPS tar1090 fallback remains available.
cache_parent="$HOME/.local/share/tihulu-flight-radar"
mkdir -p "$cache_parent"
tar_cache="$cache_parent/tar1090"
stage="$(mktemp -d "$cache_parent/.tar1090-install.XXXXXXXX")"
if git clone -q --depth 1 --single-branch --branch gh-pages --filter=blob:none --sparse \
  "https://github.com/Tihulu/tihulu-flight-radar.git" "$stage/pages" \
  && git -C "$stage/pages" sparse-checkout set tar1090 \
  && [[ -s "$stage/pages/tar1090/index.html" ]] \
  && [[ -s "$stage/pages/tar1090/planeObject.js" ]] \
  && [[ -s "$stage/pages/tar1090/db2/operators.js" ]]; then
  mkdir -p "$stage/cache"
  cp -a "$stage/pages/tar1090/." "$stage/cache/"
  # Never rely on an earlier gh-pages adapter revision: use the source that
  # pipx just installed, so the desktop's tar1090 matches current app logic.
  adapter_path="$("$py" -c 'import pathlib,tihulu_flight_radar; print(pathlib.Path(tihulu_flight_radar.__file__).parent / "web/tar1090-adapter.js")')" 
  if [[ -s "$adapter_path" ]] && grep -q 'tihulu-browser-bridge.js' "$stage/cache/index.html"; then
    cp "$adapter_path" "$stage/cache/tihulu-browser-bridge.js"
    old_cache="$stage/old-cache"
    if [[ -d "$tar_cache" ]]; then mv "$tar_cache" "$old_cache"; fi
    if mv "$stage/cache" "$tar_cache"; then
      echo "Cached full tar1090 interface locally; Internet-only works without readsb."
    else
      [[ ! -d "$old_cache" ]] || mv "$old_cache" "$tar_cache"
      echo "Warning: could not replace tar1090 cache; hosted fallback remains available." >&2
    fi
  else
    echo "Warning: tar1090 frontend metadata/adapter mismatch; old cache preserved." >&2
  fi
else
  echo "Warning: unable to cache full tar1090; HTTPS-hosted Internet-only map is the fallback." >&2
fi
rm -rf "$stage"

app_dir="$HOME/.local/share/applications"
icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$app_dir" "$icon_dir"

# Download the icon from the same ref used to install code.
icon_tmp="$(mktemp)"
trap 'rm -f "$icon_tmp"' EXIT
curl -fLsS "https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/$ref/packaging/linux/tihulu-flight-radar.svg" -o "$icon_tmp"
install -m 0644 "$icon_tmp" "$icon_dir/tihulu-flight-radar.svg"

# Remove only known obsolete *application packages* after the new pipx version
# is installed and verified. apt-get remove (not purge) preserves conffiles.
# Never remove or restart readsb, tar1090 or another module's SDR services.
for pkg in tihulu-adsb-radar tihulu-flight-radar; do
  if dpkg -s "$pkg" 2>/dev/null | grep -q "Status: install ok installed"; then
    echo "Replacing legacy desktop package: $pkg"
    sudo apt-get remove -y "$pkg"
  fi
done

# Security: this version grants NO privileged systemd controls.
# Prior /etc/sudoers.d/tihulu-flight-radar entries (if any) are untouched;
# an administrator must review old grants. Never remove or migrate automatically.

# The main icon opens the native embedded live radar, never a system browser.
# Classic keeps all earlier receiver functionality in another Qt application.
cat > "$app_dir/tihulu-flight-radar.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tihulu Flight Radar
GenericName=Live ADS-B Aircraft Radar
Comment=Native aircraft radar with antenna and Internet overlays
Exec="$app_binary"
Icon=tihulu-flight-radar
Terminal=false
StartupNotify=true
Categories=Network;HamRadio;
EOF

# The former "Web" icon now also opens an app window for existing users.
# No terminal token or manual browser navigation is needed in the native GUI.
cat > "$app_dir/tihulu-flight-radar-web.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tihulu Flight Radar Live
GenericName=Live Aircraft Map
Comment=Native desktop radar — antenna, Internet and combined overlays
Exec="$app_binary"
Icon=tihulu-flight-radar
Terminal=false
StartupNotify=true
Categories=Network;HamRadio;
EOF

cat > "$app_dir/tihulu-flight-radar-classic.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tihulu Flight Radar Classic
GenericName=Receiver Control and Full Statistics
Comment=Original Qt receiver dashboard, export and full tar1090 support
Exec="$classic_binary"
Icon=tihulu-flight-radar
Terminal=false
StartupNotify=true
Categories=Network;HamRadio;
EOF

chmod 0644 "$app_dir/tihulu-flight-radar.desktop" "$app_dir/tihulu-flight-radar-web.desktop" "$app_dir/tihulu-flight-radar-classic.desktop"
# Only the known old launcher is removed; never alter a user's other shortcuts.
rm -f "$app_dir/tihulu-adsb-radar.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$app_dir" || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi

echo
echo "Installed/updated successfully from '$ref'."
echo "COSMIC Applications → Tihulu Flight Radar (native live app)"
echo "COSMIC Applications → Tihulu Flight Radar Live (native live app, old web shortcut replaced)"
echo "COSMIC Applications → Tihulu Flight Radar Classic (legacy dashboard)"
echo "Or run: $app_binary"
echo "Classic desktop: $classic_binary"
echo "GitHub Pages companion (optional, manual): $bridge_binary"
echo "Web hardware controls default to OFF; they require --allow-control."
echo "Receiver services, SDR access and recordings were not reset or deleted."
