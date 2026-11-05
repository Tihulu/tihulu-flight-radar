# SURVIVAL KIT HANDOFF — Flight Radar lifecycle & map regression
Date: 2026-11-05
Source repository: https://github.com/Tihulu/tihulu-flight-radar

## User-reported problem
Pop!_OS 24.04 COSMIC, Nooelec NESDR SMArt v5 (USB 0bda:2838):
- After Stop receiver, subsequent Start receiver can appear successful while real reception does not resume.
- A screenshot displayed "RECEIVER RUNNING" but zero detected aircraft, positions, messages/sec, and total messages.
- The map was empty/blocked when no fresh aircraft positions were present.
- Users want the map usable without aircraft and region/location/refocus buttons.
- These problems MUST NOT be overlooked when Flight Radar functionality is incorporated into the broader Tihulu Survival Kit.

## Distinguish states rigorously
- "systemd decoder active" is NOT equivalent to "ADS-B RF messages received".
- Track decoder state, decoder start/stop errors, data freshness, message rate, and position availability separately.
- After Start, verify that readsb remains active (catch transient "active" followed by USB-busy exit).
- Show honest "Decoder active — no RF messages" when decoder is running but reception has not produced data.
- Add Restart receiver and read-only diagnostics, without broad sudo privileges.
- Do not misrepresent stale snapshots from a previous decoder session as new messages.
- On hardware failure present useful recovery steps and log information; do not claim software fixes antenna/USB problems automatically.
- Use a single SDR resource owner/lock across ADS-B/FM/DAB+/RTL-433; never silently terminate other modules.

## Map camera priority and fallback — latest user acceptance rule
1. If REAL, fresh ADS-B aircraft position(s) exist, focus an actual aircraft immediately. When GPS/receiver coordinates are known, choose the nearest real aircraft relative to that reference; otherwise rank observed aircraft using the explicitly labeled Germany default center as a heuristic.
2. If no fresh aircraft position exists but saved receiver coordinates or explicitly permitted GPS location exists, open the geographic map there.
3. If neither aircraft nor permitted reference location exists, always open the geographic map centered in Germany (51.1657 N, 10.4515 E). This is a VIEWPORT fallback, never a claimed receiver position.
4. The map must be openable before the decoder is started and when zero aircraft are received; do not obscure it with a waiting screen. Show an honest empty-aircraft state.
5. Expose Focus nearest aircraft, Show Germany, Center receiver, Use my location, Set receiver position, and selectable aircraft focus. Respect manual map movements.
6. Preserve full legacy tar1090 functionality instead of replacing it with an inferior built-in map. The new simple map must be an optional complement to tar1090.
7. Never fabricate positions or display stale/Mode S-only aircraft as located on the map.
8. Provide an offline coordinate grid when OSM tiles are unavailable; throttle failed tile requests.

## Survival Kit integration requirements
- Apply the same behavior to the responsive Flight Radar PWA across desktop, tablet and phone at the Survival Kit local URLs.
- Default to on-demand SDR lifecycle; respect multiple connected clients before stopping.
- User-configurable source modes: Antenna Only, Internet Only, Hybrid, Auto.
- Internet-based data is separate from local radio reception; online OSM tiles are NOT internet aircraft data.
- Expose decoder-service health separately from aircraft feed health in APIs and UI.
- Ensure start/stop/restart is serialized and idempotent with observable hardware ownership and a recovery path.
- Add automated tests for stopped-to-started transitions, stale aircraft snapshots, UI empty states, map fallback, source-state reporting, and SDR conflicts.
- Validate with actual NESDR hardware; unit tests alone do not prove real RF reception after restarting.


## Feature parity and UI visual-quality gate (added after regression report)

The user explicitly reported that the Qt replacement was visually worse than the deleted v0.2 GTK interface and seemed to have lost aircraft/flight data.

- Do NOT remove any previously working flight data display or feature when modernizing or integrating the frontend.
- Preserve the *full tar1090 map* (not just a simplified replacement), local LAN map URL, Start/Stop, boot setting, four live counters, mean RSSI and timestamped one-click JSON export.
- Show an actual aircraft table: callsign, ICAO, registration, type, altitude, speed, track, observation age, plus a details view exposing actual received fields and optional raw JSON.
- Keep decoder, RF reception, USB conflict and data freshness states distinct.
- Restore high-quality coherent dark/light theme and readable card layout without black stripes/overlapping labels. Layout must work on desktops and adapt to phone/tablet for Survival Kit.
- Regression tests and screenshots must be checked against the prior v0.2 GTK layout, not only the new Qt implementation.
- See docs/FEATURE_PARITY_AND_SURVIVAL_KIT_GATE.md as the mandatory acceptance checklist for the Survival Kit agents.

## Implementation checkpoints
- Review this issue when integrating the stand-alone Tihulu Flight Radar source.
- Check current main and all relevant fix PRs before copying code.
- Preserve English-only UI and prior Survival Kit architecture decisions.
- Carry the acceptance criteria above into project milestone tracking and user-visible UI/flowcharts.
