# Flight Radar feature preservation and Survival Kit integration checklist

Source comparison: original Tihulu ADS-B Radar v0.2.0 GTK4 package (2026-11-05) vs current Tihulu Flight Radar cross-platform Qt desktop.

## User acceptance rule

**No previously working feature may be removed, hidden permanently, or silently replaced with an inferior substitute.** The earlier full tar1090 aircraft display remains available even when the built-in map is offered.

## Retained earlier GTK4 capabilities

| Original capability | Cross-platform desktop 0.3.1 |
| --- | --- |
| Start / Stop readsb and tar1090 | Start, Stop and Restart; serialized and verified |
| Decoder status and tar1090 status | Receiver status panel with health details and read-only diagnostics |
| Aircraft count | Live reception card |
| Fresh-positioned aircraft count | Live reception card |
| Messages per second | Live reception card |
| Cumulative message count | Live reception card |
| Mean RSSI (dBFS) | Live reception card |
| **Full tar1090 aircraft map** | Separate **Open full tar1090 map** action with local endpoint detection |
| LAN tar1090 address | Visible under Map & exports on Linux |
| Automatic timestamped JSON export to Downloads | **Quick export (timestamped)** |
| Export actual received aircraft JSON | **Export JSON as…** plus raw JSON in details |
| Enable / disable readsb + tar1090 at boot | Receiver settings checkbox for both services |
| Advisory competing SDR process check | Conflict warning before claiming an idle receiver |
| No forced shutdown of unknown SDR apps | Preserved |
| Restricted Linux service permissions | Preserved (four exact systemd commands) |
| Closing window does not kill systemd services | Preserved |
| English UI | Preserved |

## Additional cross-platform features

- Aircraft table: flight/callsign, ICAO, registration, type, barometric altitude, ground speed, track and last-seen age.
- Aircraft detail dialog: all available observed fields, including position, vertical speed and RSSI, plus raw decoder JSON.
- Select an aircraft to open the built-in map focused on its actual fresh coordinate.
- Built-in geographic map as an independent complement to tar1090.
- Linux services, native Direct readsb and Remote JSON source modes.
- Windows x64, Debian/Ubuntu x64 and macOS Apple Silicon desktop builds (native USB testing required).

## Mandatory map initial camera priority

1. **Actual, fresh aircraft coordinate exists:** focus a real aircraft, selecting nearest to a known receiver/GPS coordinate when available. If no real receiver coordinate exists, use distance to the explicitly labeled default Germany map center only as a selection heuristic, not a receiver location.
2. **No positioned aircraft; real saved receiver / permitted GPS location exists:** open at that coordinate.
3. **Neither exists:** show Germany by default, centered approximately 51.1657 N, 10.4515 E, with no invented aircraft, receiver or user marker.

The map **must be openable when the decoder is stopped or aircraft count is zero**. Available controls: Focus nearest aircraft, Show Germany, Center receiver, Use my location, Set receiver position, zoom, pan and selected-aircraft focus. Manual panning should not be overridden until refocus is requested.

## Mandatory decoder health behavior

- "Service active" is not equivalent to "receiving RF messages".
- Verify post-start readsb stability; show honest zero-messages state.
- Support Stop -> Start -> Restart without stale pre-restart telemetry.
- Surface USB/SDR resource contention and read-only diagnostic logs.
- Do not take over an SDR used by FM/DAB+/RTL-433 without an explicit resource manager handoff.

## Survival Kit integration — do not overlook

The main Survival Kit Flight Radar Center must retain all of these capabilities when implementing the responsive phone/tablet/desktop PWA. The same local URL must adapt without dropping controls or aircraft data on smaller screens. Use shared backend, source provenance and SDR resource ownership; support Antenna/Internet/Hybrid/Automatic modes, on-demand default and permitted offline operation. OpenStreetMap tiles do **not** constitute an online aircraft feed. Preserve the standalone Flight Radar repository and avoid replacing tar1090 with a feature-incomplete map.

## Verification gates

- Qt smoke: old buttons, decoder modes, 4 metric cards, full tar1090 map, LAN URL, quick export, aircraft list and a loadable empty map.
- JavaScript tests: airplane-first / GPS-second / Germany-default camera and no invented positions.
- Python tests: stale aircraft, SDR conflict, restart transitions, JSON export and remote mode.
- CI: Debian x64, Ubuntu/Pop!_OS x64, macOS arm64 and Windows x64.
- Hardware: manual Stop -> Start -> Restart with Nooelec NESDR SMArt v5 and actual received-message increases.
- Visual/manual: compare new Qt dashboard against v0.2 screenshots on COSMIC; verify no content overlap and proper resizing.

**Automated CI cannot alone certify actual radio reception or the final human visual quality.**
