#!/usr/bin/env bash
# TIHULU Flight Radar — explicit Pop!_OS / Debian version switch.
# Both refs are exact published GitHub commit SHAs, not moving branches.
# One pipx environment: --force replaces old app; never installs duplicates.
# No uninstall/purge/restart of readsb, tar1090, SDR drivers or recordings.
set -Eeuo pipefail

usage() {
  printf '%s\n' \
    'Usage: bash popos-version-switch.sh preview|legacy' \
    '  preview  install 0.3.2.dev1 multi-provider development snapshot' \
    '  legacy   restore the preserved 0.3.1 pre-multi-source snapshot' \
    'Close Tihulu Flight Radar windows before switching versions.'
}
case "${1:-}" in
  preview)
    ref="ff934a67f0c4b93e23997d01307ad89bc9fbdb95"
    expected="0.3.2.dev1"
    ;;
  legacy)
    ref="67280cd84feb89faec6a80f5fe2a55ce5f7b89e6"
    expected="0.3.1"
    ;;
  -h|--help|help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-get >/dev/null 2>&1; then
  echo "The installer supports Debian, Ubuntu and Pop!_OS only." >&2
  exit 1
fi
if (( EUID == 0 )); then
  echo "Run as your normal desktop user without sudo; installer will ask when needed." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to fetch the version-pinned installer." >&2
  exit 1
fi

py="$HOME/.local/share/pipx/venvs/tihulu-flight-radar/bin/python"
previous="not installed"
if [[ -x "$py" ]]; then
  previous="$("$py" -c 'import tihulu_flight_radar; print(tihulu_flight_radar.__version__)' 2>/dev/null || echo 'unknown')"
fi

echo "TIHULU Flight Radar: $previous -> $expected"
echo "The current pipx installation will be REPLACED, not installed side by side."
echo "The former 0.3.1 code remains archived at GitHub legacy/v0.3.1."
echo "Receiver services, SDR drivers, user settings and recordings will not be purged."

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl --fail --location --silent --show-error \
  "https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/$ref/scripts/install-linux.sh" \
  --output "$tmp"

# Original installer supports an explicit TIHULU_REF and uses pipx install
# --force to replace the application's existing virtual environment/launchers.
TIHULU_REF="$ref" bash "$tmp"

if [[ ! -x "$py" ]]; then
  echo "Installation reported completion but the pipx Python environment is absent." >&2
  exit 1
fi
actual="$("$py" -c 'import tihulu_flight_radar; print(tihulu_flight_radar.__version__)')"
if [[ "$actual" != "$expected" ]]; then
  echo "Unexpected installed version $actual (wanted $expected); check pipx list." >&2
  exit 1
fi
printf '\n%s\n' \
  "Installed TIHULU Flight Radar $actual from exact GitHub commit $ref." \
  "Use: bash popos-version-switch.sh legacy   (to restore original 0.3.1)" \
  "Use: bash popos-version-switch.sh preview  (to reinstall 0.3.2.dev1)"
