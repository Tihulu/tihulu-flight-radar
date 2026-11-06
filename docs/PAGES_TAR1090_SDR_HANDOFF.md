# GitHub Pages, tar1090 Internet overlay and SDR lifecycle

Status: draft PR https://github.com/Tihulu/tihulu-flight-radar/pull/6.
No main branch modifications or public deployment in this PR.
The intended Pages URL is https://tihulu.github.io/tihulu-flight-radar/.
A green pull-request check does NOT establish that the Pages URL is live.

## GitHub Pages

The site is static and installable as a PWA. It can show real aircraft via:
- A locally installed, authenticated loopback bridge for USB ADS-B and optional Internet data.
- An operator-provided HTTPS endpoint ending in /api/aircraft, supporting CORS from https://tihulu.github.io. This enables Internet-only aircraft without the receiver bridge.

Public adsb.lol and OpenSky endpoints generally do not allow browser CORS access.
The opt-in sample Worker at deploy/cloudflare-worker.mjs and deploy/wrangler.toml is not deployed automatically. To use it, the Cloudflare account owner can run:

    npm exec --yes wrangler login
    npm exec --yes wrangler deploy --config deploy/wrangler.toml

Then paste the *actual deployed URL* ending /api/aircraft into the Pages Internet feed URL field. Before production deployment, confirm ADS-B provider rules, quotas and licensing and configure Worker-side abuse protection. Never embed API secrets in public static HTML. ODbL attribution is required for adsb.lol. The Pages workflow deploys only from main after repository Pages settings use GitHub Actions.

## tar1090 camera and network overlay

Official tar1090 query options from wiedehopf/tar1090/README-query.md include icao, noIsolation, SiteLat, SiteLon, centerReceiver and zoom.
When launched from the native/classic app, tar1090 now focuses on a fresh real antenna aircraft; else authorized receiver coordinates; else Germany (51.1657, 10.4515) as a labeled fallback, rather than its previously saved America viewport. When launched from the Tihulu web map, it uses the actual visible local aircraft or the selected viewport.

On desktop only, tar1090 embedded in Qt WebEngine gains an independent **blue Internet aircraft layer**, an on/off checkbox, last-update/status and per-source deduplication. The extra markers come from the network API and are NOT counted as RTL-SDR messages or stored in tar1090 data. The original upstream tar1090 installation/config.js is never modified. The overlay requires a local/private trusted tar1090 host and must be tested against actual versions.

On GitHub Pages, opening a separate cross-origin tar1090 page can apply the focus URL but cannot inject an overlay into another origin. For combined overlays in an ordinary web browser, use the Tihulu Pages radar map itself. The native tar1090 overlay is not the same as a browser cross-origin modification.

## Receiver release on application exit

Native and classic dashboards default to Release local SDR on exit (can be disabled in Receiver settings). If Linux service mode is active and the preference is enabled, closing the application requests a narrowly scoped stop for readsb.service and tar1090.service; this includes a preexisting local service and does not disable boot settings. If direct mode is used, only the child decoder created by the app is stopped. Remote JSON mode does not control remote hardware. Failures produce a warning instead of claiming the SDR was released.

## Verification remaining

Run CI and real Pop!_OS COSMIC Wayland/Nooelec NESDR SMArt v5 tests: start receiver, check genuine message growth; open full tar1090 and check focus and blue Internet overlay; close the app, verify readsb inactive and rtl_test can claim the tuner. Check Windows/macOS packaging, ARM64 Pi, browser Pages 200, upstream rate limits, and map 403 fallback before merging to main.
