# TIHULU Flight Radar — Windows desktop 0.3.2.dev4

**Status:** ✅ Draft release `desktop-0.3.2.dev4-20261122-2327` (GitHub Actions: `desktop-versions-build.yml`, windows-latest)

## Install
1. Download [`TihuluFlightRadar-win-x64.zip`](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/TihuluFlightRadar-win-x64.zip)
   ([release page](https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-2327) · hash: `SHA256SUMS`)
2. Unzip into a folder (no Program Files needed; a user folder is recommended)
3. Run `TihuluFlightRadar.exe`

## Requirements
- Windows 10/11 x64 · Microsoft Visual C++ Redistributable (usually already installed)
- RTL-SDR driver is separate (WinUSB/Zadig); readsb can be installed separately
- App data is kept under `%APPDATA%\Tihulu\FlightRadar`

## Notes
- Built with PyInstaller; published as an unsigned executable
- No service installation; shutdown only releases the app's own resources
