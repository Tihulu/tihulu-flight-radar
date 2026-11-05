# Tihulu Flight Radar

English-language, local-first ADS-B / Mode S receiver desktop software.

**Version 0.3.0 (development preview).** Uses real receiver data only. It never
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

The build workflow produces preview artifacts on Linux x64, Windows x64 and
macOS ARM64 runners. A successful build **does not** prove direct USB reception
on every device. No drivers, decoder binaries, or permission policies are bundled.

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

## Local map

Open Map launches an integrated local HTTP viewer bound to 127.0.0.1 on a random
port. It plots **only genuine, recent positions** and keeps a short in-session
track. Aircraft lacking valid coordinates are listed without map markers.
Offline, the viewer shows a geographic coordinate grid; online OpenStreetMap
tiles are optional, with attribution. We do not bundle offline OSM tiles.
The map server is loopback-only. Existing tar1090 remains available for
LAN devices, depending on its local network/firewall configuration.

## Data and security

- Reads /run/readsb/aircraft.json in Linux services mode.
- Remote JSON is a user-provided HTTP(S) URL; avoid using untrusted endpoints.
- Exports only a raw received JSON snapshot chosen by the user.
- Stale data is rejected. Missing aircraft positions are never inferred.
- No cloud account, feed uploads, background polling when the UI is closed,
  or auto-start on boot is added by this application.
- Two applications cannot claim the same physical RTL-SDR simultaneously.

## Roadmap

- Signed Windows installer and notarized macOS DMG.
- Verified Windows local SDR backend and driver installer guidance.
- Raspberry Pi packages and headless Survival Kit Radio/SDR Center backend.
- Offline MBTiles packages, aircraft history database, signal graphs and
  multiple receiver support.
