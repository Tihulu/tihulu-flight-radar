# Flight Radar web app, GitHub Pages and local receiver bridge

**Status:** First working code candidate on `feature/github-pages-local-bridge-2026-11-06`. GitHub Pages is **not deployed** until the PR is accepted and Pages is enabled with **GitHub Actions** in repository Settings. Hardware tests are pending.

## Architecture

The same static files live at `tihulu_flight_radar/web/` and can be served by GitHub Pages or by the local bridge.

- GitHub Pages target, after deployment: `https://tihulu.github.io/tihulu-flight-radar/`.
- Local browser frontend: `http://127.0.0.1:8510/`.
- Companion backend: Python 3.11+, readsb-compatible receiver already installed and configured, or remote provider adsb.lol.
- The bridge is **loopback-only** and requires a random pairing token on every API request, including read-only queries. The token is printed to its own local terminal, never embedded into GitHub Pages or shared upstream.
- Website API calls from `https://tihulu.github.io` require browser permission for local network/loopback access in supported browsers. Strict CORS, origin/host checks and bearer authentication still apply. No security-header bypasses.
- The bridge is **not** a LAN server for mobile/Raspberry Pi hotspot yet. Implementing a TLS-secured, explicitly paired LAN gateway is a separate acceptance gate. Accessing an HTTP Pi address from an HTTPS Pages page is **not** supported.
- GitHub Pages cannot run readsb or Python; direct USB access from all browsers is not reliable. Internet-only aircraft data from Pages also requires a paired local bridge in this first version, because provider browser-CORS access must not be assumed. A separately approved hosted proxy or provider-supported CORS service is a future possibility.

## Start the companion (all supported Python platforms)

In a checkout of this branch:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps .
tihulu-flight-bridge
```

On Windows PowerShell, use `.venv\Scripts\Activate.ps1` and `python -m pip ...` (Windows Python may be called `py -3`). The bridge uses the Python standard library and does not need Qt; the main standalone desktop app retains its own PySide6 dependency and existing installer/build process.

The process prints:

- The local web UI address.
- The local API origin.
- A new random **session pairing token**. Keep it private.

Open the local UI, or the GitHub Pages site when it is published, enter the printed bridge URL and token, then click **Connect**. Use **Antenna only**, **Internet only**, **Hybrid** or **Auto**, and choose which colored source overlay is shown.

To permit browser-based receiver Start / Stop / Restart explicitly, run:

```sh
tihulu-flight-bridge --allow-control
```

Without this option the web controls are disabled. On Linux services mode, existing `readsb` / `tar1090` units and restricted sudoers permissions must already work; no unrestricted administrator privilege is installed or requested. On Windows, macOS and on Linux without services the existing `ReceiverController` can launch a separately installed, compatible `readsb` executable. **Windows native RTL-SDR driver + readsb remains unvalidated**, and a working build is not proof of direct reception.

**Raspberry Pi 5 ARM64:** use a Python 3.11+ environment and install this project's source with `--no-deps` for the lightweight bridge; the separate ARM64 runner compiles/tests it. Raspberry Pi GPIO, kernel, HAT, USB permissions, real RF reception and secure hotspot/LAN gateway require Pi-side testing.

## Data and privacy behavior

- Local readsb messages are never uploaded by this implementation. When Internet data is selected, the bridge queries `api.adsb.lol` with the current map center and bounded radius (10–250 nautical miles; currently default 100), so the chosen center is shared with that provider. The provider's API data has ODbL 1.0 attribution; follow provider conditions before redistributing stored snapshots.
- Online refreshes are cached and limited in the bridge; HTTP 429 triggers backoff. No online backend polling starts until a browser actually requests an online source. Closing the tab stops client polling.
- Only plausible, fresh, genuine positions render as aircraft markers. ICAO24 matches are represented as a single aircraft with distinct source observations. RF message totals are not affected by Internet data.
- Source layers are a *visibility filter*, not a command to retune or stop the RTL-SDR. Local-only operation does not require Internet and map grid rendering does not require online tiles.
- This first web version does **not** yet replace the full native Qt desktop dashboard or detailed tar1090 viewer. They remain available through their existing interfaces. A link to an installed tar1090 endpoint can be configured in later UI parity work.

## Builds and delivery

The existing `build.yml` continues to build Windows x64, macOS ARM64, Ubuntu x64, Debian 12 x64 previews. The new `bridge-arm64.yml` uses a Linux ARM64 CI runner for a **source-based Pi bridge preview**. There is no Pi-specific native GUI or validated device image yet.

The `pages.yml` workflow validates static files on PRs and deploys only from `main` after the required GitHub Pages configuration. The endpoint must not be called active until deployment actually succeeds.

## Release acceptance not yet met

- Confirm GitHub Pages deployment and loopback CORS/local-network permissions on Firefox, Safari, Chrome, Windows, macOS and Linux.
- Validate direct RTL-SDR reception + Stop/Start/Restart on Windows x64, Pop!_OS/Ubuntu/Debian, macOS Apple Silicon and Pi 5 ARM64.
- Add secure LAN/mobile bridge via TLS and device pairing, including `tihulu.lan` Survival Kit routing when actually installed.
- Connect the same source-aware backend to the full tar1090 viewer and complete all earlier feature-parity visual and telemetry gates.
- Verify provider availability, ODbL obligations, aircraft feed quotas, result schemas and privacy flows against real live API responses.

Issue tracking: [Flight Radar #5](https://github.com/Tihulu/tihulu-flight-radar/issues/5), [Survival Kit #9](https://github.com/Tihulu/tihulu-survival-kit/issues/9).


## Desktop GUI repair: use an application window, not a browser (2026-11-06)

After a user screenshot showed a nonfunctional unpaired page, an invalid bare `127.0.0.1:8510` URL and mixed `403 Access blocked` OSM tiles, the design was corrected:

- `tihulu-flight-radar` now starts `tihulu_flight_radar.native:main`, an actual **Qt WebEngine main window** with the responsive source-aware radar. It starts a randomly ported loopback bridge and passes its ephemeral pairing token to the trusted embedded page after load. No URL entry, terminal token or external browser is required in the native window.
- `tihulu-flight-radar-classic` starts the original Qt dashboard. The new native window also offers **Receiver → Open full classic receiver dashboard** and shares the same receiver controller (no duplicate RTL-SDR ownership). Legacy map buttons use Qt WebEngine dialogs instead of `webbrowser.open`.
- COSMIC Applications launchers include **Tihulu Flight Radar** (native), **Tihulu Flight Radar Live** (old Web shortcut updated to native), and **Tihulu Flight Radar Classic** (preserved).
- Standalone GitHub Pages browsers now normalize `127.0.0.1:8510` into `http://127.0.0.1:8510`. The bridge still must actually be running, and the token is required in a browser.
- The bridge now serves `Referrer-Policy: strict-origin-when-cross-origin` rather than `no-referrer`, to comply with [OSM tile server requirements](https://operations.osmfoundation.org/policies/tiles/). Browser reload and clearing previously blocked cached tiles may be necessary; the offline coordinate grid remains usable if third-party map tiles still refuse access.
- Qt WebEngine is a new desktop dependency: `PySide6-WebEngine`. Linux package installation includes its additional shared libraries. Raspberry Pi headless bridge remains independent of this optional large GUI engine.

### Remaining verification gates

- Test the native Qt window and the browser map on the user's real Pop!_OS COSMIC Wayland desktop, including NVIDIA/Qt GPU interaction.
- Verify macOS ARM64 and Windows x64 Qt WebEngine packaging and runtime, not merely wheel installation.
- Confirm OSM volunteer tiles load with proper Referer and rate-limited cache usage. Never evade OSM blocks by disguising the client; use alternate authorized providers or offline tiles if still blocked.
- Test RF reception with actual attached RTL-SDR, local readsb and hardware ownership.

These are draft changes in [PR #6](https://github.com/Tihulu/tihulu-flight-radar/pull/6), not a released update.

## November 6, 2026 — Why native shows Internet planes but static Pages showed radio only

The desktop application uses its own Python-backed `DataProvider` to call
`api.adsb.lol` / `adsb.fi`. A static GitHub Pages origin cannot directly read
those APIs without the providers enabling browser CORS. Previously the web
app defaulted to IntelSky, a **military/government-only** CORS-compatible feed,
so 0 Internet aircraft near Cologne was possible even while the desktop
showed dozens of general flights. **This is not a USB RF failure.**

The browser/PWA now offers a clearly identified **experimental general ADS-B**
source, using the external public `cors.dev` gateway to read the
`adsb.lol` point API without running a local bridge. Selection is visible
above the radar; in WebUSB mode it is queried alongside true radio messages
with independent timestamps and I/R source badges.

Limitations to be transparent about:
- The public gateway is **not operated by TIHULU** and may be unavailable,
  deny a request, rate-limit its shared egress IP, or be blocked upstream.
  It is not a guaranteed replacement for the native desktop backend.
- A public gateway sees the browser's IP address and **coarse map center**
  (rounded to 0.1°). No WebUSB IQ, pairing token, AirLabs API key, or
  permissioned high-precision GPS coordinate is forwarded.
- Requests to the shared gateway are rate-limited by the client and bounded
  to fixed public ADS-B point endpoints; no arbitrary URL proxying.
- Source attributions: **adsb.lol, ODbL 1.0**; the gateway is separate.
  Only actual fresh records from `now` / `seen` / `seen_pos` count as
  Internet observations. Duplicate ICAO24 IDs combine into one I/R icon.
- If the relay fails, the SDR stays open and real antenna counts remain.
  The UI reports the specific error. Network CORS, API usage permissions,
  upstream quota and availability still need real browser acceptance tests.
- For reliable use, deploy the existing
  `deploy/cloudflare-worker.mjs` to a **user-owned HTTPS hosting account**
  after checking upstream terms and rate limits; enter its fixed
  `/api/aircraft` URL via Custom provider. Never pretend GitHub Pages alone
  includes a live server, and never embed private API keys in static JS.

The browser-only source is an enhancement to, not a replacement for,
the existing local receiver service and separate tar1090 integration.
