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

## Linux installation (Pop!_OS, Ubuntu, Debian)

Install or upgrade from GitHub **main** with the
[interactive Linux installer](scripts/install-linux.sh). It installs the
Python application through pipx, adds a COSMIC/XDG Applications launcher
and icon, removes only the obsolete `tihulu-adsb-radar` and duplicate
`tihulu-flight-radar` Debian packages if present, and grants the current
Linux account narrowly scoped `readsb`/`tar1090` service controls.

The ADS-B receiver services are **not removed**. Run as your normal user:

```bash
f="$(mktemp)" && curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh -o "$f" && bash "$f"; rm -f "$f"
```

Review the installer source before running scripts that request sudo.
Afterward launch from **COSMIC Applications → Tihulu Flight Radar**
or use `~/.local/bin/tihulu-flight-radar`.
## Development run

Requires Python 3.11+ (3.12 recommended).

1. Create a virtual environment: python -m venv .venv
2. Activate it (Linux/macOS): source .venv/bin/activate
   (Windows PowerShell): .venv\Scripts\Activate.ps1
3. Install: python -m pip install -e ".[test]"
4. Launch: tihulu-flight-radar
5. Test: python -m pytest -q

All visible UI copy, messages, docs and workflows are in English.

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


### Closing the app releases receivers started by this app

The application already has **Start / Stop / Restart** buttons. The Linux
`readsb.service` is now treated as an app-owned session **only if it was
inactive and explicitly started using the Flight Radar Start button**.
On desktop window close, the program finishes pending actions and stops
that app-started systemd receiver (as well as directly spawned readsb
children), preventing the RTL-SDR from remaining busy. Pre-existing
systemd services are considered **externally managed** and are **not
stopped silently**: select Stop first when switching to FM/DAB. If the
restricted sudo permission fails on close, the application reports the
failure and cancels close rather than claiming the USB is free.

Boot-enable/disable is a separate explicit control; closing the app does
not change system startup settings. No broad process-kill commands are used.
Background-mode default is OFF for receivers owned by the desktop app.


On automatic close, Flight Radar stops **readsb.service only**, leaving
an independent tar1090 map/UI service running. The exact one-unit
`systemctl stop readsb.service` command requires a refreshed narrow
sudoers policy; re-running the Linux installer after this PR merges
installs it without broadening to unrestricted sudo. Explicit in-app
Stop/Restart controls retain the previous paired readsb/tar1090 behavior.
