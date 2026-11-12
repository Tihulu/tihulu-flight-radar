# Frozen v0.3.1 feature inventory — evidence is SOURCE, not hardware certification

All paths below are relative to `archive/stable-first/source/`. Every listed path belongs to the **same original Git tree** `a916732793c405e73f5de996b528ac96437222cd`. The separate launcher is a protective adapter, **not** a modification of the frozen application.

| Original capability | Source evidence | Safe launcher / acceptance |
| --- | --- | --- |
| Native Qt WebEngine main window and local bridge | `tihulu_flight_radar/native.py`, `bridge.py` | Original Qt present; synthetic GUI smoke in CI; installed-GUI/Pop!_OS HOLD |
| Native classic dashboard, status, list, aircraft details and exports | `app.py`, `core.py`, `tests/test_core.py` | Original source preserved |
| Real ADS-B/Mode S reception via external readsb | `control.py`, `core.py` | **Passive data read only; no device acquisition** |
| Linux readsb/tar1090 service actions | `control.py`, `tests/test_control.py` | Original Start/Stop/Restart source preserved but **disabled** in Stable First safe runtime |
| Direct readsb process mode and RTL-SDR use | `control.py` | **Disabled in safe launcher**; hardware collision unresolved in original source |
| Remote JSON and local aircraft.json observations | `core.py`, `control.py`, `bridge.py` | Read-only paths remain available; real external data not guaranteed |
| Internet ADS-B sources, cached feeds and attribution | `bridge.py`, `tests/internet_sources.test.cjs` | Real upstream availability, licensing and connectivity not certified |
| Antenna / Internet / Hybrid / Auto source designation | `bridge.py`, `web/app.js`, `web/index.html` | Preserved merge/source logic; no fabricated aircraft |
| Aircraft map, focus/zoom, region fallback and map controls | `map.html`, `map_focus.js`, `web/app.js`, `native.py` | Legacy native defaults include Cologne selection; UI hardware QA HOLD |
| tar1090 viewer/overlay integration | `tar_map.py`, `tar_overlay.py`, `web/tar1090-adapter.js` | Generated upstream tar1090 files are **not** tracked/bundled; parity HOLD |
| Browser/PWA and WebUSB source support | `web/index.html`, `web/sw.js`, `web/browser_usb.mjs`, `web/adsb_worker.mjs` | Original source available, not claimed production-ready WebUSB in new installer |
| Settings, saved receiver mode, location, UI toggles | `app.py`, `native.py` (Qt `QSettings("Tihulu", "FlightRadar")`) | New launcher isolates XDG roots; true profile isolation requires native QA |
| Original build, packaging and tests | `pyproject.toml`, `scripts/`, `packaging/`, `tests/`, `.github/workflows/` | Preserved as inert archive, never used as an installer shortcut |

## Explicit non-claims

- v0.3.2.dev4, later changes on `main` and Draft PR #15–#21 have **not** been imported into this frozen source.
- A Git-identical source tree does **not** prove that the currently installed historical binary or all runtime resource files were identical.
- Stable First's passive launcher does **not** provide working active Start/Stop/Restart, direct radio acquisition, physical RF validation, general-use installer certification, or cross-platform native release acceptance.
- Imported source without generated tar1090 files is not proof of complete bundled offline tar1090 rendering.
- Original upstream dependencies include the Linux readsb decoder, optional systemd services, Qt/WebEngine distributions, and potentially network tile/internet providers. Model files, recordings and private settings are intentionally absent.

See `manifest/provenance.json` for the exhaustive list of **64** files, original executable modes, Git blob SHA-1 and independently computed SHA-256 hashes. The archive's Git subtree SHA matches the historical root tree exactly.
