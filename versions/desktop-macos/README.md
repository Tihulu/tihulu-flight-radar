# TIHULU Flight Radar — macOS desktop 0.3.2.dev4

**Status:** ✅ Draft release `desktop-0.3.2.dev4-20261122-0734` (GitHub Actions: `desktop-versions-build.yml`, macos-latest)

## Install
1. Download [`TihuluFlightRadar-macos-arm64.zip`](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-0734/TihuluFlightRadar-macos-arm64.zip)
   (Apple Silicon arm64 build · [release page](https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-0734) · hash: `SHA256SUMS`)
2. Drag the `TihuluFlightRadar.app` folder into `/Applications` (or a user folder)
3. Gatekeeper may warn on first open: right-click → Open (expected behavior for unsigned builds)

## Requirements
- macOS 12+ (Intel or Apple Silicon)
- RTL-SDR driver is separate; readsb can be installed separately
- Data is kept under `~/Library/Application Support/Tihulu/FlightRadar`

## Notes
- Built with PyInstaller; NO Apple notarization/signature — separate approval required before publishing
- Without code signing/notarization, broad distribution is not recommended (PUBLIC RELEASE HOLD)
