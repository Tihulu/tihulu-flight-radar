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

## tar1090 camera, receiver markers, and network overlay

**Bug found in the previous draft:** Using SiteLat/SiteLon to focus tar1090
actually overrides its receiver/site location, sometimes persisting that false
location in tar1090 browser storage. This produced the unwanted large black
range rings and white receiver dot centered in Germany.

Fixed in the current draft:
- Never transmit SiteLat/SiteLon or centerReceiver to fake the receiver's
  physical position just to position the map.
- Use native-view-only tihuluFocusLat/tihuluFocusLon coordinates. The embedded
  Qt OpenLayers page sets the initial map camera **once**, then leaves user
  panning/zooming alone.
- Use tar1090's supported rangeRings=0 switch and hide the
  siteCircleLayer/locationDotLayer *in the embedded Qt view only*, without
  changing tar1090's installation, config.js or actual receiver coordinates.
- Priority remains: fresh genuinely received local plane; authorized receiver
  reference (if available); Germany as a labeled viewport-only fallback.
- In browser-only Pages, tar1090 external links cannot inject camera JavaScript
  into another origin; the Tihulu Pages map itself provides correctly centered
  combined views. The native embedded viewer is the authoritative tar overlay.

The native Qt embedded tar1090 viewer also has an independent blue Internet
aircraft layer and a visible loading/error/status panel, including online
provider freshness. The public ADS-B provider is queried by the local Python
bridge. No Internet aircraft are credited to the user's SDR RF messages.
Upstream tar1090 is never modified. adsb.lol is the primary source; for
**personal, non-commercial** local use, adsb.fi is a secondary fallback with
source-specific attribution, subject to its published limits.

If an earlier app version already stored a fake receiver location in an
individual browser's tar1090 localStorage, the updated native view hides its
visual marker but does not silently delete that user's settings. Check the
tar1090 site's own site-location settings separately before trusting any
receiver position-based radius or distance reporting.

## Receiver release on application exit

Native and classic dashboards default to Release local SDR on exit (can be disabled in Receiver settings). If Linux service mode is active and the preference is enabled, closing the application requests a narrowly scoped stop for readsb.service and tar1090.service; this includes a preexisting local service and does not disable boot settings. If direct mode is used, only the child decoder created by the app is stopped. Remote JSON mode does not control remote hardware. Failures produce a warning instead of claiming the SDR was released.

## Verification remaining

Run CI and real Pop!_OS COSMIC Wayland/Nooelec NESDR SMArt v5 tests: start receiver, check genuine message growth; open full tar1090 and check focus and blue Internet overlay; close the app, verify readsb inactive and rtl_test can claim the tuner. Check Windows/macOS packaging, ARM64 Pi, browser Pages 200, upstream rate limits, and map 403 fallback before merging to main.

## Diagnosing antenna and online source failures

The old native radar ignored the user's saved Direct readsb / Remote JSON
receiver mode and always defaulted to Linux services. On exit, the new
release-on-exit policy stops local readsb, but startup previously did not
restart it. The native app now loads the saved mode, falls back to a direct
readsb binary when the systemd unit is absent, and (by default) asynchronously
starts its local receiver at launch. There is a Receiver menu checkbox to
disable auto-start. Startup failures appear in the status bar and receiver
panel; failed network sources show their provider error rather than an empty
unexplained map.

A valid running readsb process is **not proof of RF reception**. On real
hardware verify readsb's fresh message counts and timestamps separately.
The bridge never fabricates messages, positions or aircraft.

Before using the preview on real Nooelec hardware, ensure no concurrent
rtl_433, rtl_test, welle.io or SDR module is claiming the single USB tuner.
If the source remains unavailable, inspect the actual application error and
readsb/tar1090 systemd journal rather than repeatedly reinstalling.
