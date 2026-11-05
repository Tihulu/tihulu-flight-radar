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

## Map camera priority and fallback
1. If saved receiver coordinates or a browser-permitted current location are available, show that geographic area.
2. If real, fresh positioned aircraft are received, allow "Focus nearest aircraft" relative to the known location.
3. If no user/receiver location is available, center the DEFAULT VIEW at Germany (51.1657 N, 10.4515 E); this is NOT the receiver location.
4. When valid aircraft positions become available, focus on the nearest real aircraft to the known reference; in the absence of one, distance to Germany's default map center is a clearly labeled heuristic.
5. If no positioned aircraft exist, still show the map at the known location or Germany default; show empty-aircraft state, never fabricate aircraft or coordinates.
6. Expose explicit controls: Show Germany, Focus nearest aircraft, Center receiver, Use my location, Set receiver position. Preserve manual map movement until deliberate refocus.
7. Provide offline coordinate grid if OSM tiles unavailable. Online tile failure must not create an endless retry loop.

## Survival Kit integration requirements
- Apply the same behavior to the responsive Flight Radar PWA across desktop, tablet and phone at the Survival Kit local URLs.
- Default to on-demand SDR lifecycle; respect multiple connected clients before stopping.
- User-configurable source modes: Antenna Only, Internet Only, Hybrid, Auto.
- Internet-based data is separate from local radio reception; online OSM tiles are NOT internet aircraft data.
- Expose decoder-service health separately from aircraft feed health in APIs and UI.
- Ensure start/stop/restart is serialized and idempotent with observable hardware ownership and a recovery path.
- Add automated tests for stopped-to-started transitions, stale aircraft snapshots, UI empty states, map fallback, source-state reporting, and SDR conflicts.
- Validate with actual NESDR hardware; unit tests alone do not prove real RF reception after restarting.

## Implementation checkpoints
- Review this issue when integrating the stand-alone Tihulu Flight Radar source.
- Check current main and all relevant fix PRs before copying code.
- Preserve English-only UI and prior Survival Kit architecture decisions.
- Carry the acceptance criteria above into project milestone tracking and user-visible UI/flowcharts.
