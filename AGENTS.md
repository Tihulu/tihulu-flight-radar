# TIHULU FLIGHT RADAR — TWO PAGES CONTRACT (read before every change)

## Full upstream tar1090 without an antenna — 0.3.2.dev1 contract

- New preview is pinned at source SHA `ff934a67f0c4b93e23997d01307ad89bc9fbdb95`
  via `preview/v0.3.2-dev1`; legacy 0.3.1 stays frozen at
  `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6`. Never delete/replace
  that legacy branch or make a rollback script silently install from `main`.
- Original tar1090 interface **must open with Internet-only aircraft and zero
  readsb messages**, showing genuine original map/details, and also support
  RF-only and same-ICAO I/R without duplicate planes.
- On Pop!_OS, `scripts/install-linux.sh` installs into the existing pipx
  environment using `--force`, caches original GPL tar1090 assets to the
  user-owned static data directory, and preserves readsb/tar1090/services.
  The `scripts/popos-version-switch.sh` preview/legacy commands use exact
  pinned commit SHAs and verify the imported package version.
- Never auto-start or auto-claim the SDR just to show Internet flights; on
  fresh native install `auto_start_receiver` defaults OFF, and explicit
  user settings are honored. No invented RF counts/positions or permanent
  storage of pairing tokens. Internet access is still necessary to obtain
  real online observations even if the original tar1090 UI itself is cached.
- Share and synchronize the same revised `web/app.js`, `web/tar1090-adapter.js`,
  `web/index.html` and PWA assets in BOTH canonical Pages deployments;
  source-specific display layers must be toggleable and stale data expired.
- Gates: `tests/tar_full_browser.test.cjs`,
  `tests/test_tar_static_internet_only.py`,
  `tests/test_version_switch.py`, original RF provenance, static URL safety,
  and platform build checks. Fixtures alone do not prove the live provider
  / user's physical Nooelec hardware.



## User-verified 0.3.1 stable baseline and optional multi-provider preview (Nov 6, 2026)

Preserve the user's installed Pop!_OS `0.3.1` binary; the native `0.3.2.dev1`
branch is **opt-in only**. On actual user hardware, antenna (R) and Internet
(I) planes already work, and the same ICAO shows once as I/R. This is a hard
regression gate across Linux, macOS, Windows, Pi and both Pages origins.

The preview adds independent network inclusion layers for adsb.lol, adsb.fi,
OpenSky and IntelSky, with bounded polling, timestamps, provider attribution,
rate-limits and no duplicate ICAO markers. Airplanes.live is feeder-restricted:
do not silently poll it. Local RF observations always remain distinguishable
and RF-preferred. Do not claim live provider availability from fixture tests.
Read `tihulu_flight_radar/network_sources.py`, `web/multi_sources.js`, and the
associated tests before changing Internet flight handling.


**Source of truth:** `Tihulu/tihulu-flight-radar` — never develop a second, divergent Flight Radar app in TEXT CENTER.

The **same browser build** must be published at BOTH addresses:
1. Standalone: https://tihulu.github.io/tihulu-flight-radar/
2. TEXT CENTER: https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/

Canonical browser source: `tihulu_flight_radar/web/` in `Tihulu/tihulu-flight-radar`. Preserve its direct WebUSB 1090 MHz reception, genuine RF/Internet/Both provenance, altitude colors, tar1090 backend-health gating, PWA, filters, Hard Stop/USB release, and existing native Windows/Linux/macOS/Pi clients. Never silently auto-claim SDR from a different app. No simulated aircraft data.

**Active reviewed source ref (Nov 6, 2026):** `feature/github-pages-local-bridge-2026-11-06` (draft PR #6). Until approved merge, do not assume `main` has the current browser implementation. Once PR #6 is merged, *atomically update both publishing workflows and this document to `main`*. Do not delete the feature ref before verifying both live sites.

## Mandatory dual publication on every browser update

- Edit and test source in the Flight Radar repository. Do not hand-edit the mirrored `TIHULU-TEXT-CENTER/flight_radar/` as a second source.
- The source branch's `.github/workflows/pages.yml` builds and publishes the standalone site on `gh-pages`. The default-branch `.github/workflows/standalone-pages.yml` supplies scheduled/manual recovery using the same source ref; neither requires deploying through an unconfigured `github-pages` environment.
- The TEXT CENTER repository's `.github/workflows/sync-flight-radar-pages.yml` fetches that *same* source branch and publishes the built files under `flight_radar/` on its existing `gh-pages` branch. It also polls periodically and accepts `workflow_dispatch`. Do not disrupt the Satellite, RF Geolocation, Radio or other TEXT CENTER pages.
- **Publication gates:** both Actions jobs green; both URLs return index.html; bundled `vendor/rtlsdr.mjs` and adsb worker present; both `source-revision.json` files contain the exact same `source_sha` and ideally have byte-identical browser assets. This file is generated during each publish.
- Bump PWA service worker cache version when changing browser assets. Test the two origins separately because WebUSB permissions and cached PWAs are per-origin.
- For urgent user-requested changes, trigger/commit the TEXT CENTER sync on that same turn; scheduled polling is the fallback, not a claim of instant synchronization.
- Do not claim Pages is live merely because a source-branch CI check passed. **Standalone Pages uses GitHub Settings → Pages → Deploy from a branch → `gh-pages` / `(root)`**; its GitHub Actions push alone is insufficient unless the Pages source is configured. If not enabled, report the precise remaining setup action.
- When reporting completed work, always give **both URLs**, active source commit, mirror sync commit, test results and explicit blockers; avoid calling the Flight Radar project complete when only one website was updated.

Full upstream tar1090 frontend is bundled from pinned GPL-2.0-or-later source via `scripts/build-web-tar1090.sh`, including the same-origin `tar1090-adapter.js` and real source data. Never substitute a simplified tar-lookalike for user-requested full aircraft/photo/details controls. Keep source attribution, RF/Internet provenance, and no simulated observations. A public CORS relay is experimental and may not reliably provide Internet aircraft. Never claim third-party backend or photo API has been validated without live tests.

Mirror details: `docs/DUAL_GITHUB_PAGES.md` in this repository and `docs/FLIGHT_RADAR_DUAL_PAGES.md` in TEXT CENTER.

This file is a durable handoff instruction for every coding agent and future development conversation. It supplements rather than overrides existing project preservation/release requirements.
