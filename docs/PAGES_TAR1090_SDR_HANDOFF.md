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


## 2026-11-06 — follow-up to screenshot: 27 Internet, 0 RF messages, tar overlay stuck

Screenshot-confirmed behavior in actual native Qt build:
- Main responsive radar was paired successfully and displayed 27 **real
  online** aircraft, demonstrating the network feed and auto-pairing worked.
- readsb and tar1090 processes were marked active but readsb reported **zero
  receiver messages**. Running processes do not prove USB capture or RF
  decoding; no software must claim otherwise.
- The embedded tar1090 map rendered tiles but the added overlay stayed
  `Internet overlay: waiting for tar1090 map…`. This is a **separate**
  Qt WebEngine OpenLayers attachment problem, not evidence of absent
  online planes.
- The initial map view was centered around Germany's geographic midpoint,
  near Erfurt, which did not match the user's intended Cologne view.

Changes on Draft PR #6:
1. `TarOverlayView` explicitly executes the map probe and online feature
   renderer in Qt WebEngine **MainWorld (0)**. The probe reports a
   `ready/reason` result, catches JavaScript exceptions, retries immediately
   after load, and presents real diagnostic text when OpenLayers is not ready.
   No infinite silent “waiting” label if a probe fails. The same camera-only
   site-location protection and ring hiding remain intact.
2. The embedded tar1090 window has a **separate Internet feed cache**. Earlier
   it shared the main radar's global 35-second cooldown for one coordinate
   key; a different tar map center consequently returned zero planes.
   Each view queries only when opened/required; upstream provider backoff and
   licensing still apply. A Qt window displaying tar1090 without OpenLayers
   symbols must clearly report the limitation; never invent overlays.
3. Native desktop initially selects the **Cologne city region** (coarse
   50.938 N, 6.960 E, not the physical receiver location). Web default
   remains Germany. Both expose explicit Cologne, Germany, GPS-permission
   and Search Here controls. The map **camera center and online search
   center are independent**, so focusing an aircraft no longer changes the
   API coordinate cache key and makes planes disappear.
4. Internet provider per-request timeout now fits inside the frontend's
   timeout. Brief failures preserve only last *genuinely received*
   observations with monotonically increasing seen/seen_pos ages;
   old planes vanish automatically beyond their freshness limit.
   Provider names, attribution and last genuine observation time are shown.
5. RF source state `decoder_no_rf_messages` shows explanatory diagnostics:
   check `journalctl -u readsb -n 40 --no-pager`, 1090 MHz antenna, USB
   device exclusivity, and previous Satellite Center/Brave sessions.
   This is read-only diagnosis; no opportunistic USB reset, driver unload,
   readsb restart or permission bypass is performed.

**Still pending**: physical validation of Nooelec ADS-B messages and correct
tar1090 OpenLayers overlay positioning on the user's Pop!_OS COSMIC Qt
runtime. Cross-platform CI verifies source/logic but cannot substitute for
live RF hardware.


## 2026-11-06 — Startup camera hierarchy (requested)

Both native Qt and GitHub Pages/browser radar share the following **startup
camera priority**:

1. **Current location**, only if the user explicitly grants browser
   geolocation. Qt WebEngine displays a Yes/No dialog for its trusted
   loopback origin; no background location permissions are granted.
2. If not available or denied, **nearest fresh, genuinely radio-positioned
   aircraft**, choosing the nearest to Cologne as reference when there is no
   location. A plane received by the SDR but positioned solely using
   Internet data does NOT qualify as a radio-positioned plane.
3. If neither is available, **Cologne (50.938 N, 6.960 E)**, a fixed
   fallback center, never asserted as the physical antenna position.

Manual pan/zoom or explicitly selecting/focusing an aircraft overrides
startup automation. Geolocation may upgrade the radio fallback while
permission is resolving but never overrides a manual choice.

Opening tar1090 from the main radar preserves the selected startup camera
instead of jumping to a random Internet plane. Classic tar1090 uses
authorized location, nearest fresh local aircraft, and Cologne. None of
these camera operations overwrites tar1090 physical receiver coordinates.
