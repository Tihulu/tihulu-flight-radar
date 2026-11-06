# Tihulu Flight Radar

English-language, local-first ADS-B / Mode S receiver desktop software.

**Version 0.3.1 (development preview).** Uses real receiver data only. It never
creates simulated aircraft or positions. ADS-B broadcasts may contain locations;
Mode S does not guarantee location. MLAT positioning requires synchronized
multiple receivers and is **not** calculated by this app.

## Targets and current limitations

| OS | Desktop UI | Direct RTL-SDR | Remote receiver |
| --- | --- | --- | --- |
| Debian / Ubuntu / Pop!_OS x64 | Qt / PySide6 | Existing readsb/tar1090 systemd, or local readsb executable | Yes |
| macOS Apple Silicon (M1/M2/M3/M4) | Qt / PySide6 | Homebrew readsb and compatible RTL-SDR | Yes |
| Windows x64 | Qt / PySide6 | Only with a separately supplied working readsb binary and USB driver; not packaged or validated | Yes |
| Raspberry Pi Linux ARM64 | Python source | Existing readsb daemon or separately installed readsb | Yes |

The build workflow produces preview artifacts on Ubuntu Linux x64, Debian 12
x64, Windows x64 and macOS ARM64 runners. A successful build **does not** prove direct USB reception
on every device. No drivers, decoder binaries, or permission policies are bundled.

## Debian .deb preview

The Debian 12 workflow produces an unsigned Debian package as well as a
portable application folder. Install with:

    sudo apt install ./tihulu-flight-radar_0.3.1_amd64.deb

The new package does not overwrite the earlier tihulu-adsb-radar v0.2.0.
It adds a documented restricted sudoers rule for sudo-group administrators
allowing *only* start/stop/enable/disable of readsb and tar1090. This avoids
password prompts after the one-time package installation. Review
packaging/linux/sudoers.conf before installation. The app does not install
a decoder or RTL-SDR driver by itself.

## One-line Linux install / upgrade (Pop!_OS, Ubuntu, Debian)

The installer installs or **replaces your old Tihulu ADS-B/Flight Radar desktop version** using pipx and creates two COSMIC/XDG Applications shortcuts:

- **Tihulu Flight Radar** — existing full Qt desktop dashboard and advanced tar1090 access.
- **Tihulu Flight Radar Web** — starts the loopback-only browser companion, opens the local web dashboard and prints a temporary pairing token to the terminal.

It preserves `readsb`/`tar1090` services, receiver settings and recordings; removes only identified obsolete Tihulu desktop *packages* (with `apt-get remove`, not purge) and the former `tihulu-adsb-radar.desktop` launcher. The new bridge's hardware controls are off by default.

**Preview installer for this unmerged development branch** (one line, as your normal user, without `sudo` in front):

```bash
bash -c 'set -euo pipefail; f=$(mktemp); trap "rm -f \"$f\"" EXIT; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/feature/github-pages-local-bridge-2026-11-06/scripts/install-linux.sh -o "$f"; TIHULU_REF=feature/github-pages-local-bridge-2026-11-06 bash "$f"'
```

After the reviewed changes reach `main`, the stable one-line updater will be:

```bash
bash -c 'set -euo pipefail; f=$(mktemp); trap "rm -f \"$f\"" EXIT; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh -o "$f"; bash "$f"'
```

**Do not use the stable updater to request the preview features until they are actually merged.** This script needs an Internet connection and will ask for sudo permission for distro packages, cleanup of old Debian app packages, and narrowly scoped readsb/tar1090 service rules. Review [the script](scripts/install-linux.sh) before execution, especially on a machine with customized packages.

The same command can be run again to update the pipx installation and application entries. The terminal shown when opening **Tihulu Flight Radar Web** contains the short-lived pairing token that must be pasted into the web page; do not publish it. If Applications has not refreshed immediately, sign out and back in. For manual launch, use `~/.local/bin/tihulu-flight-radar` or `~/.local/bin/tihulu-flight-bridge --open-browser` (the second should be run in a visible terminal).

**Limitations:** This is still a draft implementation, not a released site. The local bridge requires the existing readsb decoder and correct RTL-SDR driver for actual RF reception. It does not provide insecure public LAN control.
## Development run

Requires Python 3.11+ (3.12 recommended).

1. Create a virtual environment: python -m venv .venv
2. Activate it (Linux/macOS): source .venv/bin/activate
   (Windows PowerShell): .venv\Scripts\Activate.ps1
3. Install: python -m pip install -e ".[test]"
4. Launch: tihulu-flight-radar
5. Test: python -m pytest -q

All visible UI copy, messages, docs and workflows are in English.


## GitHub Pages and paired local web receiver (development candidate)

A responsive static web dashboard has been added under `tihulu_flight_radar/web/` for GitHub Pages and local browser use. **This feature is not released or published yet.** The intended project URL after enabling the Pages deployment workflow is `https://tihulu.github.io/tihulu-flight-radar/`.

To use local USB ADS-B data, launch the paired companion on the **receiver computer**, not on GitHub Pages:

```sh
# From a checkout of the development branch (Python 3.11+):
python -m pip install --no-deps .
tihulu-flight-bridge
```

Open `http://127.0.0.1:8510/`, enter the session pairing token displayed in the terminal and choose **Antenna only**, **Internet only**, **Hybrid**, or **Auto**. Bridge hardware controls default **disabled**; use `tihulu-flight-bridge --allow-control` for explicit authenticated hardware Start/Stop/Restart. Local readsb and direct RTL-SDR still require platform-specific drivers/decoder. No Python or USB code can run directly on GitHub Pages. Internet data on the Pages app presently also uses the paired companion (because the public providers' browser CORS support is not assured).

The bridge binds only to loopback. **Pi/Survival Kit secure LAN/mobile connectivity and a no-companion hosted online provider are not implemented yet.** Other platforms can run the local bridge and use the already existing Qt desktop build previews; ARM64 Pi is source-based/CI smoke tested, not yet hardware-validated. The desktop Qt dashboard and full tar1090 viewer are retained unchanged.

See [Web, GitHub Pages and bridge guide](docs/GITHUB_PAGES_AND_LOCAL_BRIDGE.md), [feature issue #5](https://github.com/Tihulu/tihulu-flight-radar/issues/5) and [Survival Kit issue #9](https://github.com/Tihulu/tihulu-survival-kit/issues/9).

## Receiver modes

- **Linux services**: controls an already installed readsb + tar1090 systemd
  service pair. The app uses exactly four narrowly defined commands for
  start/stop/enable/disable with sudo -n. To avoid password prompts, the
  existing v0.2.0 Debian package grants ONLY those commands to members of
  the sudo group via its sudoers drop-in. On other Linux installations,
  configure equivalent limited authorization. Never grant unrestricted sudo.
- **Direct readsb**: launches the separately installed readsb process with
  RTL-SDR at 1090 MHz and a temporary JSON output directory. Does not
  use systemd or request administrator credentials. The app terminates the
  child process on exit. Linux users should STOP the readsb systemd service
  before using this mode with the same dongle.
- **Remote JSON**: enter the full URL to a receiver's readsb
  aircraft.json. Works on all desktop platforms, including Windows without
  local RTL-SDR. The remote receiver remains independently controlled.

macOS Apple Silicon: install Homebrew, then run brew install readsb.
Connect the NESDR dongle and select Direct readsb; never run another SDR
client at the same time. No app admin password is required for this mode.
Windows: use Remote JSON unless a separately tested native readsb executable
and WinUSB RTL-SDR driver are available.

## Receiver health and restart

Start / Stop / Restart operations are serialized and the readsb systemd state
is verified after each transition. An active decoder is **not** proof of
actual RF reception. The UI now distinguishes a running decoder from
receiving ADS-B messages and offers **Receiver diagnostics** on Linux
(read-only systemd / journal output). A newly started readsb service may
have zero messages for a while, especially with antenna, interference
or exclusive USB ownership problems.

When start fails or message counts remain zero, check receiver ownership,
antenna orientation and the last readsb logs. Do not assume an active service
implies aircraft data. See
[Survival Kit handoff notes](docs/SURVIVAL_KIT_FLIGHT_RADAR_HANDOFF_2026-11-05.md)
for integration acceptance criteria.

## Interface, flight data and map

Version 0.3.1 restores the earlier GTK4 v0.2 dashboard capabilities **without replacing or removing the full tar1090 aircraft viewer**. The English-language Qt UI shows the four original live statistics (aircraft, positioned aircraft, messages/second, total messages), mean RSSI, Start/Stop/Restart, boot settings, local LAN tar1090 URL, a full tar1090 map button, automatic timestamped quick JSON export and Save As export. It additionally has a live aircraft list and full readsb observation details including raw received JSON.

The **built-in map** complements, rather than replaces, the full tar1090 viewer. It opens even when there is no active decoder, no aircraft or no valid coordinates. Initial camera priority:

1. Real fresh aircraft positions: focus the nearest valid aircraft relative to receiver/GPS coordinates, or to the labeled Germany map center if no real reference location exists.
2. No fresh aircraft position: center on real explicitly saved receiver coordinates or permitted browser GPS location.
3. Neither aircraft positions nor an authorized reference: show Germany (51.1657°N, 10.4515°E) as a **default map view**, not as a claimed receiver position.

The map buttons include Focus nearest aircraft, Show Germany, Center receiver, Use my location and Set receiver position. Selecting a positioned aircraft in the desktop table can open the built-in map focused on it. Manual zoom/pan is respected until the user requests recentering.

The embedded HTTP map stays on loopback only (prefers 127.0.0.1:8505 for stable browser settings; uses an ephemeral port if occupied). It shows only genuine fresh aircraft position markers and short session tracks. OpenStreetMap tiles are optional and require internet; without tiles, a geographic coordinate grid remains available. The installed full tar1090 viewer retains its own detailed interface and LAN exposure according to the receiver installation.

See the [feature preservation and Survival Kit checklist](docs/FEATURE_PARITY_AND_SURVIVAL_KIT_GATE.md). This document is a non-regression requirement for the integrated Survival Kit responsive Flight Radar Center.

## Data and security

- Reads /run/readsb/aircraft.json in Linux services mode.
- Remote JSON is a user-provided HTTP(S) URL; avoid using untrusted endpoints.
- Exports only a raw received JSON snapshot chosen by the user.
- Stale data is rejected. Missing aircraft positions are never inferred.
- No cloud account or feed uploads. The UI stops polling when closed; systemd receiver
  background service startup remains a user-controlled opt-in.
- Two applications cannot claim the same physical RTL-SDR simultaneously.

## Roadmap

- Signed Windows installer and notarized macOS DMG.
- Verified Windows local SDR backend and driver installer guidance.
- Raspberry Pi packages and headless Survival Kit Radio/SDR Center backend.
- Offline MBTiles packages, aircraft history database, signal graphs and
  multiple receiver support.
