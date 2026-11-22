# TIHULU Flight Radar — Web 0.3.2.dev4

**Frozen:** 2026-11-21 · **Source:** main `75edc0efe478ca96febc5bb7b2721400a42889c2`
(app.js SHA256 `f99fbcfb700c…`, byte-identical with the live origin) · **Copy:** `site/` (47 MB, 31 files)

## Live access (recommended)
- Standalone: https://tihulu.github.io/tihulu-flight-radar/
- TEXT CENTER mirror: https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/

Both origins are built from the same source; `source-revision.json` must show the same
`source_sha`. The mirror site synchronizes periodically (a few minutes of delay possible).

## One-line local server (from this copy)
```
git clone --depth 1 https://github.com/Tihulu/tihulu-flight-radar.git tfr && \
cd tfr/versions/web-0.3.2.dev4/site && python3 -m http.server 8811
# Browser: http://localhost:8811/
```
Internet aircraft work; USB reception requires HTTPS (WebUSB does not work outside
localhost — an expected browser security rule).

## Contents
- RF area/circles and the five-layer RF history model (rf_history_*)
- Show BEST on map + LIVE cards · flight journey · map motion
- Resizable aircraft panel · source-based loading (Load · Radio / Load · Internet)
- Rich aircraft detail/multi-selection UI · full upstream tar1090 (GPL, bundled)

## Verification
```
curl -sS https://tihulu.github.io/tihulu-flight-radar/app.js | sha256sum   # f99fbcfb700c...
```
