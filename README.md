# Tihulu Flight Radar

## Location chooser — same as Satellite Center (0.3.2.dev4)

From either the standard radar map **Choose place** or full original
tar1090 **Choose place**, select Germany / Türkiye; browse one of 16 German
Bundesländer or 81 Turkish provinces; then choose a city, town, municipality,
or district locality. The same **ODbL-licensed 8,084-entry offline catalog**
(7,104 Germany and 980 Türkiye) and accent-insensitive search from Satellite
Center is bundled into web, PWA and native desktop builds. Examples: Köln,
Hürth, İzmir, Karaburun and Bornova. Country/region selection does not
change location until a specific place or manual coordinates are applied.
Choose 25–250 NM Internet search radius, manual WGS84 coordinates, or
explicit browser GPS. **Search worldwide online** uses opt-in Open-Meteo
Geocoding only on click; typed offline names are never sent to a provider.

The chosen place and search radius are stored in browser-local settings on the
web. On native Qt/Pop!_OS, a token-protected loopback endpoint stores the
selection in an owner-private configuration file (Qt ports change on restart).
the next launch. The UI never changes actual antenna/SDR location, starts
or retunes readsb, or invents RF planes; it only changes the map camera and
Internet ADS-B query center. The same selected map camera is applied when
the tar1090 iframe is open. Browser Pages without an antenna still work.
Offline place records are **approximate settlement coordinates**, not
complete statutory district/Kreis boundaries: some smaller municipalities
may be missing; use optional online search or manual coordinates instead.
Full provenance: [CITY_DATA_LICENSE.md](tihulu_flight_radar/web/CITY_DATA_LICENSE.md).


## Preview 0.3.2.dev4 — full tar1090 on web and desktop without an antenna (6 Nov 2026)

Both web Pages mirrors and the installed Pop!_OS native Qt WebEngine use the same original upstream tar1090 aircraft map, right-hand aircraft table, advanced filters, OSM map, altitude colors and source badges. Use **Full tar1090 map** in the top bar, or append `?view=tar1090` to a radar URL. The original Internet stream remains selectable. All sources can be merged by ICAO24; real local RF is entirely optional. Browser Pages may be limited by third-party API CORS/quotas. The native app now exposes the independent Internet provider checkbox layers rather than hiding them.

The **same complete upstream tar1090 interface** now opens from the browser
and from the native Pop!_OS app when no RTL-SDR/readsb receiver is attached.
It accepts actual Internet-only aircraft, real radio-only observations or
ICAO24-deduplicated **I/R** hybrids. The original tar1090 map, photo/aircraft
details, sidebar, filters, metadata and source badges are retained. The full
GUI has explicit **Internet (I)**, **Radio (R)** and **Both (I/R)** display layers.

Pop!_OS installer caches the complete tar1090 HTML/JS/aircraft metadata at
`~/.local/share/tihulu-flight-radar/tar1090` so the native app can serve
it safely from its private loopback bridge. If the optional cache fails, the
app can use the trusted HTTPS Pages copy. The cache is static assets, **not**
fabricated aircraft; actual Internet planes still require a working provider.
An antenna is never automatically required to open tar1090, and fresh installs
do not automatically start/readsb-claim the SDR.

**Preserved legacy:** `legacy/v0.3.1` at
`67280cd84feb89faec6a80f5fe2a55ce5f7b89e6` remains untouched.
The installer upgrades the **same pipx environment**, not a parallel app;
users can always restore the 0.3.1 commit via the pinned version switcher.
Read [the full tar1090 guide](docs/ANTENNA_OPTIONAL_TAR1090.md) and
[the Pop!_OS version guide](docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md).
The optional 0.3.2.dev4 preview has not been physically certified on the
user's Nooelec receiver yet.

## Pop!_OS upgrade with preserved 0.3.1 legacy rollback

The known-good **0.3.1** source snapshot is archived at
[`legacy/v0.3.1`](https://github.com/Tihulu/tihulu-flight-radar/tree/legacy/v0.3.1)
(exact commit `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6`).
The new opt-in **0.3.2.dev4** Internet-only original-tar1090 preview is archived at
[`preview/v0.3.2-dev4`](https://github.com/Tihulu/tihulu-flight-radar/tree/preview/v0.3.2-dev4)
(source commit `def7a62ff6951951bc3a432b93da3251c7ea4162`).

**Close the app before switching.** Download the version switcher once:
```bash
curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/preview/v0.3.2-dev4/scripts/popos-version-switch.sh -o "$HOME/tihulu-flight-switch.sh"
```
Then replace the old installed pipx application with the preview:
```bash
bash "$HOME/tihulu-flight-switch.sh" preview
```
Or restore the original 0.3.1 snapshot whenever needed:
```bash
bash "$HOME/tihulu-flight-switch.sh" legacy
```

The wrapper uses exact Git SHAs, `pipx install --force` (one application,
not two installed copies), desktop shortcut refresh and an installed version
check. Do **not** purge `readsb` or `tar1090`: their services and SDR
settings are preserved. The archived GitHub source represents the last
pre-multi-provider 0.3.1 code; a local `0.3.1` version string alone cannot
prove the same source commit. Full details:
[Pop!_OS version install and rollback](docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md).


## Multi-source base functionality (introduced in 0.3.2.dev0; retained in 0.3.2.dev4)

**The existing installed Pop!_OS 0.3.1 is the user-verified stable baseline.
Do not auto-upgrade or silently replace it.** The following features are in the
reviewed development branch only until acceptance.

- Browser and native Qt WebEngine radar now expose an **Internet source selector**:
  adsb.lol (unchanged and individually available), adsb.fi (personal/non-commercial),
  OpenSky (API credits; at most every 5 minutes), and limited IntelSky. The
  `Combine selected` mode is the new browser preview default with adsb.lol
  and adsb.fi on; **Select all available** adds the others. Individual source
  checkboxes act as inclusion layers. Airplanes.live is labeled disabled
  because public API use currently requires feeder authorization.
- Each Internet network has independent bounded polling, TTL and 429/CORS
  diagnostics. The original adsb.lol-only mode is always available. When a
  public relay blocks or throttles a network, its actual availability is
  shown; the app does not invent flights or label cached stale records live.
  GitHub Pages uses a third-party CORS relay, not a guaranteed private service.
  For production reliability, provision a bounded owner-hosted HTTPS relay
  after verifying provider use policies; never publish credentials.
- Aircraft are deduplicated by **verified six-character ICAO24** across all
  selected Internet sources. Each record retains the list of networks and
  individual raw observations. The `I` badge is Internet-only; **`I/R` only
  appears when the same ICAO is also genuinely received locally**. Local RF
  position, counters, and observations take priority, as in 0.3.1.
- The optional native bridge accepts a `net=adsblol,adsbfi,opensky,intelsky`
  query *only on an authenticated, explicitly paired local endpoint*.
  Without `net`, the original adsb.lol + adsb.fi fallback code path remains
  untouched. The new companion never starts or takes over an SDR when
  gathering Internet-only flights.
- Identical browser assets are expected at
  https://tihulu.github.io/tihulu-flight-radar/ and
  https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/
  only after **both publishing runs and Pages deployments** succeed.
  The sole browser source is `tihulu_flight_radar/web/` in this repository.

**Verification:** source-level and synthetic fixture tests are not a live
API/CORS uptime guarantee, nor proof of an automatic update on the user's
computer. Keep the existing 0.3.1 installed until the optional development
preview is manually installed and physically tested.


## Current browser preview — source ownership and real Internet options (6 Nov 2026)

**Publishing targets (verify both deployments and matching source-revision.json):**
https://tihulu.github.io/tihulu-flight-radar/ and
https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/.

The user has **physically confirmed** real Nooelec 0bda:2838 browser WebUSB Mode S reception after releasing its specific Linux DVB driver; the same physical SDR cannot also run readsb/tar1090. When WebUSB is active, **Full radar map** expands the same real source-aware browser map without opening an empty legacy tar1090 backend. **External tar1090** requires separately running readsb and a current `data/aircraft.json`; the native classic app checks JSON freshness before opening.

Browser Internet sources: built-in **IntelSky** (real CORS-enabled *limited military/government* feed); opt-in **AirLabs** (own browser-visible key, usage quotas and plan-dependent fields); or trusted HTTPS/CORS `/api/aircraft` source for wider coverage. adsb.lol/adsb.fi generally need an authorized cross-origin relay. Never mark an Internet-only plane as RF. The full details and troubleshooting are in [tar1090 and Internet source guide](docs/TAR1090_WEBUSB_AND_INTERNET_SOURCES.md).

**Status:** Release is still a draft PR, and real end-to-end tests of every Internet API/CORS path and native UI on user hardware are pending. Node/Python CI tests are not proof of provider uptime or new device support.


English-language, local-first ADS-B / Mode S receiver desktop software.

**Current development branch version 0.3.2.dev4; user's stable legacy baseline 0.3.1.** Uses real receiver data only. It never
creates simulated aircraft or positions. ADS-B broadcasts may contain locations;
Mode S does not guarantee location. MLAT positioning requires synchronized
multiple receivers and is **not** calculated by this app.

## Browser-first GitHub Pages (experimental, no desktop installation)

**Intended URL after release:** https://tihulu.github.io/tihulu-flight-radar/

The current **draft PR #6** adds a static, install-free aircraft radar that runs
inside Chromium-based browsers (Brave, Chrome, Edge). No Python, readsb,
local service, npm or pairing token is required for the **direct USB** path:

1. Open the HTTPS page in Brave/Chrome/Edge. Permit current location if you
   want the map to start there; otherwise the first valid radio-positioned
   aircraft is chosen, or Cologne if none exists.
2. Click **Choose RTL-SDR & start**, and explicitly select the Nooelec
   RTL2832U USB receiver. It tunes to 1090 MHz at 2 MSps.
3. The browser decodes genuine Mode S/ADS-B DF17/18 frames with CRC
   verification in a Web Worker, and plots airborne positions only after
   valid recent even+odd CPR frames are received. Source badges are Antenna,
   Internet and Both; Internet-only positions are never labeled as RF.
4. Click **Hard stop / release USB** before another SDR application needs
   the device. The page also releases its USB handle when hidden/closed.

The JavaScript RTL-SDR driver is pinned to version 3.0.7 and **bundled into
the GitHub Pages artifact during CI**. Nothing is installed on the viewer's
computer, and a third-party runtime JavaScript CDN is not required.

**Internet aircraft without USB:** use the advanced settings to enter a
trusted HTTPS endpoint with an accessible browser CORS policy. Public
adsb.lol/adsb.fi endpoints do **not** support third-party browser CORS; an
authorized Internet feed or optional user-operated relay is still needed
for this *different* source. GitHub Pages itself has no server backend.

**Hardware limitations:** WebUSB only works in compatible browsers; Linux
USB permissions and conflicting readsb, Gqrx or DVB drivers may need
manual OS-level attention, and Windows may need a compatible WinUSB driver.
The website cannot stop a process or change privileged OS settings.
Firefox and Safari can use the map with Internet/paired sources but do not
support direct WebUSB.

**Status:** Static protocol tests pass on synthetic IQ/known real Mode S
frames; actual RTL-SDR hardware/WebUSB streaming, CPU cost, OS driver
compatibility, and independent tar1090 parity need physical acceptance tests.
The Pages workflow deploys only from the reviewed `main` branch after
a successful GitHub Actions release, **not from this draft PR**.

See [browser-only implementation and release gates](docs/PAGES_TAR1090_SDR_HANDOFF.md).

## Targets and current limitations

| OS | Desktop UI | Direct RTL-SDR | Remote receiver |
| --- | --- | --- | --- |
| Debian / Ubuntu / Pop!_OS x64 | Qt / PySide6 | Existing readsb/tar1090 systemd, or local readsb executable | Yes |
| macOS Apple Silicon (M1/M2/M3/M4) | Qt / PySide6 | Homebrew readsb and compatible RTL-SDR | Yes |
| Windows x64 | Qt / PySide6 | Only with a separately supplied working readsb binary and USB driver; not packaged or validated | Yes |
| Raspberry Pi Linux ARM64 | Python source | Existing readsb daemon or separately installed readsb | Yes |

The build workflow produces preview artifacts on Ubuntu Linux x64, Debian 12
x64, Windows x64 and macOS ARM64 runners. A successful build **does not** prove direct USB reception
on every device. No drivers, decoder binaries, or permission policies are bundled.

## Debian .deb preview

The Debian 12 workflow produces an unsigned Debian package as well as a
portable application folder. Install with:

    sudo apt install ./tihulu-flight-radar_0.3.1_amd64.deb

The new package does not overwrite the earlier tihulu-adsb-radar v0.2.0.
It adds a documented restricted sudoers rule for sudo-group administrators
allowing *only* start/stop/enable/disable of readsb and tar1090. This avoids
password prompts after the one-time package installation. Review
packaging/linux/sudoers.conf before installation. The app does not install
a decoder or RTL-SDR driver by itself.

## One-line install / update (Pop!_OS, Ubuntu, Debian)

The installer updates the existing Tihulu Flight Radar through pipx and refreshes COSMIC/XDG Applications shortcuts. **The default desktop application is now a real Qt WebEngine window; it does not launch a system browser.** The bundled local receiver bridge pairs automatically, so there is no `127.0.0.1:8510` field or session token to enter in the native app.

- **Tihulu Flight Radar** — new native in-app live radar with Antenna/Internet/Hybrid/Auto source modes, overlays and map.
- **Tihulu Flight Radar Live** — replaces the old "Web" Applications shortcut; opens the same native radar window, not an external browser.
- **Tihulu Flight Radar Classic** — preserves the earlier native Qt dashboard with all receiver controls, raw details, quick exports and full tar1090 access. It can also be opened from the new app's **Receiver** menu. Its maps now open inside Qt windows.

**Install or update the current draft preview with one command (run as your regular user):**

```bash
bash -c 'set -euo pipefail; f=$(mktemp); trap "rm -f \"$f\"" EXIT; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/feature/github-pages-local-bridge-2026-11-06/scripts/install-linux.sh -o "$f"; TIHULU_REF=feature/github-pages-local-bridge-2026-11-06 bash "$f"'
```

**Stable installer (only after this PR has passed checks and is merged to main):**

```bash
bash -c 'set -euo pipefail; f=$(mktemp); trap "rm -f \"$f\"" EXIT; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh -o "$f"; bash "$f"'
```

The installer asks for narrowly scoped sudo permissions when necessary, replaces only known obsolete Tihulu application packages and icons, and **does not reset readsb/tar1090 services, other SDR modules, recordings or receiver settings**. Review [the installer source](scripts/install-linux.sh) before allowing package changes. Running the same command again updates the application; if COSMIC has cached the menu, log out/in to refresh it.

The **GitHub Pages version** is separate and still needs a locally launched bridge or compatible hosted API for live data. To start the manual bridge for a browser, use `~/.local/bin/tihulu-flight-bridge` in a terminal, then pair using its token. Browsers now accept `127.0.0.1:8510` and `http://127.0.0.1:8510`. The online OpenStreetMap tile issue has been addressed by sending a policy-compatible origin Referer from the local server; offline coordinate-grid fallback remains available.

**Development caveat:** the native Qt WebEngine app and map fixes are in a draft PR, not yet released or physically validated on every OS/receiver. Windows USB driver/readsb and Pi 5 hardware need separate tests.

## Development run

Requires Python 3.11+ (3.12 recommended).

1. Create a virtual environment: python -m venv .venv
2. Activate it (Linux/macOS): source .venv/bin/activate
   (Windows PowerShell): .venv\Scripts\Activate.ps1
3. Install: python -m pip install -e ".[test]"
4. Launch: tihulu-flight-radar
5. Test: python -m pytest -q

All visible UI copy, messages, docs and workflows are in English.


## GitHub Pages and paired local web receiver (development candidate)

A responsive static web dashboard has been added under `tihulu_flight_radar/web/` for GitHub Pages and local browser use. **This feature is not released or published yet.** The intended project URL after enabling the Pages deployment workflow is `https://tihulu.github.io/tihulu-flight-radar/`.

To use local USB ADS-B data, launch the paired companion on the **receiver computer**, not on GitHub Pages:

```sh
# From a checkout of the development branch (Python 3.11+):
python -m pip install --no-deps .
tihulu-flight-bridge
```

Open `http://127.0.0.1:8510/`, enter the session pairing token displayed in the terminal and choose **Antenna only**, **Internet only**, **Hybrid**, or **Auto**. Bridge hardware controls default **disabled**; use `tihulu-flight-bridge --allow-control` for explicit authenticated hardware Start/Stop/Restart. Local readsb and direct RTL-SDR still require platform-specific drivers/decoder. No Python or USB code can run directly on GitHub Pages. Internet data on the Pages app presently also uses the paired companion (because the public providers' browser CORS support is not assured).

The bridge binds only to loopback. **Pi/Survival Kit secure LAN/mobile connectivity and a no-companion hosted online provider are not implemented yet.** Other platforms can run the local bridge and use the already existing Qt desktop build previews; ARM64 Pi is source-based/CI smoke tested, not yet hardware-validated. The desktop Qt dashboard and full tar1090 viewer are retained unchanged.

See [Web, GitHub Pages and bridge guide](docs/GITHUB_PAGES_AND_LOCAL_BRIDGE.md), [feature issue #5](https://github.com/Tihulu/tihulu-flight-radar/issues/5) and [Survival Kit issue #9](https://github.com/Tihulu/tihulu-survival-kit/issues/9).

## Receiver modes

- **Linux services**: controls an already installed readsb + tar1090 systemd
  service pair. The app uses exactly four narrowly defined commands for
  start/stop/enable/disable with sudo -n. To avoid password prompts, the
  existing v0.2.0 Debian package grants ONLY those commands to members of
  the sudo group via its sudoers drop-in. On other Linux installations,
  configure equivalent limited authorization. Never grant unrestricted sudo.
- **Direct readsb**: launches the separately installed readsb process with
  RTL-SDR at 1090 MHz and a temporary JSON output directory. Does not
  use systemd or request administrator credentials. The app terminates the
  child process on exit. Linux users should STOP the readsb systemd service
  before using this mode with the same dongle.
- **Remote JSON**: enter the full URL to a receiver's readsb
  aircraft.json. Works on all desktop platforms, including Windows without
  local RTL-SDR. The remote receiver remains independently controlled.

macOS Apple Silicon: install Homebrew, then run brew install readsb.
Connect the NESDR dongle and select Direct readsb; never run another SDR
client at the same time. No app admin password is required for this mode.
Windows: use Remote JSON unless a separately tested native readsb executable
and WinUSB RTL-SDR driver are available.

## Receiver health and restart

Start / Stop / Restart operations are serialized and the readsb systemd state
is verified after each transition. An active decoder is **not** proof of
actual RF reception. The UI now distinguishes a running decoder from
receiving ADS-B messages and offers **Receiver diagnostics** on Linux
(read-only systemd / journal output). A newly started readsb service may
have zero messages for a while, especially with antenna, interference
or exclusive USB ownership problems.

When start fails or message counts remain zero, check receiver ownership,
antenna orientation and the last readsb logs. Do not assume an active service
implies aircraft data. See
[Survival Kit handoff notes](docs/SURVIVAL_KIT_FLIGHT_RADAR_HANDOFF_2026-11-05.md)
for integration acceptance criteria.

## Interface, flight data and map

Version 0.3.1 restores the earlier GTK4 v0.2 dashboard capabilities **without replacing or removing the full tar1090 aircraft viewer**. The English-language Qt UI shows the four original live statistics (aircraft, positioned aircraft, messages/second, total messages), mean RSSI, Start/Stop/Restart, boot settings, local LAN tar1090 URL, a full tar1090 map button, automatic timestamped quick JSON export and Save As export. It additionally has a live aircraft list and full readsb observation details including raw received JSON.

The **built-in map** complements, rather than replaces, the full tar1090 viewer. It opens even when there is no active decoder, no aircraft or no valid coordinates. Initial camera priority:

1. Real fresh aircraft positions: focus the nearest valid aircraft relative to receiver/GPS coordinates, or to the labeled Germany map center if no real reference location exists.
2. No fresh aircraft position: center on real explicitly saved receiver coordinates or permitted browser GPS location.
3. Neither aircraft positions nor an authorized reference: show Germany (51.1657°N, 10.4515°E) as a **default map view**, not as a claimed receiver position.

The map buttons include Focus nearest aircraft, Show Germany, Center receiver, Use my location and Set receiver position. Selecting a positioned aircraft in the desktop table can open the built-in map focused on it. Manual zoom/pan is respected until the user requests recentering.

The embedded HTTP map stays on loopback only (prefers 127.0.0.1:8505 for stable browser settings; uses an ephemeral port if occupied). It shows only genuine fresh aircraft position markers and short session tracks. OpenStreetMap tiles are optional and require internet; without tiles, a geographic coordinate grid remains available. The installed full tar1090 viewer retains its own detailed interface and LAN exposure according to the receiver installation.

See the [feature preservation and Survival Kit checklist](docs/FEATURE_PARITY_AND_SURVIVAL_KIT_GATE.md). This document is a non-regression requirement for the integrated Survival Kit responsive Flight Radar Center.

## Data and security

- Reads /run/readsb/aircraft.json in Linux services mode.
- Remote JSON is a user-provided HTTP(S) URL; avoid using untrusted endpoints.
- Exports only a raw received JSON snapshot chosen by the user.
- Stale data is rejected. Missing aircraft positions are never inferred.
- No cloud account or feed uploads. The UI stops polling when closed; systemd receiver
  background service startup remains a user-controlled opt-in.
- Two applications cannot claim the same physical RTL-SDR simultaneously.

## Roadmap

- Signed Windows installer and notarized macOS DMG.
- Verified Windows local SDR backend and driver installer guidance.
- Raspberry Pi packages and headless Survival Kit Radio/SDR Center backend.
- Offline MBTiles packages, aircraft history database, signal graphs and
  multiple receiver support.
