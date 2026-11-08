# TIHULU Flight Radar

**Real ADS-B / Mode S aircraft tracking — desktop and web.** Internet sources, optional local RTL-SDR reception, the complete original tar1090 map, and deduplicated I / R / I/R aircraft markers.

[**Open web radar**](https://tihulu.github.io/tihulu-flight-radar/) · [**Full tar1090 map**](https://tihulu.github.io/tihulu-flight-radar/?view=tar1090) · [**Install & restore site**](https://tihulu.github.io/tihulu-flight-radar/install.html) · [**TEXT CENTER radar**](https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/)

## Install or update — Pop!_OS, Ubuntu, Debian

**One terminal command, as your regular user (not `sudo bash`):**

```bash
bash -c 'set -o pipefail; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash'
```

This installs the **current `main` desktop build** into the *existing* `pipx` installation (`pipx install --force`). Run it again to update. It refreshes the COSMIC/Linux application shortcuts instead of installing another Flight Radar. You may be asked for administrator permission to install system dependencies and a narrowly scoped `readsb`/`tar1090` service-control rule. The installer **does not purge, restart or auto-claim your SDR, readsb, tar1090, recordings or receiver configuration**. Review [the complete script](scripts/install-linux.sh) before executing a downloaded shell script.

The default shortcut starts a **PySide6 / Qt WebEngine desktop application**. Qt WebEngine renders the interface; the physical RTL-SDR is managed through Linux SDR drivers and native `readsb`, **not through browser WebUSB**.

After installation:

```bash
tihulu-flight-radar
# Check the installed Python package:
~/.local/share/pipx/venvs/tihulu-flight-radar/bin/python -c "import tihulu_flight_radar; print(tihulu_flight_radar.__version__)"
```

The `main` code currently reports **0.3.2.dev4**. This is an *active development build*, not a physically certified hardware release.

### Go back to legacy 0.3.1

The last user-confirmed working 0.3.1 source is permanently recorded at [`legacy/v0.3.1`](https://github.com/Tihulu/tihulu-flight-radar/tree/legacy/v0.3.1), exact commit `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6`. Roll back with **one line**, after closing the app:

```bash
bash -c 'set -euo pipefail; curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/popos-version-switch.sh -o "$HOME/tihulu-flight-switch.sh"; bash "$HOME/tihulu-flight-switch.sh" legacy'
```

The legacy command replaces the current pipx app, **not** the external receiver services or recordings. To reinstall the archived 0.3.2.dev4 preview, run `bash "$HOME/tihulu-flight-switch.sh" preview`. See the [full upgrade/rollback guide](docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md).

## Use the web app

- **Standalone radar:** https://tihulu.github.io/tihulu-flight-radar/
- **Full original tar1090:** https://tihulu.github.io/tihulu-flight-radar/?view=tar1090
- **Shared TEXT CENTER mirror:** https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/
- **Install and download landing page:** https://tihulu.github.io/tihulu-flight-radar/install.html

The browser version runs without a desktop installation. Internet-only aircraft can appear without an antenna when the selected networks are available. Direct USB reception in the browser **is a separate optional WebUSB path** requiring a supported Chromium-based browser and access to the SDR; it is not how the native desktop receives RF.

The website and desktop keep genuine source provenance: **I** = Internet only, **R** = received by physical radio, **I/R** = the same valid ICAO24 aircraft in both. Multiple Internet networks are deduplicated by ICAO24. Outages and CORS/API rate limits may reduce coverage; no synthetic aircraft are inserted.

## Features

- **Real ADS-B and Mode S:** Local `readsb` receiver, optional network decoder, and authenticated loopback companion. RF/Internet/Both overlays and detailed per-aircraft information.
- **Full original tar1090:** Aircraft table, search, filters, metadata, live map, altitude colors and source labels. Can open Internet-only with no SDR.
- **Independent Internet sources:** Preserve `adsb.lol`; optional `adsb.fi`, OpenSky Network and limited IntelSky layers. Source quotas/terms apply. `Airplanes.live` is not queried without compatible access.
- **Country/state/locality location search:** Satellite Center's 8,084-point offline catalog: 7,104 places across Germany's 16 Bundesländer and 980 places across Türkiye's 81 provinces. Choose a city/locality, manual WGS84 coordinates or opt-in device GPS/online geocoding. These are approximate settlement coordinates, **not an exhaustive official Kreis/ilçe registry**.
- **Multi-platform:** Qt app on Pop!_OS/Ubuntu/Debian, Windows x64 and macOS Apple Silicon; ARM64 Raspberry Pi bridge/source support. Drivers and a suitable `readsb` are required for local hardware. Successful CI builds do not prove every device works.

## Windows, macOS and Debian package previews

When cross-platform CI passes, portable bundles appear under [**Cross-platform CI and preview builds**](https://github.com/Tihulu/tihulu-flight-radar/actions/workflows/build.yml). Download artifacts from the relevant successful workflow run. Debian x64 preview packages are named `tihulu-flight-radar_0.3.2.dev4_amd64.deb`. These are **unsigned previews**; native USB drivers/decoder are not bundled.

## Offline single-SDR RF Timing Laboratory

The **RF Timing Laboratory** is built into the same browser and Qt desktop
radar interface. It does **not** need an external aircraft API, an account,
GPS, or cloud processing.

- **WebUSB radio (Brave / Chrome / Edge):** with a single RTL-SDR already
  receiving real 1090 MHz I/Q, capture CRC-verified ADS-B frame sample
  indices at a nominal 2 Msps rate. The local dashboard shows per-aircraft
  interarrival median/MAD, USB host-read delays, packet counts and bounded
  recording buffers. Start, pause, clear, export JSON/CSV, and import a
  previously saved session entirely offline. Open the site online **once**
  to cache its WebUSB driver and other PWA assets before going offline.
- **Qt desktop (Pop!_OS / Linux):** use the same laboratory and a native
  JSON/CSV save dialog. Standard `readsb aircraft.json` supplies real
  receiver observations and relative age, **not raw packet ADC timestamps**.
  Fine sample-index timing requires a raw I/Q or separately verified
  timestamp-capable receiver source. Offline imported recordings can still
  be inspected.
- **RF coverage:** enable **Assume stationary receiver** to retain up to
  64 verified RF-positioned aircraft (at most two hours) and intersect
  their conservative radio-horizon constraints. Six rings are displayed
  to limit clutter. The possible region may narrow as new aircraft arrive,
  but that does **not** establish a precise receiver position or guarantee
  increasing accuracy. Clear the history if you move the antenna.

**Scientific limitation:** the nominal 0.5 µs ADC sample spacing is **not**
0.5 µs UTC arrival-time accuracy. Standard ADS-B packets do not contain
a trustworthy exact transmission epoch, and USB/OS processing latency is
not propagation time. The single-SDR lab therefore does **not** compute
a fake time-of-flight distance, GPS fix or accuracy score. See
[RF Timing Laboratory and coverage limitations](docs/RF_COVERAGE_AND_TIMESTAMP_LIMITS.md).

## Receiver safety and data integrity

- A **physical SDR is never required** to view Internet aircraft or open the map.
- In the native desktop the SDR is handled by Linux/`readsb` (or the platform's equivalent), **not WebUSB**. The same SDR cannot be claimed simultaneously by `readsb` and browser WebUSB.
- The browser local receiver bridge binds to loopback and its non-static API requires a pairing token. Hardware controls are disabled by default unless explicitly requested.
- No fabricated RF signal levels, aircraft positions, MLAT or radio messages. Static aircraft metadata is not proof of reception.
- Browser-only public CORS relays are experimental; neither exact availability nor global coverage is guaranteed.
- Preserve legacy 0.3.1 and the original tar1090 upstream copyright/license notices.

## Architecture

| Component | Technology |
| --- | --- |
| Desktop UI | Python 3.11+, PySide6 / Qt WebEngine |
| Radio decoding | Native `readsb` / RTL-SDR OS drivers (optional) |
| Browser frontend | HTML, CSS, JavaScript, optional browser WebUSB |
| Native/browser bridge | Local Python HTTP API on `127.0.0.1`, authenticated for aircraft/control APIs |
| Maps | Original upstream tar1090 and shared Flight Radar interface |
| Internet data | Selected providers, timestamps, independent caches and ICAO24 deduplication |

**Canonical source:** `Tihulu/tihulu-flight-radar` → `tihulu_flight_radar/web/`. The TEXT CENTER deployment is a **generated mirror**, not a second source repository. All reviewed changes should land on **`main`** and publish to both GitHub Pages origins using [the dual-publication contract](docs/DUAL_GITHUB_PAGES.md).

## Development and test

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
node --test tests/*.test.cjs
```

Cross-platform Actions test Linux, Debian, macOS Apple Silicon and Windows. For Pages builds, see `.github/workflows/pages.yml`; for a local-only bridge see [the bridge guide](docs/GITHUB_PAGES_AND_LOCAL_BRIDGE.md). The app does not bundle or install SDR drivers or a decoder.

## Additional documentation

- [Pop!_OS upgrade and pinned rollback](docs/POP_OS_VERSION_SWITCH_AND_LEGACY.md)
- [Full tar1090 and antenna-optional behavior](docs/ANTENNA_OPTIONAL_TAR1090.md)
- [Dual GitHub Pages publication and parity](docs/DUAL_GITHUB_PAGES.md)
- [Browser WebUSB ownership and Linux USB conflicts](docs/RTL_SDR_WEBUSB_LINUX_OWNERSHIP.md)
- [GitHub Pages and paired local bridge](docs/GITHUB_PAGES_AND_LOCAL_BRIDGE.md)
- [Internet source limitations](docs/TAR1090_WEBUSB_AND_INTERNET_SOURCES.md)

**Attribution:** The bundled original tar1090 frontend remains under its upstream GPL-2.0-or-later licensing and attribution; see `tihulu_flight_radar/web/tar1090/UPSTREAM-GPL-LICENSE.txt` in generated artifacts. The Satellite Center place dataset has separate [ODbL provenance](tihulu_flight_radar/web/CITY_DATA_LICENSE.md). This repository does not currently supply a blanket license for all original project code.
