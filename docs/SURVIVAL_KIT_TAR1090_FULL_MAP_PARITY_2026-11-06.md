# Tihulu Survival Kit — tar1090 Full Map Parity & Multi-device Access

**Date:** 2026-11-06
**Status:** Binding handoff requirements for Survival Kit integration; NOT a claim that the Kit implementation is complete.
**Standalone app:** https://github.com/Tihulu/tihulu-flight-radar
**Upstream tar1090:** https://github.com/wiedehopf/tar1090

## New user requirement: richer tar1090 map is primary, not optional decoration

The user prefers the **full-featured tar1090 aircraft map** to the simplified
built-in aircraft map. **Do not replace tar1090 with the basic grid/map.**
Flight Radar Center in Tihulu Survival Kit must provide a first-class,
full-capability tar1090-driven map from the *same local Survival Kit URLs* on
**desktop browsers, smartphones and tablets**. The lightweight built-in map
can remain a fallback for offline/low-resource/decoder-unavailable cases.

The previously restored standalone Flight Radar v0.3.1 main is the stable
reference; do not regress any of its desktop features while integrating the Kit.

## Same-origin local web access

Primary app: `http://tihulu.lan/flight-radar`,
`http://tihulu.local/flight-radar` (where local DNS/mDNS is actually
configured), optionally `tuhulu.local` as an alias.
Implement an integrated rich-map route, e.g.
`/flight-radar/map` and a native tar1090 compatibility route
`/flight-radar/tar1090/`.
The paths are examples; follow existing Survival Kit routing conventions.

- Serve or reverse-proxy full tar1090 HTML/JS/CSS, images, configuration,
  historical snapshots and decoder JSON endpoints *with correct base paths*.
- Do not leave hard-coded `localhost` URLs in phone/tablet content:
  `localhost` on a phone would mean the phone itself, not the Pi.
- Keep the full map reachable on the local LAN through the Kit's
  authentication/session system. Do not publish unrestricted decoder ports.
- Verify asset URLs, redirects, query strings, caching headers, browser
  cross-origin restrictions, HTTPS/mixed-content behavior when applicable,
  and readsb/tar1090 lifecycle.
- Retain direct local tar1090 route for compatibility if already configured,
  but it is NOT a substitute for an integrated Kit route.
- Do not automatically enable public/WAN exposure; local network only by
  default.

## Verified upstream tar1090 functionality to preserve

From the upstream README, subject to active decoder support and actual
available data: multiple map styles, darkening/dimming, selectable callsign
labels, selecting multiple aircraft, adjustable history, efficient all-track
display, `?pTracks` reception/track views and history time controls,
filtering by aircraft properties/type/altitude, and optional receiver
coverage/range/heatmap overlays when correctly configured.

Preserve the original tar1090 aircraft table, selection and detail behavior,
map gestures and shortcuts where applicable. Audit the *actual installed*
tar1090 version for its additional fields and controls. Feature availability
must be detected: don't promise database-enriched aircraft types,
registrations, trace history or heatmaps if the source services aren't
configured to supply them.

Maintain proper attribution and applicable upstream software licenses.

## One shared responsive UI, no feature loss

- Desktop: spacious large rich map with aircraft list, filters, receiver
  status, optional multi-panel aircraft details and usable controls.
- Tablet: map plus collapsible/split detail pane in landscape or portrait.
- Phone: full-height interactive map and bottom-sheet/list controls; no tiny
  unusable buttons and no hidden/lost aircraft filters. All tar1090 functions
  must remain discoverable; advanced tools may live in clearly labeled menus.
- Same user/session/backend/data and full functionality across breakpoints.
  Do not build a less-capable mobile clone.
- Perform touch, pointer, keyboard, visual and orientation regression tests.

## Camera behavior — supersedes prior conflicting map requirements

1. When *any* real aircraft has **fresh valid coordinates**, focus a real
   aircraft immediately. If a saved receiver coordinate or permitted device
   GPS position is known, select the nearest to that reference; otherwise
   select a real aircraft nearest the explicitly labeled Germany default
   center as a heuristic. Never invent missing coordinates.
2. If NO fresh positioned aircraft exist and receiver/device location is
   available, show that actual reference coordinate.
3. If neither exists, show **Germany** as a viewport default:
   latitude 51.1657 N, longitude 10.4515 E, zoom appropriate for the region.
   This is NOT the receiver location.
4. The rich map must load with zero aircraft and even if the decoder is
   stopped; show honest empty/error status rather than a blank blocking screen.
5. Expose Focus Nearest Aircraft, Show Germany, Center Receiver,
   Use My Location, Set Receiver Position, Fit All, Follow Selected,
   Reset View, pan and zoom as appropriate. Respect manual camera movements.
6. Browser geolocation requires permission. Don't assume the user's actual
   location from IP or expose coordinates unnecessarily.

## Keep every earlier feature / repair

Preserve the original GTK v0.2 dashboard capabilities and standalone
cross-platform Qt v0.3.1 functionality:
Start/Stop/Restart, bounded systemd permissions, on-demand default and shared
SDR locks, honest 'decoder running but no RF messages' state, no stale JSON
after restart, real airplane list and rich details, four live counters
(aircraft, positioned, msg/s and total), RSSI, local tar1090 and LAN URLs,
timestamped quick JSON export, Save As export, boot startup toggle, remote
receiver input, source selection, warnings and diagnostics.

Survival Kit web integration additionally supports optional independent
internet-aircraft provider feeds and hybrid source ingestion. tar1090 is not
automatically a hybrid provider renderer: implement an appropriate secure,
validated map data adapter **if** internet/hybrid traffic must appear within
the rich map. Never silently rewrite readsb's on-disk JSON or claim online
positions were locally received. Label source/MLAT freshness and attribution.

One USB RTL-SDR cannot simultaneously serve FM, DAB+, RTL-433 and ADS-B;
coordinate access with the Survival Kit SDR resource manager. Closing one
mobile tab must not stop a receiver still used by other clients.

## Acceptance tests / rollout gate

- Open `/flight-radar/map` and the native tar1090 compatibility route on:
  desktop Linux/Windows/macOS browsers, iPhone Safari, iPad Safari, and
  Android Chrome (or representatives including portrait & landscape).
- Verify full aircraft table/details, search/filter/multiple selection,
  map layers, historical tracks/`pTracks` and optional advanced overlays
  **only when their dependencies are configured**.
- Check all paths/assets/data requests resolve over the local hostname
  (no phone-side localhost), without auth bypass or cross-origin failures.
- Verify airplane -> permitted GPS/receiver -> Germany camera priority and
  meaningful no-aircraft, stale-feed, decoder-off, offline-map states.
- Verify Stop/Start/Restart with the real Nooelec NESDR SMArt v5, not just
  green systemd state. Test USB busy and competing SDR module handoffs.
- Test source provenance and online/hybrid data integrity when configured.
- Preserve UI feature parity on mobile; do not hide features permanently.
- Test low-power Raspberry Pi Base and on-demand receiver lifecycle.
- Audit actual frontend/screenshots visually; green unit tests do not
  certify responsive UX or physical reception.

## Related existing handoffs

- [Standalone feature-parity gate](FEATURE_PARITY_AND_SURVIVAL_KIT_GATE.md)
- [Receiver lifecycle/Germany map repair handoff](SURVIVAL_KIT_FLIGHT_RADAR_HANDOFF_2026-11-05.md)

**Survival Kit agents: read this document before designing the rich-map module;
record these as acceptance criteria in the existing stage ledger. Do not
restart the Survival Kit project, overwrite existing source ownership, or
replace the full tar1090 UI with a feature-incomplete implementation.**
