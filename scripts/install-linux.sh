#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$(uname -s)" != Linux ] || ! command -v apt-get >/dev/null; then
  echo "This installer supports Debian, Ubuntu and Pop!_OS only." >&2; exit 1
fi
if [ "$EUID" = 0 ]; then
  echo "Run as your regular desktop user, without sudo." >&2; exit 1
fi
login="$(id -un)"
if [[ ! "$login" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "Unexpected account name; refusing to create sudo rule." >&2; exit 1
fi

echo "Installing Tihulu Flight Radar from GitHub main."
echo "The installer will request sudo once for packages and restricted service permissions."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  pipx python3-venv git curl sudo \
  libegl1 libgl1 libxkbcommon0 libxcb-cursor0 libdbus-1-3 libglib2.0-0
pipx install --force "git+https://github.com/Tihulu/tihulu-flight-radar.git@main"

binary="$HOME/.local/bin/tihulu-flight-radar"
if [ ! -x "$binary" ]; then
  echo "The pipx executable is missing: $binary" >&2; exit 1
fi

app_dir="$HOME/.local/share/applications"
icon_dir="$HOME/.local/share/icons/hicolor/scalable/apps"
mkdir -p "$app_dir" "$icon_dir"
curl -fLsS "https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/packaging/linux/tihulu-flight-radar.svg" \
  -o "$icon_dir/tihulu-flight-radar.svg"

cat > "$app_dir/tihulu-flight-radar.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tihulu Flight Radar
Comment=Local-first ADS-B and Mode S aircraft monitor
Exec="$binary"
Icon=tihulu-flight-radar
Terminal=false
StartupNotify=true
Categories=Network;HamRadio;
EOF

# Remove only the obsolete desktop packages, not the readsb / tar1090 services.
for pkg in tihulu-adsb-radar tihulu-flight-radar; do
  if dpkg -s "$pkg" 2>/dev/null | grep -q "Status: install ok installed"; then
    sudo apt-get purge -y "$pkg"
  fi
done
rm -f "$app_dir/tihulu-adsb-radar.desktop"

# Minimal, account-specific authorization for exact service operations.
policy="$(mktemp)"
trap 'rm -f "$policy"' EXIT
cat > "$policy" <<EOF
Cmnd_Alias TIHULU_FLIGHT = /usr/bin/systemctl start readsb.service tar1090.service, /usr/bin/systemctl stop readsb.service tar1090.service, /usr/bin/systemctl stop readsb.service, /usr/bin/systemctl enable readsb.service tar1090.service, /usr/bin/systemctl disable readsb.service tar1090.service
$login ALL=(root) NOPASSWD: TIHULU_FLIGHT
EOF
sudo visudo -cf "$policy"
sudo install -m 0440 "$policy" /etc/sudoers.d/tihulu-flight-radar
sudo visudo -cf /etc/sudoers.d/tihulu-flight-radar

if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$app_dir" || true
fi
echo "Success. Open COSMIC Applications -> Tihulu Flight Radar."
echo "Receiver readsb and tar1090 are preserved."
