# tar1090, direct WebUSB and Internet aircraft — source handoff

Updated 6 November 2026. Applies to Tihulu Flight Radar desktop (Qt), GitHub Pages, and installed PWA.

## Observed, physically verified USB state

Nooelec NESDR SMArt v5 RTL2832U `0bda:2838` works in the browser after the Linux `dvb_usb_rtl28xxu` kernel driver is explicitly unbound from its exact matching interface. **Do not re-plug after unbind before browser capture.** The direct browser receiver showed genuine CRC-verified Mode S messages and 11 antenna aircraft on the user's screenshot. Never modify or stop OS services from a website. Use the optional per-device helper in `scripts/rtl-sdr-usb-interface.sh` only from an explicit user command, after inspecting its code.

## Why the original tar1090 page was grey

The installed `http://127.0.0.1/tar1090/` HTML can remain reachable while its **separate readsb/dump1090 receiver data** has stopped. tar1090 calls `data/aircraft.json`, not the JavaScript WebUSB decoder running in another HTTPS tab. The original page then shows `n/a` and "Problem fetching data from the server". The map tiles may also appear grey if OSM tiles or other resources failed, which is an independent issue.

Verify from Pop!_OS without changing any service:
```bash
systemctl is-active readsb.service || true
curl -sS -i --max-time 5 http://127.0.0.1/tar1090/data/aircraft.json | head -c 600
curl -sS -I --max-time 5 http://127.0.0.1/tar1090/
```
A `200 text/html` page is NOT sufficient. A working decoder supplies readable JSON including a recent `now` timestamp and an `aircraft` list, even if the list is legitimately empty.

**One USB device cannot simultaneously be owned by WebUSB and readsb.** While direct WebUSB has the receiver, use the Flight Radar **Full radar map**. This expanded map uses the current tab's actual antenna frames, selected Internet feed and I/R source filters and never pretends to control readsb. The explicit **External tar1090 (readsb required)** action is for an independently running decoder (for example a separate receiver) and is suppressed in WebUSB mode. After hard-stopping this tab's USB, the user may separately restore/launch readsb if they choose. The native classic application checks actual recent tar1090 `data/aircraft.json` before opening it; stale or missing JSON falls back to the built-in map rather than a blank, misleading tar1090 panel.

If `data/aircraft.json` is genuinely live but OSM map tiles are blank, investigate browser DevTools Network requests and tile server response / rate limits separately; do not attribute every grey background to RTL-SDR hardware.

## Real Internet aircraft on static GitHub Pages

The website does not host a server; a public URL does not imply browser CORS permission.

- **IntelSky (default browser preset):** documents HTTPS browser CORS and exposes a live global `ac` snapshot at `https://intelsky.org/api/`. The app validates the provider timestamp, filters positions within the chosen map search region, validates ICAO24 IDs, preserves `position_source=internet`, and shows **limited military/government network coverage**. It is not a complete sivil/general aircraft feed. Zero in the region does not prove a failed source or antenna.
- **AirLabs (opt-in):** provides a browser CORS-compatible, API-key-based `/api/v9/flights` feed. User provides their **own** key for the current tab. It is sent to AirLabs in a query string and can be visible in browser developer tools; do not embed a shared key. Positions and `updated` timestamps are validated; documented altitude metres are converted to feet and speed km/h to knots before altitude color and flight table display. Automatic calls are no more frequent than 60 seconds to limit quota use, and free plans may offer limited fields/usage.
- **Custom HTTPS/CORS feed (opt-in):** validated `/api/aircraft` endpoint, without URL-embedded credentials. Must return `{generated_at,aircraft,provider,attribution}` and real fresh positions with `hex`, `lat`, `lon`, `seen`, `seen_pos`. Example owner-operated and source-attributed proxy in `deploy/cloudflare-worker.mjs` **is not deployed** by GitHub Pages. adsb.lol and adsb.fi APIs generally do not allow direct cross-site browser reads; a configured authorized relay is needed for those. Provider policies, CORS headers and rate limits must be checked before deployment.
- **Off:** no Internet traffic. The RTL-SDR can still receive local ADS-B.

Source **Antenna** always means a genuine local decoder observation; **Internet** means an external provider observation; **Both** means a valid matching ICAO seen in both. The position retains the true per-record position source. Never mark web-only positions as RF or invent a location when one is absent.

The app reports HTTP errors, no CORS, invalid schema, stale timestamps, 429 cooldown, source attribution, observed counts and "limited coverage". OSM tiles require network and are separate from aircraft data. AirLabs keys remain in the UI session only, never in local storage or a GitHub commit.

## Release gates

- Browser source parsers and Hybrid dedup tests pass under Node before promoting draft PR.
- Native UI source has a real tar1090 backend verification test.
- A physical WebUSB test on Pop!_OS already confirmed local ADS-B reception; tests do not prove the upstream IntelSky/AirLabs service will be reachable or return flights at an arbitrary moment.
- The existing GitHub Pages app path is `https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/`. The independent repository Pages URL has not been enabled and should not be advertised as published.
- The main branch remains separate from the draft, and distribution to existing TEXT CENTER Pages happens only through its pinned source workflow after tests pass.
